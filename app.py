import os
import uuid
import subprocess
from flask import Flask, request, jsonify, send_from_directory
from threading import Thread

app = Flask(__name__)

# store job info in memory (later we can move to Redis/db)
jobs = {}

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def process_video(job_id, media_url):
    try:
        input_file = os.path.join(OUTPUT_DIR, f"{job_id}.mp4")
        clip_file = os.path.join(OUTPUT_DIR, f"{job_id}_clip.mp4")

        # Step 1: Download video
        jobs[job_id]["status"] = "downloading"
        cmd_dl = ["yt-dlp", "-f", "bestvideo+bestaudio", "-o", input_file, media_url]
        subprocess.run(cmd_dl, check=True)

        # Step 2: Clip first 30s without re-encoding
        jobs[job_id]["status"] = "processing"
        cmd_clip = [
            "ffmpeg",
            "-ss", "00:00:00",
            "-i", input_file,
            "-t", "30",
            "-c", "copy",      # no re-encode, just cut
            clip_file
        ]
        subprocess.run(cmd_clip, check=True)

        # Success
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["download_url"] = f"/download/{job_id}_clip.mp4"

    except subprocess.CalledProcessError as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/process", methods=["POST"])
def process():
    data = request.json
    media_url = data.get("media_url")

    if not media_url:
        return jsonify({"error": "Missing media_url"}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued"}

    thread = Thread(target=process_video, args=(job_id, media_url))
    thread.start()

    return jsonify({"job_id": job_id, "status": "queued"})


@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/download/<path:filename>")
def download(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
