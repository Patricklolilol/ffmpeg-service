#!/usr/bin/env python3
"""
worker.py

Usage:
- This file exposes process_job(job_id, media_url, options)
- RQ CLI should import it (e.g. job queued as 'worker.process_job')
- Ensure REDIS_URL is set in the environment.
"""

import os
import sys
import json
import shlex
import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path

import redis

# Optional imports (not fatal)
try:
    from faster_whisper import WhisperModel
    _HAS_WHISPER = True
except Exception:
    WhisperModel = None
    _HAS_WHISPER = False

try:
    import cv2
    _HAS_CV2 = True
except Exception:
    cv2 = None
    _HAS_CV2 = False

# Logging
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("worker")

# Environment / defaults
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "outputs"))
BASE_URL = os.environ.get("BASE_URL", "")  # e.g. https://ffmpeg-service... used to build public urls

# Ensure output directory
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Connect to Redis
r = redis.from_url(REDIS_URL, decode_responses=True)

# Redis key format
def _redis_key(job_id: str) -> str:
    return f"ff:job:{job_id}"

def now_ts() -> str:
    return datetime.utcnow().isoformat() + "Z"

def write_redis(job_id: str, data: dict):
    """Write the canonical shape returned by /info: { code, data }"""
    payload = {"code": 0, "data": data}
    key = _redis_key(job_id)
    r.set(key, json.dumps(payload))
    log.debug("Wrote redis key %s -> %s", key, json.dumps(payload))

def write_error(job_id: str, message: str, err_meta=None):
    data = {
        "progress": 0,
        "stage": "Failed",
        "status": "failed",
        "error": message,
        "updated_at": now_ts(),
    }
    if err_meta:
        data["error_meta"] = err_meta
    payload = {"code": 1, "data": data}
    r.set(_redis_key(job_id), json.dumps(payload))
    log.error("Job %s failed: %s", job_id, message)

def update_job_status(job_id: str, progress: int, stage: str, status: str, extra: dict = None):
    """Update progress/stage/status and optionally include screenshots/conversion info"""
    data = {
        "progress": int(progress),
        "stage": stage,
        "status": status,
        "updated_at": now_ts(),
    }
    if extra:
        data.update(extra)
    write_redis(job_id, data)
    log.info("Job %s status update: %s %d%%", job_id, stage, progress)

def run_cmd(cmd, cwd=None, timeout=None):
    """Run shell command, return (returncode, stdout, stderr). Raises subprocess.CalledProcessError on non-zero if raise_on_err True."""
    log.debug("Running command: %s", cmd)
    completed = subprocess.run(shlex.split(cmd), cwd=cwd, capture_output=True, text=True, timeout=timeout)
    log.debug("Cmd exit=%s stdout=%s stderr=%s", completed.returncode, completed.stdout[:2000], completed.stderr[:2000])
    return completed.returncode, completed.stdout, completed.stderr

def download_media(job_id: str, media_url: str):
    """Download via yt-dlp to outputs/<job_id>.*; return local filepath (first match)"""
    out_template = OUTPUT_DIR / f"{job_id}.%(ext)s"
    cmd = f"yt-dlp -f best -o {shlex.quote(str(out_template))} {shlex.quote(media_url)}"
    update_job_status(job_id, 5, "Downloading", "processing")
    rc, out, err = run_cmd(cmd, timeout=600)
    if rc != 0:
        raise RuntimeError(f"yt-dlp failed (rc={rc}): {err.strip()}")
    # find downloaded file
    for ext in ("mp4", "mkv", "webm", "mov", "m4a", "webm", "mkv"):
        candidate = OUTPUT_DIR / f"{job_id}.{ext}"
        if candidate.exists():
            return str(candidate)
    # If not found, list directory and return first matching
    for p in OUTPUT_DIR.iterdir():
        if p.name.startswith(job_id + "."):
            return str(p)
    raise FileNotFoundError("Download finished but file not found for job " + job_id)

