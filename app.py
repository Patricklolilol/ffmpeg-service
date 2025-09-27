import os
import uuid
import redis
from rq import Queue
from flask import Flask, request, jsonify, send_from_directory
from worker import process_video

app = Flask(__name__)

# Redis connection (Railway provides REDIS_URL)
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
conn = redis.from_url(redis_url)
q = Queue(connection=conn)

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    media_url = data.get("media_url")
    if not media_url:
        return jsonify({"error": "media_url is required"}), 400

    job_id = str(uuid.uuid4())
    job = q.enqueue(process_video, job_id, media_url, OUTPUT_DIR, job_id=job_id)

    return jsonify({"job_id": job.get_id(), "status": "queued"})


@app.route("/status/<job_id>", methods=["GET"])
def status(job_id):
    job = q.fetch_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    if job.is_failed:
        return jsonify({"status": "failed", "error": str(job.exc_info)})

    if job.is_finished:
        return jsonify({"status": "completed", "download_url": f"/download/{job.result}"})

    return jsonify({"status": job.get_status()})


@app.route("/download/<path:filename>", methods=["GET"])
def download(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
