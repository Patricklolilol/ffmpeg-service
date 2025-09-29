import os, uuid, json
from flask import Flask, request, jsonify, send_from_directory, abort

from redis import Redis
from rq import Queue

app = Flask(__name__)
OUTPUT_DIR = os.path.join(os.getcwd(), "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

REDIS_URL = os.getenv("REDIS_URL")
redis_conn = None
queue = None
if REDIS_URL:
    redis_conn = Redis.from_url(REDIS_URL)
    queue = Queue("default", connection=redis_conn)


def write_info(job_id: str, info: dict):
    path = os.path.join(OUTPUT_DIR, f"{job_id}.json")
    with open(path, "w") as f:
        json.dump(info, f)


def read_info(job_id: str):
    path = os.path.join(OUTPUT_DIR, f"{job_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/process", methods=["POST"])
def process():
    body = request.get_json(silent=True) or {}
    media_url = body.get("media_url")
    if not media_url:
        return jsonify({"error": "media_url required"}), 400

    job_id = str(uuid.uuid4())
    info = {
        "job_id": job_id,
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "media_url": media_url
    }
    write_info(job_id, info)

    if queue is None:
        return jsonify({"error": "Redis not configured on server"}), 500

    # enqueue the worker task (worker imports tasks.process_media)
    queue.enqueue("tasks.process_media", job_id, media_url, job_timeout=3600)

    return jsonify({"job_id": job_id, "status": "queued"}), 202


@app.route("/info", methods=["POST", "GET"])
def info():
    # Accept POST { job_id } or GET ?job_id=
    body = request.get_json(silent=True) or {}
    job_id = body.get("job_id") or request.args.get("job_id")
    if not job_id:
        return jsonify({"error": "job_id required"}), 400

    info = read_info(job_id)
    if info is None:
        return jsonify({"code": 1, "message": "job not found"}), 404

    # Build response according to the shape ClipMaster/Lovable expects:
    resp_data = {
        "progress": info.get("progress", 0),
        "stage": info.get("stage"),
        "status": info.get("status"),
    }

    # attach conversion and screenshots if present, make absolute URLs
    host = request.host_url.rstrip("/")
    if info.get("conversion") and info["conversion"].get("file"):
        resp_data["conversion"] = {
            "url": f"{host}/download/{info['conversion']['file']}",
            "file": info["conversion"]["file"]
        }
    if info.get("screenshots"):
        s_list = []
        for fname in info["screenshots"]:
            s_list.append({"url": f"{host}/download/{fname}", "file": fname})
        resp_data["screenshots"] = s_list

    # use code 0 to indicate the service responded successfully
    response_body = {"code": 0, "data": resp_data}
    # Use 200 when processing/completed, 202 otherwise (keeps compatibility)
    status_code = 200 if info.get("status") in ("processing", "completed") else 202
    return jsonify(response_body), status_code


@app.route("/download/<path:filename>")
def download(filename):
    # safe-serving file from outputs
    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        return abort(404)
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
