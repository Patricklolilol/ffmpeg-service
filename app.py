from flask import Flask, request, jsonify, send_from_directory
from redis import Redis
from rq import Queue
import os
import uuid
from tasks import process_media

app = Flask(__name__)

# Redis connection
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_conn = Redis.from_url(redis_url)
q = Queue("default", connection=redis_conn)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    media_url = data.get("media_url")

    if not media_url:
        return jsonify({"error": "Missing media_url"}), 400

    job_id = str(uuid.uuid4())
    job = q.enqueue(process_media, media_url, job_id, job_id=job_id)

    return jsonify({"job_id": job.get_id(), "status": "queued"})

@app.route("/status/<job_id>", methods=["GET"])
def status(job_id):
    from rq.job import Job
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except:
        return jsonify({"error": "Job not found"}), 404

    if job.is_finished:
        return jsonify({"status": "completed", "download_url": f"/download/{job_id}_clip.mp4"})
    elif job.is_failed:
        return jsonify({"status": "failed", "error": str(job.exc_info)})
    else:
        return jsonify({"status": job.get_status()})

@app.route("/download/<path:filename>")
def download(filename):
    return send_from_directory("outputs", filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
