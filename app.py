import os
import uuid
from flask import Flask, request, jsonify
from redis import Redis
from rq import Queue
from worker import process_media

app = Flask(__name__)

# Redis connection
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_conn = Redis.from_url(redis_url)
q = Queue(connection=redis_conn)

# Ensure outputs dir exists
os.makedirs("outputs", exist_ok=True)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/process", methods=["POST"])
def process():
    try:
        data = request.get_json()
        media_url = data.get("media_url")
        if not media_url:
            return jsonify({"error": "Missing media_url"}), 400

        job_id = str(uuid.uuid4())
        job = q.enqueue(process_media, media_url, job_id, job_timeout="15m")

        return jsonify({"job_id": job.get_id(), "status": "queued"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/status/<job_id>")
def status(job_id):
    try:
        job = q.fetch_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404

        if job.is_finished:
            return jsonify({"status": "completed", "result": job.result})
        elif job.is_failed:
            return jsonify({"status": "failed", "error": str(job.exc_info)})
        else:
            return jsonify({"status": job.get_status()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
