import os
import tempfile
import subprocess
import uuid
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def run_command(cmd):
    """Run shell command and capture output + errors."""
    try:
        result = subprocess.run(
            cmd, check=True, capture_output=True, text=True
        )
        return result.stdout.strip(), result.stderr.strip()
    except subprocess.CalledProcessError as e:
        return None, e.stderr.strip()


def download_youtube_video(url, download_dir):
    """Download YouTube video using yt-dlp and return local filepath."""
    filename = str(uuid.uuid4()) + ".mp4"
    filepath = os.path.join(download_dir, filename)

    cmd = [
        "yt-dlp",
        "-f", "mp4",
        "-o", filepath,
        url
    ]

    try:
        subprocess.run(cmd, check=True)
        if os.path.exists(filepath):
            return filepath
        else:
            return None
    except subprocess.CalledProcessError:
        return None


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json(force=True)
    media_url = data.get("media_url")

    if not media_url:
        return jsonify({"code": 400, "msg": "Missing media_url", "data": {}}), 400

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
            local_file = media_url

        # Output file
        out_filename = str(uuid.uuid4()) + ".mp4"
        out_path = os.path.join(OUTPUT_DIR, out_filename)

        # Run ffmpeg
        cmd = [
            "ffmpeg",
            "-y",
            "-i", local_file,
            "-c:v", "libx264",
            "-c:a", "aac",
            out_path
        ]
        stdout, stderr = run_command(cmd)

        if not os.path.exists(out_path):
            return jsonify(
                {"code": 500, "msg": "FFmpeg processing failed", "error": stderr, "data": {}}
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
