import os
import tempfile
import subprocess
import uuid
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def run_command(cmd):
    """Run shell command safely and capture output."""
    try:
        result = subprocess.run(
            cmd, shell=True, check=True, capture_output=True, text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return None


def download_youtube_video(url, download_dir):
    """Download YouTube video using yt-dlp."""
    try:
        filename = str(uuid.uuid4()) + ".mp4"
        filepath = os.path.join(download_dir, filename)
        cmd = f'yt-dlp -f best -o "{filepath}" "{url}"'
        success = run_command(cmd)
        if success is None or not os.path.exists(filepath):
            return None
        return filepath
    except Exception:
        return None


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json(force=True)
    media_url = data.get("media_url")

    if not media_url:
        return jsonify({"code": 400, "msg": "Missing media_url", "data": {}}), 400

    # Create temp working dir
    with tempfile.TemporaryDirectory() as tmpdir:
        local_file = None

        # Handle YouTube URLs
        if "youtube.com" in media_url or "youtu.be" in media_url:
            local_file = download_youtube_video(media_url, tmpdir)
            if not local_file:
                return jsonify(
                    {"code": 400, "msg": "Failed to download YouTube video", "data": {}}
                ), 400
        else:
            # Direct file URL (not YouTube)
            local_file = media_url

        # Generate output file path
        out_filename = str(uuid.uuid4()) + ".mp4"
        out_path = os.path.join(OUTPUT_DIR, out_filename)

        # Run ffmpeg conversion (copy video/audio stream to mp4)
        cmd = f'ffmpeg -y -i "{local_file}" -c:v libx264 -c:a aac "{out_path}"'
        success = run_command(cmd)

        if success is None or not os.path.exists(out_path):
            return jsonify(
                {"code": 500, "msg": "FFmpeg processing failed", "data": {}}
            ), 500

        return jsonify(
            {
                "code": 0,
                "msg": "Processing complete",
                "data": {
                    "video": f"/output/{out_filename}",
                },
            }
        )


@app.route("/output/<path:filename>")
def serve_output(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
