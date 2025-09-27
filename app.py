import os
import uuid
import threading
import subprocess
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

# In-memory job storage
JOBS = {}

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def run_job(job_id, media_url):
    """Background worker: downloads and processes video with ffmpeg."""
    try:
        input_file = os.path.join(OUTPUT_DIR, f"{job_id}.mp4")
        output_file = os.path.join(OUTPUT_DIR, f"{job_id}_clip.mp4")

        # Step 1: download video
        dl = subprocess.run(
            ["yt-dlp", "-f", "mp4", "-o", input_file, media_url],
            capture_output=True, text=True
        )
        if dl.returncode != 0:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = dl.stderr
            return

        # Step 2: simple clip (first 30s)
        ff = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", input_file,
                "-t", "30",
                "-c:v", "libx264", "-c:a", "aac",
                output_file
            ],
            capture_output=True, text=True
        )
        if ff.returncode != 0:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = ff.stderr
            return

        JOBS[job_id]["status"] = "completed"
        JOBS[job_id]["download_url"] = f"/download/{os.path.basename(output_file)}"

    except Exception as e:
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["error"] = str(e)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    media_url = data.get("media_url")
    if not media_url:
        return jsonify({"error": "media_url required"}), 400

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "processing"}

    thread = threading.Thread(target=run_job, args=(job_id, media_url))
    thread.start()

    return jsonify({"job_id": job_id, "status": "processing"})


@app.route("/status/<job_id>")
def status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify(job)


@app.route("/download/<path:filename>")
def download(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

