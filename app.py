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
        # Download full video + audio as MP4
        input_path = os.path.join(OUTPUTS_DIR, "input.%(ext)s")
        subprocess.run(
            [
                "yt-dlp",
                "-f", "bestvideo+bestaudio",
                "--merge-output-format", "mp4",
                "-o", input_path,
                media_url,
            ],
            check=True,
        )

        # Ensure consistent output file name
        input_file = "input.mp4"
        input_fullpath = os.path.join(OUTPUTS_DIR, input_file)
        output_file = "output.mp4"
        output_fullpath = os.path.join(OUTPUTS_DIR, output_file)

        # Convert or re-encode to guarantee playable mp4
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", input_fullpath,
                "-c:v", "libx264",
                "-c:a", "aac",
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
