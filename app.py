import os
import uuid
from flask import Flask, request, jsonify
import redis
from rq import Queue
from rq.job import Job

app = Flask(__name__)

# Connect to Redis (Railway provides REDIS_URL automatically)
redis_url = os.getenv("REDIS_URL")
redis_conn = redis.from_url(redis_url)
q = Queue(connection=redis_conn)


# Background job function (defined in worker.py, imported dynamically)
def enqueue_job(media_url):
    job_id = str(uuid.uuid4())
    q.enqueue("worker.process_video", media_url, job_id, job_id=job_id)
    return job_id


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    media_url = data.get("media_url")

    if not media_url:
        return jsonify({"error": "Missing media_url"}), 400

    job_id = enqueue_job(media_url)
    return jsonify({"job_id": job_id, "status": "queued"})


@app.route("/status/<job_id>")
def status(job_id):
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception:
        return jsonify({"error": "Job not found"}), 404

    if job.is_failed:
        return jsonify({"status": "failed", "error": str(job.exc_info)})
    elif job.is_finished:
        return jsonify({"status": "completed", "download_url": f"/download/{job_id}_clip.mp4"})
    else:
        return jsonify({"status": job.get_status()})


@app.route("/download/<filename>")
def download(filename):
    file_path = os.path.join("outputs", filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    return app.send_static_file(file_path)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