def transcribe_audio(job_id: str, input_file: str) -> dict:
    """Attempt transcription. Returns dict with 'transcript' and 'srt' paths (or empty strings)."""
    update_job_status(job_id, 30, "Transcribing", "processing")
    base = Path(input_file)
    audio_path = OUTPUT_DIR / f"{job_id}_audio.wav"
    # extract audio
    cmd_extract = f"ffmpeg -y -i {shlex.quote(str(base))} -ar 16000 -ac 1 -vn {shlex.quote(str(audio_path))}"
    rc, out, err = run_cmd(cmd_extract, timeout=300)
    if rc != 0:
        log.warning("Audio extract failed: %s", err.strip())
        # Still continue; return empty transcript
        return {"transcript": "", "srt": ""}

    if _HAS_WHISPER:
        try:
            update_job_status(job_id, 35, "Transcribing", "processing")
            log.info("Using faster-whisper for transcription")
            model = WhisperModel("small", device="cpu", compute_type="int8")  # adjust model & device as desired
            segments, info = model.transcribe(str(audio_path))
            transcript_text = "\n".join([s.text for s in segments])
            # write SRT
            srt_path = OUTPUT_DIR / f"{job_id}.srt"
            with open(srt_path, "w", encoding="utf-8") as fh:
                for i, seg in enumerate(segments, start=1):
                    start = seg.start
                    end = seg.end
                    def fmt(ts): return f"{int(ts//3600):02}:{int((ts%3600)//60):02}:{int(ts%60):02},{int((ts*1000)%1000):03}"
                    fh.write(f"{i}\n{fmt(start)} --> {fmt(end)}\n{seg.text.strip()}\n\n")
            # also write raw transcript
            transcript_path = OUTPUT_DIR / f"{job_id}.txt"
            transcript_path.write_text(transcript_text, encoding="utf-8")
            return {"transcript": str(transcript_path), "srt": str(srt_path)}
        except Exception as e:
            log.exception("faster-whisper failed: %s", e)
            return {"transcript": "", "srt": ""}
    else:
        log.info("faster-whisper not available; skipping transcription")
        return {"transcript": "", "srt": ""}

def detect_faces_and_scenes(job_id: str, video_file: str) -> dict:
    """Optional: extract thumbnails and (if cv2 available) detect faces. Returns list of thumbnail paths."""
    update_job_status(job_id, 60, "Detecting", "processing")
    thumbs = []
    # Example: create a thumbnail at 5s and 10s (expand this to real scene detection)
    for t_idx, t_sec in enumerate([5, 10, 20]):
        thumb_path = OUTPUT_DIR / f"{job_id}_thumb{t_idx+1}.jpg"
        cmd = f"ffmpeg -y -ss {t_sec} -i {shlex.quote(str(video_file))} -frames:v 1 -q:v 2 {shlex.quote(str(thumb_path))}"
        rc, out, err = run_cmd(cmd, timeout=30)
        if rc == 0 and thumb_path.exists():
            thumbs.append(str(thumb_path))
    # If cv2 exists we could run face detection and crop/center thumbnails - optional
    if _HAS_CV2 and thumbs:
        log.info("OpenCV available: running face detection for thumbnails")
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        enhanced = []
        for tp in thumbs:
            img = cv2.imread(tp)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            if len(faces) > 0:
                # crop to first face (with padding)
                x, y, w, h = faces[0]
                pad = int(0.4 * max(w, h))
                x0 = max(0, x - pad)
                y0 = max(0, y - pad)
                x1 = min(img.shape[1], x + w + pad)
                y1 = min(img.shape[0], y + h + pad)
                crop = img[y0:y1, x0:x1]
                outp = OUTPUT_DIR / f"{Path(tp).stem}_face.jpg"
                cv2.imwrite(str(outp), crop)
                enhanced.append(str(outp))
            else:
                enhanced.append(tp)
        thumbs = enhanced
    return {"screenshots": thumbs}

