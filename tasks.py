# tasks.py
import os
import time
import json
import glob
import shlex
import subprocess
import math
from pathlib import Path

import redis

REDIS_URL = os.getenv("REDIS_URL", "")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL env var must be set for worker")

redis_conn = redis.from_url(REDIS_URL, decode_responses=True)

FFMPEG_SERVICE_URL = os.getenv("FFMPEG_SERVICE_URL", "").strip().rstrip("/")
if FFMPEG_SERVICE_URL and not FFMPEG_SERVICE_URL.startswith("http"):
    FFMPEG_SERVICE_URL = "https://" + FFMPEG_SERVICE_URL

OUTPUTS_DIR = os.path.join(os.getcwd(), "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)

def job_key(job_id: str) -> str:
    return f"job:{job_id}"

def update_job(job_id: str, mapping: dict):
    mapping = {k: (json.dumps(v) if isinstance(v, (list, dict)) else str(v)) for k, v in mapping.items()}
    redis_conn.hset(job_key(job_id), mapping=mapping)
    redis_conn.hset(job_key(job_id), mapping={"updated_at": str(int(time.time()))})
    print(f"[tasks] job {job_id} update:", mapping)

def run_cmd(cmd, cwd=None, env=None):
    print(f"[tasks] run: {' '.join(shlex.quote(c) for c in cmd)}")
    res = subprocess.run(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(res.stdout)
    res.check_returncode()
    return res.stdout

def get_media_file_for_job(job_id: str):
    candidates = glob.glob(os.path.join(OUTPUTS_DIR, f"{job_id}.*"))
    if candidates:
        return candidates[0]
    candidates = glob.glob(os.path.join(OUTPUTS_DIR, f"{job_id}*"))
    return candidates[0] if candidates else None

def probe_duration(file_path: str) -> float:
    import json as _json
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", file_path]
    out = subprocess.check_output(cmd, text=True)
    info = _json.loads(out)
    dur = None
    if "format" in info and "duration" in info["format"]:
        try:
            dur = float(info["format"]["duration"])
        except:
            dur = None
    if not dur:
        for s in info.get("streams", []):
            if s.get("duration"):
                try:
                    dur = float(s["duration"])
                    break
                except:
                    pass
    return dur or 0.0

def process_media(job_id: str, media_url: str):
    try:
        update_job(job_id, {"status": "processing", "stage": "downloading", "progress": 0})
        out_template = os.path.join(OUTPUTS_DIR, f"{job_id}.%(ext)s")
        cmd = ["yt-dlp", "-f", "bestvideo+bestaudio/best", "-o", out_template, media_url]
        run_cmd(cmd)

        input_file = get_media_file_for_job(job_id)
        if not input_file:
            raise RuntimeError("Download produced no file")

        update_job(job_id, {"stage": "downloaded", "progress": 5, "input_file": input_file})

        duration = probe_duration(input_file)
        if duration <= 0:
            duration = 60.0
        update_job(job_id, {"stage": "probing", "progress": 8, "duration": str(duration)})

        clip_length = min(30, max(5, duration / 3.0))
        starts = []
        if duration <= clip_length * 1.5:
            starts = [0.0]
            clip_length = max(1.0, duration)
        else:
            starts = [0.0, max(0.0, (duration / 2.0) - (clip_length / 2.0)), max(0.0, duration - clip_length)]
        clip_paths = []
        thumbs = []

        total_steps = len(starts) * 2 + 3
        step = 0

        for idx, start in enumerate(starts, start=1):
            step += 1
            update_job(job_id, {"stage": "clipping", "progress": int(10 + step * 70 / total_steps)})
            out_clip = os.path.join(OUTPUTS_DIR, f"{job_id}_clip{idx}.mp4")
            cmd = [
                "ffmpeg",
                "-y",
                "-ss", str(max(0, float(start))),
                "-i", input_file,
                "-t", str(int(math.ceil(clip_length))),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                out_clip
            ]
            run_cmd(cmd)
            clip_paths.append(out_clip)

            step += 1
            update_job(job_id, {"stage": "thumbnail", "progress": int(10 + step * 70 / total_steps)})
            thumb_out = os.path.join(OUTPUTS_DIR, f"{job_id}_thumb{idx}.jpg")
            cmd2 = ["ffmpeg", "-y", "-ss", str(max(0, float(start) + 0.5)), "-i", input_file, "-vframes", "1", "-q:v", "2", thumb_out]
            run_cmd(cmd2)
            thumbs.append(thumb_out)

        clips_urls = ["/download/" + Path(p).name for p in clip_paths]
        thumbs_urls = ["/download/" + Path(p).name for p in thumbs]

        update_job(job_id, {
            "status": "completed",
            "stage": "completed",
            "progress": 100,
            "conversion_url": clips_urls[0] if clips_urls else "",
            "clips": clips_urls,
            "screenshots": thumbs_urls
        })
        return {"ok": True}

    except subprocess.CalledProcessError as e:
        msg = f"Command failed: {e}. Output: {getattr(e, 'output', '')}"
        update_job(job_id, {"status": "failed", "stage": "failed", "progress": 0, "error_message": msg})
        raise
    except Exception as e:
        msg = f"Error: {e}"
        update_job(job_id, {"status": "failed", "stage": "failed", "progress": 0, "error_message": msg})
        raise
