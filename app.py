# app.py
import os
import uuid
import json
from flask import Flask, request, jsonify, send_from_directory, abort
import redis

from jobs import enqueue_job  # import your enqueue function

app = Flask(__name__)

OUTPUT_DIR = os.path.join(os.getcwd(), "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_conn = redis.from_url(REDIS_URL)
JOB_PREFIX = "job:"


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/process", methods=["POST"])
def process():
    body = request.get_json(silent=True) or {}
    media_url = body.get("media_url")
    if not media_url:
        return jsonify({"error": "media_url required"}), 400

    job_id = str(uuid.uuid4())

    # enqueue the worker job
    enqueue_job(job_id, media_url, OUTPUT_DIR)

    return jsonify({"job_id": job_id, "status": "queued"}), 202


@app.route("/info", methods=["POST", "GET"])
def info():
    # Accept POST { job_id } or GET ?job_id=
    body = request.get_json(silent=True) or {}
    job_id = body.get("job_id") or request.args.get("job_id")
    if not job_id:
        return jsonify({"error": "job_id required"}), 400

    raw = redis_conn.get(f"{JOB_PREFIX}{job_id}")
    if not raw:
        return jsonify({"code": 1, "message": "job not found"}), 404

    info = json.loads(raw)

    # Build response
    resp_data = {
        "progress": info.get("progress", 0),
        "stage": info.get("stage"),
        "status": info.get("status"),
    }

    # Add conversion + screenshots if present
    host = request.host_url.rstrip("/")
    if info.get("output_file"):
        resp_data["conversion"] = {
            "url": f"{host}/download/{info['output_file']}",
            "file": info["output_file"],
        }

    response_body = {"code": 0, "data": resp_data}
    return jsonify(response_body), 200


@app.route("/download/<path:filename>")
def download(filename):
    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        return abort(404)
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