def create_clips(job_id: str, video_file: str, options: dict) -> dict:
    """
    Create clips logic. This is a simple example making one short clip.
    options may include:
      - clip_seconds: int (default 30)
      - start_at: int (seconds) (default 0)
      - ratio: "9:16" / "16:9"
    Returns dict with 'clips' list (each {url, path, duration})
    """
    update_job_status(job_id, 80, "Creating Clips", "processing")
    clip_seconds = int(options.get("clip_seconds", 30))
    start_at = int(options.get("start_at", 0))
    clip_path = OUTPUT_DIR / f"{job_id}_clip.mp4"
    cmd = f"ffmpeg -y -ss {start_at} -i {shlex.quote(str(video_file))} -t {clip_seconds} -c:v libx264 -c:a aac -strict -2 {shlex.quote(str(clip_path))}"
    rc, out, err = run_cmd(cmd, timeout=300)
    if rc != 0:
        raise RuntimeError("ffmpeg cut failed: " + err.strip())
    # Build absolute download URL if BASE_URL set
    public_url = None
    if BASE_URL:
        public_url = BASE_URL.rstrip("/") + f"/download/{clip_path.name}"
    else:
        public_url = f"/download/{clip_path.name}"
    return {"clips": [{"path": str(clip_path), "url": public_url, "duration": clip_seconds}]}

def finalize_and_upload(job_id: str, transcription: dict, detection: dict, clips: dict):
    """Mark job completed with conversion url(s) and screenshots"""
    update_job_status(job_id, 95, "Uploading", "processing")
    # convert returned data to expected shape
    data = {
        "progress": 100,
        "stage": "Completed",
        "status": "completed",
        "updated_at": now_ts(),
    }
    # add screenshots
    screenshots = []
    for s in detection.get("screenshots", []):
        name = Path(s).name
        url = BASE_URL.rstrip("/") + f"/download/{name}" if BASE_URL else f"/download/{name}"
        screenshots.append({"url": url, "path": s})
    if screenshots:
        data["screenshots"] = screenshots
    # add conversion field: pick first clip
    if clips.get("clips"):
        first = clips["clips"][0]
        data["conversion"] = {"url": first["url"], "path": first["path"]}
    # add transcript attachments if present
    if transcription.get("srt"):
        sname = Path(transcription["srt"]).name
        data.setdefault("transcript", {})["srt"] = (BASE_URL.rstrip("/") + f"/download/{sname}") if BASE_URL else f"/download/{sname}"
    if transcription.get("transcript"):
        tname = Path(transcription["transcript"]).name
        data.setdefault("transcript", {})["txt"] = (BASE_URL.rstrip("/") + f"/download/{tname}") if BASE_URL else f"/download/{tname}"

    write_redis(job_id, data)
    update_job_status(job_id, 100, "Completed", "completed")
    log.info("Job %s completed and finalized", job_id)
    return data

def process_job(job_id: str, media_url: str, options: dict = None):
    """
    Main entrypoint for an RQ job.
    - job_id: external id given when queueing
    - media_url: URL to download (YouTube link etc)
    - options: optional dict with clip options
    """
    if options is None:
        options = {}
    log.info("Starting process_job job_id=%s media_url=%s", job_id, media_url)
    try:
        # initial queued write
        write_redis(job_id, {"progress": 0, "stage": "Queued", "status": "queued", "created_at": now_ts()})
        # 1) download
        video_path = download_media(job_id, media_url)
        update_job_status(job_id, 15, "Downloaded", "processing", {"input_file": Path(video_path).name})
        # 2) transcribe
        try:
            transcription = transcribe_audio(job_id, video_path)
        except Exception as e:
            log.exception("Transcription error")
            transcription = {"transcript": "", "srt": ""}
        # 3) detect scenes / faces and screenshots
        detection = detect_faces_and_scenes(job_id, video_path)
        # 4) create clips
        clips = create_clips(job_id, video_path, options)
        # 5) finalize
        final = finalize_and_upload(job_id, transcription, detection, clips)
        return final
    except Exception as e:
        log.exception("Processing failed for job %s", job_id)
        write_error(job_id, str(e))
        # Reraise so RQ logs the exception too (depending on whether you want this)
        raise

# CLI convenience so you can run worker job locally for testing:
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python worker.py <job_id> <media_url> [json-options]")
        sys.exit(2)
    jid = sys.argv[1]
    media = sys.argv[2]
    opts = {}
    if len(sys.argv) > 3:
        try:
            opts = json.loads(sys.argv[3])
        except Exception:
            log.warning("Invalid options json; ignoring")
    try:
        res = process_job(jid, media, opts)
        print("DONE:", json.dumps(res))
    except Exception as e:
        print("ERROR:", str(e))
        sys.exit(1)
