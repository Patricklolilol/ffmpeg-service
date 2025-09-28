# jobs.py
import os
import json
import glob
import subprocess
import shlex
import time
from pathlib import Path
import redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
redis_conn = redis.from_url(REDIS_URL)
JOB_PREFIX = "job:"

def _set_job_state(job_id: str, data: dict):
    redis_conn.set(f"{JOB_PREFIX}{job_id}", json.dumps(data), ex=60 * 60 * 6)

def _get_first_downloaded(path_prefix: str):
    # returns the first matching file path for a prefix, or None
    files = glob.glob(path_prefix + ".*")
    return files[0] if files else None

def run_cmd(cmd, timeout=None):
    # cmd can be list or string
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    return proc.returncode, proc.stdout.decode("utf-8", errors="ignore"), proc.stderr.decode("utf-8", errors="ignore")

def process_media(job_id: str, media_url: str, output_dir: str):
    """
    Steps:
      1) mark queued -> downloading
      2) use yt-dlp to download best video (or fallback audio)
      3) transcode to stable mp4
      4) create a 30s clip sample outputs/<job_id>_clip.mp4
      5) update redis state (download_url paths relative to API)
    """
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    _set_job_state(job_id, {"status": "downloading", "message": "Downloading media", "job_id": job_id})

    # 1) download with yt-dlp to outputs/<job_id>.<ext>
    out_prefix = str(outdir / job_id)
    ytdlp_cmd = ["yt-dlp", "-f", "best", "-o", out_prefix + ".%(ext)s", media_url]

    code, out, err = run_cmd(ytdlp_cmd, timeout=300)
    if code != 0:
        # try audio-only fallback
        _set_job_state(job_id, {"status": "failed", "message": f"Download failed: {err}", "job_id": job_id})
        return

    # find downloaded file path
    input_file = _get_first_downloaded(out_prefix)
    if not input_file:
        _set_job_state(job_id, {"status": "failed", "message": "Download did not produce a file", "job_id": job_id})
        return

    _set_job_state(job_id, {"status": "processing", "message": "Converting to standardized MP4", "job_id": job_id, "input_file": Path(input_file).name})

    # 2) convert to mp4 (re-encode V/A to safe codecs)
    final_mp4 = outdir / f"{job_id}.mp4"
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_file,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(final_mp4),
    ]
    code2, out2, err2 = run_cmd(ffmpeg_cmd, timeout=900)
    if code2 != 0:
        _set_job_state(job_id, {"status": "failed", "message": f"FFmpeg conversion failed: {err2}", "job_id": job_id})
        return

    # 3) create a 30-second clip (start at 0 for now)
    clip_file = outdir / f"{job_id}_clip.mp4"
    ffmpeg_clip_cmd = ["ffmpeg", "-y", "-ss", "00:00:00", "-i", str(final_mp4), "-t", "30", "-c", "copy", str(clip_file)]
    code3, out3, err3 = run_cmd(ffmpeg_clip_cmd, timeout=300)
    if code3 != 0:
        # fallback: re-encode clip if copy fails (some containers / codecs)
        ffmpeg_clip_cmd2 = [
            "ffmpeg",
            "-y",
            "-ss",
            "00:00:00",
            "-i",
            str(final_mp4),
            "-t",
            "30",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(clip_file),
        ]
        code3b, out3b, err3b = run_cmd(ffmpeg_clip_cmd2, timeout=300)
        if code3b != 0:
            _set_job_state(job_id, {"status": "failed", "message": f"Clip creation failed: {err3} ; fallback: {err3b}", "job_id": job_id})
            return

    # success
    download_url = f"/download/{clip_file.name}"
    _set_job_state(job_id, {"status": "completed", "message": "Completed", "job_id": job_id, "download_url": download_url, "output_file": clip_file.name})
    return
