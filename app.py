import os
from flask import Flask, request, jsonify, send_from_directory
from rq import Queue
from redis import Redis
import uuid

app = Flask(__name__)

# Redis connection
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_conn = Redis.from_url(redis_url)
q = Queue("default", connection=redis_conn)

OUTPUT_DIR = os.path.join(os.getcwd(), "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    media_url = data.get("media_url")
    if not media_url:
        return jsonify({"error": "media_url required"}), 400

    job_id = str(uuid.uuid4())
    job = q.enqueue("worker.process_media", media_url, job_id, OUTPUT_DIR)

    return jsonify({"job_id": job_id, "status": "queued"}), 202


@app.route("/info", methods=["POST"])
def info():
    data = request.get_json()
    job_id = data.get("job_id")
    if not job_id:
        return jsonify({"error": "job_id required"}), 400

    # Look up job in Redis
    from rq.job import Job
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        status = job.get_status()
        meta = job.meta or {}
    except Exception:
        return jsonify({"code": 1, "error": "job not found"}), 404

    response = {
        "code": 0,
        "data": {
            "status": status,
            "progress": meta.get("progress", 0),
            "stage": meta.get("stage", "unknown"),
            "conversion": meta.get("conversion"),
            "screenshots": meta.get("screenshots", [])
        }
    }
    return jsonify(response), 202 if status in ["queued", "started"] else 200


@app.route("/download/<path:filename>", methods=["GET"])
def download(filename):
    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.isfile(filepath):
        return jsonify({"error": "file not found"}), 404
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)
