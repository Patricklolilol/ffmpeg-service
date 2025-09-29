# app.py
import os
import uuid
import time
import json
import logging
from flask import Flask, request, jsonify, abort

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Simple in-memory job store for demo. Replace with persistent DB in prod.
JOBS = {}

# API key (optional) — set FFMPEG_API_KEY in Railway env if you want to require it.
API_KEY = os.getenv("FFMPEG_API_KEY")

def require_api_key_hdr():
    if not API_KEY:
        return True
    key = request.headers.get("x-api-key")
    return key == API_KEY

@app.before_request
def check_api_key():
    # enforce only if API_KEY exists in env
    if API_KEY:
        key = request.headers.get("x-api-key")
        if key != API_KEY:
            abort(401, description="Invalid or missing API key")

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status":"ok"})

@app.route("/process", methods=["POST"])
def process():
    """
    Accepts JSON:
      { "media_url": "...", "options": {...} }
    For demo we will accept and queue a job and immediately return job_id + status "queued"
    To support synchronous mode in future, you can return code:0 + data on success (200).
    """
    try:
        payload = request.get_json(force=True)
        app.logger.info("POST /process payload: %s", payload)

        media_url = payload.get("media_url")
        if not media_url:
            return jsonify({"status":"error", "message":"media_url required"}), 400

        # Create a job id for your service (this is your ffmpeg_job_id that lovables stores)
        ffmpeg_job_id = str(uuid.uuid4())
        now = int(time.time())

        # store minimal job metadata; a real service would spawn a background worker
        JOBS[ffmpeg_job_id] = {
            "job_id": ffmpeg_job_id,
            "status": "queued",
            "media_url": media_url,
            "options": payload.get("options") or {},
            "created_at": now,
            "updated_at": now,
            # "progress": 0,
            # "result": None
        }

        # Immediately return asynchronous accepted shape (202)
        resp = {"job_id": ffmpeg_job_id, "status": "queued"}
        app.logger.info("Queued ffmpeg job: %s", resp)
        return jsonify(resp), 202

    except Exception as e:
        app.logger.exception("Error in /process")
        return jsonify({"status":"error","message": str(e)}), 500

@app.route("/info", methods=["POST"])
def info():
    """
    Report status of a ffmpeg job. Accepts:
      { "job_id": "<id>" }
    Responds:
      - If processing: {"job_id": "...", "status": "processing", "progress": 20}
      - If queued: {"job_id":"...","status":"queued"}
      - If completed: {"code":0, "data": { "conversion": {"url": "/download/<file>"}, "screenshots":[...]} }
      - If failed: {"code":1, "message":"failed reason"}
    """
    try:
        payload = request.get_json(force=True)
        app.logger.info("/info payload: %s", payload)
        job_id = payload.get("job_id") or payload.get("jobId")
        if not job_id:
            return jsonify({"status":"error","message":"job_id required"}), 400

        job = JOBS.get(job_id)
        if not job:
            return jsonify({"code":1,"message":"job not found"}), 404

        # Demo: simulate flow transitions depending on age
        age = int(time.time()) - job["created_at"]

        if age < 3:
            # queued
            return jsonify({"job_id": job_id, "status": "queued"}), 200
        elif age < 8:
            # processing
            return jsonify({"job_id": job_id, "status": "processing", "progress": 30}), 200
        else:
            # completed — return a data shape similar to what Lovable expects:
            # code === 0 and data with conversion.url and screenshots
            output_file = f"/download/{job_id}_clip.mp4"
            data = {
                "conversion": {"url": output_file},
                "screenshots": [
                    {"time": 0.0, "url": f"/download/{job_id}_thumb1.jpg"},
                    {"time": 1.5, "url": f"/download/{job_id}_thumb2.jpg"}
                ]
            }
            # mark job as completed in store
            job["status"] = "completed"
            job["result"] = data
            job["updated_at"] = int(time.time())
            return jsonify({"code": 0, "data": data}), 200

    except Exception as e:
        app.logger.exception("Error in /info")
        return jsonify({"status":"error","message": str(e)}), 500

# Simple download endpoints for demo — in prod these would stream actual files
@app.route("/download/<path:filename>", methods=["GET"])
def download_demo(filename):
    # For demo we return a JSON message instead of real binary files.
    return jsonify({"message": "This is a placeholder for " + filename}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
