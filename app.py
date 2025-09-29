import os
import uuid
import json
import shutil
import traceback
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, abort
from redis import Redis
from rq import Queue, get_current_job
from tasks import process_job

# Config from env
REDIS_URL = os.environ.get("REDIS_URL", "")
FFMPEG_API_KEY = os.environ.get("FFMPEG_API_KEY", "")
ALLOW_NO_APIKEY = os.environ.get("ALLOW_NO_APIKEY", "true").lower() in ("1", "true", "yes")

if not REDIS_URL:
    # For local dev a fallback:
    REDIS_URL = os.environ.get("RQ_REDIS_URL", "redis://localhost:6379/0")

redis_conn = Redis.from_url(REDIS_URL)
q = Queue(connection=redis_conn)

app = Flask(__name__)
ROOT = Path(__file__).parent.resolve()
OUT_DIR = ROOT / "outputs"
OUT_DIR.mkdir(exist_ok=True)


def check_api_key(req):
    if not FFMPEG_API_KEY:
        return ALLOW_NO_APIKEY
    header_key = req.headers.get("X-API-Key") or req.headers.get("x-api-key")
    return header_key == FFMPEG_API_KEY


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/process", methods=["POST"])
def process():
    try:
        if not check_api_key(request):
            return jsonify({"error": "Missing or invalid API key"}), 401

        data = request.get_json(force=True)
        media_url = data.get("media_url") or data.get("url") or data.get("input")
        options = data.get("options", {})
        if not media_url:
            return jsonify({"error": "media_url is required"}), 400

        job_id = str(uuid.uuid4())
        workdir = OUT_DIR / job_id
        workdir.mkdir(parents=True, exist_ok=True)

        # enqueue background job
        rq_job = q.enqueue(process_job, job_id, media_url, options, result_ttl=3600 * 24)

        # respond in async (queued) format — support both snake_case and camelCase
        resp = {"job_id": rq_job.get_id(), "status": "queued"}
        return jsonify(resp), 202

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "Processing failed", "detail": str(e)}), 500


@app.route("/info", methods=["POST"])
def info():
    """
    FFmpeg /info compatibility endpoint (POST { job_id })
    Returns job status and, if completed, download URLs
    """
    try:
        if not check_api_key(request):
            return jsonify({"error": "Missing or invalid API key"}), 401

        payload = request.get_json(force=True)
        # accept job_id or jobId
        job_id = payload.get("job_id") or payload.get("jobId")
        if not job_id:
            return jsonify({"error": "job_id required"}), 400

        # check RQ job
        from rq.job import Job
        try:
            job = Job.fetch(job_id, connection=redis_conn)
        except Exception:
            return jsonify({"code": 1, "message": "Job not found"}), 404

        if job.is_finished:
            meta = job.meta or {}
            # gather files
            outdir = OUT_DIR / job_id
            clips = []
            thumbs = []
            if outdir.exists():
                for f in sorted(outdir.iterdir()):
                    name = f.name
                    if name.endswith("_clip.mp4"):
                        clips.append(request.host_url.rstrip("/") + "/download/" + job_id + "_" + name)
                    if name.endswith("_thumb.jpg") or name.endswith("_thumb.png"):
                        thumbs.append(request.host_url.rstrip("/") + "/download/" + job_id + "_" + name)

            resp = {
                "code": 0,
                "data": {
                    "status": "completed",
                    "clips": clips,
                    "thumbnails": thumbs,
                    "metadata": meta.get("options", {})
                }
            }
            return jsonify(resp), 200

        if job.is_failed:
            return jsonify({"code": 2, "message": "failed", "error": str(job.exc_info or "")}), 200

        # queued or started
        progress = job.meta.get("progress", 0) if job.meta else 0
        stage = job.meta.get("stage", "queued") if job.meta else "queued"
        return jsonify({"code": 0, "data": {"status": "processing", "stage": stage, "progress": progress}}), 202

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "info failed", "detail": str(e)}), 500


@app.route("/status/<job_id>", methods=["GET"])
def status(job_id):
    # helper endpoint for Lovable polling of our own DB-style status
    from rq.job import Job
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception:
        return jsonify({"error": "Job not found"}), 404

    if job.is_finished:
        return jsonify({"status": "completed", "download_urls": [request.host_url.rstrip("/") + "/download/" + job_id + "_" + p.name for p in (OUT_DIR / job_id).glob("*")]}), 200
    if job.is_failed:
        return jsonify({"status": "failed", "error": str(job.exc_info)}), 200
    return jsonify({"status": "processing", "meta": job.meta}), 200


@app.route("/download/<path:filename>", methods=["GET"])
def download(filename):
    """
    Serve files created under outputs/.
    We prefix files with job id when writing them, so path like <jobid>_<file>.
    """
    # prevent path traversal
    safe = Path(filename).name
    # Search outputs for filename (return the first match)
    for root, dirs, files in os.walk(str(OUT_DIR)):
        if safe in files:
            return send_from_directory(root, safe, as_attachment=True)
    abort(404, description="File not found")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
