import os
import json
import glob
import subprocess
import shlex
from pathlib import Path
import redis
from rq import Queue

# Redis connection
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
redis_conn = redis.from_url(REDIS_URL)

# RQ queue
q = Queue("default", connection=redis_conn)

JOB_PREFIX = "job:"


def _set_job_state(job_id: str, data: dict, ttl: int = 86400):
    """
    Save job state in Redis with TTL (default 1 day).
    This is what /info queries to check progress.
    """
    redis_conn.set(f"{JOB_PREFIX}{job_id}", json.dumps(data), ex=ttl)


def _get_first_downloaded(path_prefix: str):
    files = glob.glob(path_prefix + ".*")
    return files[0] if files else None


def run_cmd(cmd, timeout=None):
    """
    Run a shell command and log stdout/stderr to worker logs
    for debugging on Railway.
    """
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)

    print(f"[RUN] {' '.join(cmd)}")
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    out = proc.stdout.decode("utf-8", errors="ignore")
    err = proc.stderr.decode("utf-8", errors="ignore")

    if out.strip():
        print(f"[STDOUT]\n{out}")
    if err.strip():
        print(f"[STDERR]\n{err}")

    return proc.returncode, out, err


def process_media(job_id: str, media_url: str, output_dir: str):
    """
    Worker task executed by RQ.
    Steps:
      1) download via yt-dlp
      2) transcode to mp4
      3) create 30s clip
      4) update Redis state
    """
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    _set_job_state(
        job_id,
        {"status": "downloading", "stage": "downloading", "progress": 0, "job_id": job_id},
    )

    # 1) download
    out_prefix = str(outdir / job_id)
    ytdlp_cmd = ["yt-dlp", "-f", "best", "-o", out_prefix + ".%(ext)s", media_url]

    code, _, err = run_cmd(ytdlp_cmd, timeout=300)
    if code != 0:
        _set_job_state(
            job_id,
            {"status": "failed", "stage": "download_failed", "error": err, "job_id": job_id},
        )
        return

    input_file = _get_first_downloaded(out_prefix)
    if not input_file:
        _set_job_state(
            job_id,
            {"status": "failed", "stage": "no_file", "error": "Download produced no file", "job_id": job_id},
        )
        return

    _set_job_state(
        job_id,
        {"status": "processing", "stage": "converting", "progress": 40, "job_id": job_id},
    )

    # 2) convert to mp4
    final_mp4 = outdir / f"{job_id}.mp4"
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", input_file,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-movflags", "+faststart", str(final_mp4)
    ]
    code2, _, err2 = run_cmd(ffmpeg_cmd, timeout=900)
    if code2 != 0:
        _set_job_state(
            job_id,
            {"status": "failed", "stage": "convert_failed", "error": err2, "job_id": job_id},
        )
        return

    # 3) create 30s clip
    clip_file = outdir / f"{job_id}_clip.mp4"
    _set_job_state(
        job_id,
        {"status": "processing", "stage": "clipping", "progress": 70, "job_id": job_id},
    )
    ffmpeg_clip_cmd = [
        "ffmpeg", "-y", "-ss", "00:00:00", "-i", str(final_mp4),
        "-t", "30", "-c", "copy", str(clip_file)
    ]
    code3, _, err3 = run_cmd(ffmpeg_clip_cmd, timeout=300)
    if code3 != 0:
        # fallback re-encode
        ffmpeg_clip_cmd2 = [
            "ffmpeg", "-y", "-ss", "00:00:00", "-i", str(final_mp4), "-t", "30",
            "-c:v", "libx264", "-c:a", "aac", str(clip_file)
        ]
        code3b, _, err3b = run_cmd(ffmpeg_clip_cmd2, timeout=300)
        if code3b != 0:
            _set_job_state(
                job_id,
                {"status": "failed", "stage": "clip_failed", "error": f"{err3}; {err3b}", "job_id": job_id},
            )
            return

    # 4) success
    _set_job_state(
        job_id,
        {
            "status": "completed",
            "stage": "completed",
            "progress": 100,
            "message": "Completed",
            "job_id": job_id,
            "output_file": clip_file.name,
        },
    )
    return clip_file.name


def enqueue_job(job_id: str, media_url: str, output_dir: str = "outputs"):
    """
    Call this from app.py when receiving /process.
    Enqueues the RQ worker job and sets initial Redis state.
    """
    # initialize job state in Redis
    _set_job_state(job_id, {"status": "queued", "stage": "queued", "progress": 0, "job_id": job_id})

    return q.enqueue(
        process_media,
        job_id,
        media_url,
        output_dir,
        job_id=job_id,
        result_ttl=86400,  # keep result 1 day
        ttl=86400          # job stays in queue max 1 day
    )
