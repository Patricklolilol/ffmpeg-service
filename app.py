# app.py
import os
import uuid
import time
import json
from flask import Flask, request, jsonify, send_from_directory, abort
import redis
import rq
import tasks  # ensure this is importable for RQ worker

app = Flask(__name__)

REDIS_URL = os.getenv("REDIS_URL", "")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL env var must be set")

redis_conn = redis.from_url(REDIS_URL, decode_responses=True)
queue = rq.Queue("default", connection=redis_conn)

# Base URL used to build absolute download URLs. Set in Railway variables:
# FFMPEG_SERVICE_URL=https://ffmpeg-service-production-79e5.up.railway.app
FFMPEG_SERVICE_URL = os.getenv("FFMPEG_SERVICE_URL", "").strip().rstrip("/")
if FFMPEG_SERVICE_URL and not FFMPEG_SERVICE_URL.startswith("http"):
    FFMPEG_SERVICE_URL = "https://" + FFMPEG_SERVICE_URL

OUTPUTS_DIR = os.path.join(os.getcwd(), "outputs")

def job_key(job_id: str) -> str:
    return f"job:{job_id}"

def set_job_fields(job_id: str, mapping: dict):
    redis_conn.hset(job_key(job_id), mapping=mapping)
    redis_conn.hset(job_key(job_id), mapping={"updated_at": str(int(time.time()))})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/process", methods=["POST"])
def process_route():
    """
    Accepts: {"media_url": "<url>"}
    Returns async shape:
      HTTP 202 { "job_id": "...", "status": "queued" }
    """
    payload = request.get_json(force=True, silent=True) or {}
    media_url = payload.get("media_url") or payload.get("url") or payload.get("mediaUrl")
    if not media_url:
        return jsonify({"error": "media_url required"}), 400

    job_id = str(uuid.uuid4())
    created = int(time.time())
    # initial metadata in Redis
    initial = {
        "status": "queued",
        "stage": "queued",
        "progress": "0",
        "created_at": str(created),
        "updated_at": str(created),
        "media_url": media_url
    }
    redis_conn.hset(job_key(job_id), mapping=initial)

    # enqueue the actual background job (tasks.process_media)
    # pass the job_id so worker can update Redis
    queue.enqueue(tasks.process_media, job_id, media_url, job_timeout=60*60*2)  # 2h

    response = {"job_id": job_id, "status": "queued"}
    return jsonify(response), 202

@app.route("/info", methods=["POST"])
def info_route():
    """
    Accepts: {"job_id": "..." }
    Returns: {"code":0,"data":{ progress, stage, status, screenshots, conversion:{url}, clips: [...] }}
    """
    payload = request.get_json(force=True, silent=True) or {}
    job_id = payload.get("job_id") or payload.get("jobId")
    if not job_id:
        return jsonify({"code": 1, "message": "job_id required"}), 400

    key = job_key(job_id)
    if not redis_conn.exists(key):
        return jsonify({"code": 2, "message": "job not found"}), 404

    raw = redis_conn.hgetall(key)
    # normalize
    status = raw.get("status", "")
    stage = raw.get("stage", "")
    try:
        progress = int(raw.get("progress", "0"))
    except Exception:
        progress = 0
    screenshots = []
    if raw.get("screenshots"):
        try:
            screenshots = json.loads(raw.get("screenshots"))
        except Exception:
            screenshots = [raw.get("screenshots")]
    clips = []
    if raw.get("clips"):
        try:
            clips = json.loads(raw.get("clips"))
        except Exception:
            clips = []
    conversion_url = raw.get("conversion_url") or ""
    if conversion_url and FFMPEG_SERVICE_URL and conversion_url.startswith("/"):
        conversion_url = FFMPEG_SERVICE_URL.rstrip("/") + conversion_url

    # Build the response shape expected by Lovable (compatibility)
    data = {
        "status": status,
        "stage": stage,
        "progress": progress,
        "screenshots": screenshots,
        "clips": clips,
        "conversion": {"url": conversion_url} if conversion_url else None,
    }
    return jsonify({"code": 0, "data": data}), 200

@app.route("/download/<path:filename>", methods=["GET"])
def download(filename):
    # Security note: we allow only files from outputs directory
    safe_path = os.path.abspath(OUTPUTS_DIR)
    target = os.path.abspath(os.path.join(OUTPUTS_DIR, filename))
    if not target.startswith(safe_path):
        abort(403)
    if not os.path.exists(target):
        return jsonify({"error": "file not found"}), 404
    # send file
    return send_from_directory(OUTPUTS_DIR, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
