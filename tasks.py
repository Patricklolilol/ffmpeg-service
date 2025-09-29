import os
import shlex
import time
import json
import subprocess
from pathlib import Path
from yt_dlp import YoutubeDL
from redis import Redis
from rq import get_current_job

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
redis_conn = Redis.from_url(REDIS_URL)

ROOT = Path(__file__).parent.resolve()
OUT_DIR = ROOT / "outputs"
OUT_DIR.mkdir(exist_ok=True)


def safe_run(cmd):
    print("CMD:", cmd)
    proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print("STDOUT:", proc.stdout)
    print("STDERR:", proc.stderr)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\nSTDERR: {proc.stderr}")
    return proc.stdout


def download_media(media_url, dest_path):
    ydl_opts = {
        "outtmpl": str(dest_path),
        "format": "bestaudio/best+bestvideo/best",
        "quiet": True,
        "no_warnings": True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(media_url, download=True)
    return info


def transcribe_audio_if_possible(audio_file, srt_out):
    # optional faster-whisper - only run if installed
    try:
        from faster_whisper import WhisperModel
    except Exception:
        print("faster-whisper not available: skipping transcription")
        return False

    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(audio_file), beam_size=5)
    # write simple SRT
    with open(srt_out, "w", encoding="utf-8") as fh:
        idx = 1
        for seg in segments:
            start = seg.start
            end = seg.end
            def fmt(t):
                h = int(t // 3600)
                m = int((t % 3600) // 60)
                s = int(t % 60)
                ms = int((t - int(t)) * 1000)
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
            fh.write(f"{idx}\n")
            fh.write(f"{fmt(start)} --> {fmt(end)}\n")
            fh.write(seg.text.strip() + "\n\n")
            idx += 1
    return True


def burn_subtitles(input_video, srt_file, out_video):
    # ffmpeg with subtitles filter (libass must be present in ffmpeg build)
    cmd = f'ffmpeg -y -i "{input_video}" -vf "subtitles={srt_file}:force_style=\'FontName=DejaVu Sans,Fontsize=28\'" -c:a copy "{out_video}"'
    safe_run(cmd)


def create_clips_from_video(video_file, out_prefix, job_meta):
    """
    Create three short clips at approximate highlights:
    - This is a simple algorithm: create 3 equal-length clips from the video.
    - You can replace this with face-detection / speaker-change logic later.
    """
    # get duration
    cmd = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{video_file}"'
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError("ffprobe failed: " + out.stderr)
    duration = float(out.stdout.strip())
    clip_len = max(3, min(30, int(duration / 6)))  # clip length heuristic

    clips = []
    thumbs = []
    starts = [max(0, (duration * i) / 4) for i in range(1, 4)]
    for i, s in enumerate(starts, start=1):
        clip_path = Path(video_file).parent / f"{out_prefix}_clip_{i}.mp4"
        cmd = f'ffmpeg -y -ss {s:.2f} -i "{video_file}" -t {clip_len} -c:v libx264 -preset fast -crf 23 -c:a aac -b:a 128k "{clip_path}"'
        safe_run(cmd)
        clips.append(clip_path.name)

        thumb_path = Path(video_file).parent / f"{out_prefix}_thumb_{i}.jpg"
        cmd2 = f'ffmpeg -y -ss {s:.2f} -i "{video_file}" -frames:v 1 -q:v 2 "{thumb_path}"'
        safe_run(cmd2)
        thumbs.append(thumb_path.name)

    return clips, thumbs


def process_job(job_id, media_url, options):
    """
    Worker entrypoint — runs inside RQ worker.
    Steps:
      - download media
      - extract audio/video as .mp4
      - optional transcription -> produce subtitles and burn into clips
      - generate clips and thumbs
      - write metadata into job.meta
    """
    job = get_current_job()
    try:
        job.meta["stage"] = "downloading"
        job.meta["progress"] = 5
        job.save_meta()

        workdir = OUT_DIR / job_id
        workdir.mkdir(parents=True, exist_ok=True)

        # Download into workdir/input.%(ext)s
        out_template = str(workdir / "input.%(ext)s")
        info = download_media(media_url, out_template)

        # find downloaded file (mp4/mkv/webm)
        downloaded = None
        for p in workdir.iterdir():
            if p.name.startswith("input.") and p.is_file():
                downloaded = p
                break
        if downloaded is None:
            raise RuntimeError("Download did not produce file")

        # For safety convert to mp4 container if needed
        mp4_file = workdir / f"{job_id}.mp4"
        cmd_copy = f'ffmpeg -y -i "{downloaded}" -c:v copy -c:a aac -b:a 128k "{mp4_file}"'
        safe_run(cmd_copy)

        job.meta["stage"] = "transcribing"
        job.meta["progress"] = 30
        job.save_meta()

        srt_file = workdir / f"{job_id}.srt"
        transcribed = transcribe_audio_if_possible(mp4_file, srt_file)

        job.meta["stage"] = "clipping"
        job.meta["progress"] = 50
        job.save_meta()

        # create clips (3) and thumbs
        out_prefix = job_id
        clips, thumbs = create_clips_from_video(mp4_file, out_prefix, job.meta)

        # If we have subtitles, burn them into each clip (optional)
        if transcribed and srt_file.exists():
            job.meta["stage"] = "burning_captions"
            job.meta["progress"] = 80
            job.save_meta()
            # burn separately for each clip
            for i, clip in enumerate(clips, start=1):
                clip_path = workdir / clip
                burned = workdir / f"{out_prefix}_clip_{i}_captioned.mp4"
                try:
                    burn_subtitles(clip_path, srt_file, burned)
                    # replace clip with captioned version
                    clip_path.unlink()
                    burned.rename(clip_path)
                except Exception as e:
                    print("Burn subtitles failed for", clip_path, e)

        # final metadata save
        job.meta["stage"] = "completed"
        job.meta["progress"] = 100
        job.meta["options"] = options
        job.save_meta()

        # return a small result
        return {"job_id": job_id, "clips": clips, "thumbnails": thumbs}

    except Exception as exc:
        print("Job failed:", exc)
        job.meta["stage"] = "failed"
        job.meta["progress"] = 0
        job.save_meta()
        raise
