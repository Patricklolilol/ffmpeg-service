import os
import subprocess
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

OUTPUTS_DIR = "outputs"
os.makedirs(OUTPUTS_DIR, exist_ok=True)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    media_url = data.get("media_url")

    if not media_url:
        return jsonify({"error": "No media_url provided"}), 400

    try:
        # Download video at <=720p
        input_path = os.path.join(OUTPUTS_DIR, "input.%(ext)s")
        subprocess.run(
            [
                "yt-dlp",
                "-f", "mp4[height<=720]+bestaudio/best[height<=720]",
                "--merge-output-format", "mp4",
                "-o", input_path,
                media_url,
            ],
            check=True,
        )

        input_file = "input.mp4"
        input_fullpath = os.path.join(OUTPUTS_DIR, input_file)
        output_file = "output.mp4"
        output_fullpath = os.path.join(OUTPUTS_DIR, output_file)

        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", input_fullpath,
                "-c:v", "libx264",
                "-c:a", "aac",
                "-preset", "ultrafast",
                output_fullpath
            ],
            check=True,
        )

        return jsonify({
            "message": "Processing complete",
            "input_file": input_file,
            "output_file": output_file,
            "download_url": f"/download/{output_file}"
        })

    except subprocess.CalledProcessError as e:
        return jsonify({"error": f"Processing failed: {str(e)}"}), 500

@app.route("/download/<path:filename>", methods=["GET"])
def download(filename):
    return send_from_directory(OUTPUTS_DIR, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
