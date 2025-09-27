import os
import glob
import subprocess
from flask import Flask, request, jsonify, send_from_directory

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
        # Clean old files
        for f in glob.glob(os.path.join(OUTPUT_DIR, "*")):
            os.remove(f)

        # Step 1: Download with yt-dlp
        output_path = os.path.join(OUTPUT_DIR, "input.%(ext)s")
        result = subprocess.run(
            ["yt-dlp", "-f", "bestaudio", "-o", output_path, url],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return jsonify({
                "error": "yt-dlp failed",
                "stdout": result.stdout,
                "stderr": result.stderr
            }), 500

        # Step 2: Find downloaded file
        downloaded_files = glob.glob(os.path.join(OUTPUT_DIR, "input.*"))
        if not downloaded_files:
            return jsonify({"error": "No file downloaded"}), 500
        input_file = downloaded_files[0]

        # Step 3: Convert to MP3
        output_file = os.path.join(OUTPUT_DIR, "output.mp3")
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", input_file, output_file],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return jsonify({
                "error": "ffmpeg failed",
                "stdout": result.stdout,
                "stderr": result.stderr
            }), 500

        return jsonify({
            "message": "Processing complete",
            "input_file": os.path.basename(input_file),
            "output_file": os.path.basename(output_file),
            "download_url": f"/download/{os.path.basename(output_file)}"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/download/<filename>", methods=["GET"])
def download(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)
