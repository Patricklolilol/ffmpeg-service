import os
import subprocess
from flask import Flask, request, jsonify

app = Flask(__name__)

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    url = data.get("media_url")
    if not url:
        return jsonify({"error": "No media_url provided"}), 400

    try:
        # Step 1: Download the audio using yt-dlp
        output_path = os.path.join(OUTPUT_DIR, "input.%(ext)s")
        subprocess.run(
            ["yt-dlp", "-f", "bestaudio", "-o", output_path, url],
            check=True
        )

        # Step 2: Convert to mp3 with ffmpeg
        input_file = os.path.join(OUTPUT_DIR, "input.webm")  # yt-dlp default for audio
        output_file = os.path.join(OUTPUT_DIR, "output.mp3")

        subprocess.run(
            ["ffmpeg", "-y", "-i", input_file, output_file],
            check=True
        )

        return jsonify({"message": "Processing complete", "output_file": output_file})

    except subprocess.CalledProcessError as e:
        return jsonify({"error": f"Processing failed: {str(e)}"}), 500
