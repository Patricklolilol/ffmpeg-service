import os
import uuid
import threading
import subprocess
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

# Store job states in memory (later: Redis/DB for scaling)
JOBS = {}

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def run_job(job_id, media_url):
    try:
        JOBS[job_id]["status"] = "downloading"

        input_file = os.path.join(OUTPUT_DIR, f"{job_id}.mp4")
        output_file = os.path.join(OUTPUT_DIR, f"{job_id}_clip.mp4")

        # ✅ Force yt-dlp to save to a known location
        download_cmd = [
            "yt-dlp",
            "-f", "mp4",
            "-o", input_file,   # Explicit output file
            media_url,
        ]
        subprocess.run(download_cmd, check=True)

        if not os.path.exists(input_file):
            raise Exception("Download did not produce file")

        JOBS[job_id]["status"] = "processing"

        # Clip first 30s
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-ss", "00:00:00",
            "-i", input_file,
            "-t", "30",
            "-c", "copy",
            output_file,
        ]
        subprocess.run(ffmpeg_cmd, check=True)

        if not os.path.exists(output_file):
            raise Exception("Clipping failed")

        JOBS[job_id]["status"] = "completed"
        JOBS[job_id]["download_url"] = f"/download/{job_id}_clip.mp4"

    except Exception as e:
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["error"] = str(e)


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    media_url = data.get("media_url")

    if not media_url:
        return jsonify({"error": "Missing media_url"}), 400

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "queued"}

    threading.Thread(target=run_job, args=(job_id, media_url)).start()

    return jsonify({"job_id": job_id, "status": "queued"})


@app.route("/status/<job_id>", methods=["GET"])
def status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/download/<path:filename>", methods=["GET"])
def download(filename):
    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404
    return send_file(filepath, as_attachment=True)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
