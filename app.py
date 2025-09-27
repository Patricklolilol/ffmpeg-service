import os
import uuid
import redis
from rq import Queue
from flask import Flask, request, jsonify

app = Flask(__name__)

# Redis connection
redis_url = os.getenv("REDIS_URL")
if not redis_url:
    raise ValueError("Missing REDIS_URL in environment variables")

conn = redis.from_url(redis_url)
q = Queue(connection=conn)

# Healthcheck
@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}

# Submit job
@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    if not data or "media_url" not in data:
        return jsonify({"error": "media_url is required"}), 400

    media_url = data["media_url"]
    job_id = str(uuid.uuid4())

    from worker import process_video  # import the task function

    job = q.enqueue(process_video, media_url, job_id, job_id=job_id)

    return jsonify({"job_id": job.get_id(), "status": "queued"})

# Check job status
@app.route("/status/<job_id>", methods=["GET"])
def status(job_id):
    from rq.job import Job

    try:
        job = Job.fetch(job_id, connection=conn)
    except Exception:
        return jsonify({"error": "Job not found"}), 404

    if job.is_finished:
        return jsonify({"status": "completed", "result": job.result})
    elif job.is_failed:
        return jsonify({"status": "failed", "error": str(job.exc_info)})
    else:
        return jsonify({"status": job.get_status()})
