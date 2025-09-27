from flask import Flask, request, jsonify, send_from_directory
from redis import Redis
from rq import Queue
import os
import jobs

app = Flask(__name__)

redis_conn = Redis(host="redis", port=6379)
q = Queue(connection=redis_conn)

OUTPUT_DIR = "outputs"

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/process", methods=["POST"])
def process():
    data = request.json
    media_url = data.get("media_url")
    if not media_url:
        return jsonify({"error": "media_url required"}), 400

    job = q.enqueue(jobs.process_video, media_url)
    return jsonify({"job_id": job.id, "status": "queued"})

@app.route("/status/<job_id>")
def status(job_id):
    from rq.job import Job
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except:
        return jsonify({"error": "job not found"}), 404

    if job.is_finished:
        return jsonify({"status": "finished", "result": job.result})
    elif job.is_failed:
        return jsonify({"status": "failed", "error": str(job.exc_info)})
    else:
        return jsonify({"status": job.get_status()})

@app.route("/download/<filename>")
def download(filename):
    return send_from_directory(OUTPUT_DIR, filename)

