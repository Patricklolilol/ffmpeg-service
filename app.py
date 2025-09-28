import os
import uuid
import json
from flask import Flask, request, jsonify, send_from_directory
import redis
from rq import Queue
from rq.job import Job

# Worker tasks live in tasks.py (same repo)
import tasks

app = Flask(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
redis_conn = redis.from_url(REDIS_URL)
q = Queue("default", connection=redis_conn)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/process", methods=["POST"])
def process():
    payload = request.get_json() or {}
    media_url = payload.get("media_url")
    if not media_url:
        return jsonify({"error": "media_url required"}), 400
    opts = payload.get("options", {})

    job_id = str(uuid.uuid4())
    # enqueue the job (tasks.process_media will run in worker)
    job = q.enqueue("tasks.process_media", media_url, job_id, opts, job_id=job_id, result_ttl=60*60*24)

    return jsonify({"job_id": job.get_id(), "status": "queued"}), 202


@app.route("/status/<job_id>", methods=["GET"])
def status(job_id):
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception:
        return jsonify({"error": "Job not found"}), 404

    resp = {
        "id": job.get_id(),
        "status": job.get_status(),
        "result": job.result,
        "meta": job.meta,
    }

    # if job finished and produced a file path in result, return download_url
    if job.is_finished and job.result and isinstance(job.result, dict):
        out = job.result.get("output_file")
        if out:
            resp["download_url"] = f"/download/{os.path.basename(out)}"

    # if failed show error message
    if job.is_failed:
        resp["error"] = str(job.exc_info)

    return jsonify(resp)


@app.route("/download/<path:filename>", methods=["GET"])
def download(filename):
    # outputs are stored in outputs/ subfolder
    outputs_dir = os.path.join(os.getcwd(), "outputs")
    if not os.path.exists(os.path.join(outputs_dir, filename)):
        return jsonify({"error": "file not found"}), 404
    return send_from_directory(outputs_dir, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
