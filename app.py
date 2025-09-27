import os
import uuid
import subprocess
import threading
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)
OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Store jobs in memory
jobs = {}

def run_job(job_id, media_url):
    try:
        jobs[job_id]["status"] = "downloading"

        # Download video with yt-dlp
        input_file = os.path.join(OUTPUT_DIR, f"{job_id}.mp4")
        download_cmd = [
            "yt-dlp", "-f", "bestvideo+bestaudio/best",
            "-o", input_file, media_url
        ]

        result = subprocess.run(download_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = f"Download failed: {result.stderr}"
            return

        if not os.path.exists(input_file):
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = "Download did not produce file"
            return

        jobs[job_id]["status"] = "processing"

        # Clip first 30s
        output_file = os.path.join(OUTPUT_DIR, f"{job_id}_clip.mp4")
        clip_cmd = [
            "ffmpeg", "-y", "-ss", "00:00:00",
            "-i", input_file, "-t", "30",
            "-c:v", "libx264", "-c:a", "aac",
            output_file
        ]

        result = subprocess.run(clip_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = f"FFmpeg failed: {result.stderr}"
            return

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["download_url"] = f"/download/{os.path.basename(output_file)}"

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    media_url = data.get("media_url")
    if not media_url:
        return jsonify({"error": "Missing media_url"}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued"}

    thread = threading.Thread(target=run_job, args=(job_id, media_url))
    thread.start()

    return jsonify({"job_id": job_id, "status": "queued"})


@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/download/<filename>")
def download(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
