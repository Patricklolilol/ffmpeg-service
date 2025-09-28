import os
import subprocess
import uuid
from flask import Flask, request, jsonify

app = Flask(__name__)

os.makedirs("outputs", exist_ok=True)

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/process", methods=["POST"])
def process():
    try:
        data = request.get_json()
        media_url = data.get("media_url")
        if not media_url:
            return jsonify({"error": "Missing media_url"}), 400

        job_id = str(uuid.uuid4())
        input_path = f"outputs/{job_id}.%(ext)s"

        # Download
        cmd = ["yt-dlp", "-f", "bestaudio", "-o", input_path, media_url]
        subprocess.check_call(cmd)

        return jsonify({
            "job_id": job_id,
            "status": "queued",
            "message": "Download started"
        })
    except subprocess.CalledProcessError as e:
        return jsonify({"error": f"yt-dlp failed: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
