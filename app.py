# app.py
import os
import uuid
import json
import glob
import shutil
import subprocess
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, abort
import redis
from rq import Queue

# Config
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "outputs"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Connect to Redis and RQ
redis_conn = redis.from_url(REDIS_URL)
q = Queue("default", connection=redis_conn, default_timeout=60 * 60 * 2)  # 2 hours

# Local job state keys prefix
JOB_PREFIX = "job:"

app = Flask(__name__)


def _set_job_state(job_id: str, data: dict):
    redis_conn.set(f"{JOB_PREFIX}{job_id}", json.dumps(data), ex=60 * 60 * 6)


def _get_job_state(job_id: str):
    raw = redis_conn.get(f"{JOB_PREFIX}{job_id}")
    return json.loads(raw) if raw else None


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/process", methods=["POST"])
def process():
    payload = request.get_json(force=True, silent=True)
    if not payload:
        return jsonify({"error": "invalid JSON body"}), 400

    media_url = payload.get("media_url")
    if not media_url:
        return jsonify({"error": "media_url missing"}), 400

    job_id = str(uuid.uuid4())
    # initial state
    _set_job_state(job_id, {"status": "queued", "message": "Job queued", "job_id": job_id})

    # enqueue background job (jobs.process_media)
    # import deferred (jobs is a module file shipped with the repo)
    from jobs import process_media

    q.enqueue(process_media, job_id, media_url, OUTPUT_DIR.as_posix())

    return jsonify({"job_id": job_id, "status": "queued"}), 202


@app.route("/status/<job_id>", methods=["GET"])
def status(job_id):
    st = _get_job_state(job_id)
    if not st:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(st)


@app.route("/download/<path:filename>", methods=["GET"])
def download(filename):
    # Security: only serve from OUTPUT_DIR
    safe_path = (OUTPUT_DIR / filename).resolve()
    if not str(safe_path).startswith(str(OUTPUT_DIR.resolve())) or not safe_path.exists():
        abort(404)
    return send_from_directory(OUTPUT_DIR.as_posix(), filename, as_attachment=True)


@app.errorhandler(500)
def handle_500(e):
    app.logger.exception("Internal server error")
    return (
        "<!doctype html><html><head><title>500 Internal Server Error</title></head>"
        "<body><h1><p>Internal Server Error</p></h1></body></html>",
        500,
    )


if __name__ == "__main__":
    # for local debugging
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=False)
