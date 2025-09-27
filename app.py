import os
import subprocess
import uuid
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def download_youtube_video(url: str, output_path: str) -> bool:
    """Download YouTube video with yt-dlp."""
    try:
        subprocess.run(
            ["yt-dlp", "-f", "best[ext=mp4]", "-o", output_path, url],
            check=True
        )
        return True
    except subprocess.CalledProcessError:
        return False

def process_video(input_path: str, output_path: str) -> bool:
    """Use ffmpeg to process video (trim first 30s)."""
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", input_path,
                "-t", "30",  # trim to first 30s
                "-c:v", "libx264",
                "-c:a", "aac",
                output_path
            ],
            check=True
        )
        return True
    except subprocess.CalledProcessError:
        return False

@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    if not data or "media_url" not in data:
        return jsonify({"code": 400, "msg": "Missing media_url"}), 400

    media_url = data["media_url"]
    job_id = str(uuid.uuid4())

    input_path = os.path.join(OUTPUT_DIR, f"{job_id}_input.mp4")
    output_path = os.path.join(OUTPUT_DIR, f"{job_id}_output.mp4")

    # Step 1: Download
    if not download_youtube_video(media_url, input_path):
        return jsonify({"code": 400, "msg": "Failed to download YouTube video"}), 400

    # Step 2: Process
    if not process_video(input_path, output_path):
        return jsonify({"code": 500, "msg": "FFmpeg processing failed"}), 500

    # Step 3: Return result
    return jsonify({
        "code": 0,
        "msg": "Success",
        "data": {
            "job_id": job_id,
            "clip_url": f"/outputs/{job_id}_output.mp4"
        }
    }), 200

@app.route("/outputs/<path:filename>")
def serve_output(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
