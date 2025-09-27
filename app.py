import os
import uuid
import threading
import subprocess
from flask import Flask, request, jsonify, send_from_directory
import yt_dlp
from faster_whisper import WhisperModel

app = Flask(__name__)

# Storage
jobs = {}
OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load Whisper once (fast + accurate enough)
model = WhisperModel("small", device="cpu", compute_type="int8")


def download_and_process(job_id, media_url):
    try:
        jobs[job_id]["status"] = "downloading"
        video_path = os.path.join(OUTPUT_DIR, f"{job_id}.mp4")

        # Download video
        ydl_opts = {
            "outtmpl": video_path,
            "format": "mp4/best",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([media_url])

        if not os.path.exists(video_path):
            raise Exception("Download did not produce file")

        # Cut first 30s (temporary until smart clipping)
        jobs[job_id]["status"] = "clipping"
        clip_path = os.path.join(OUTPUT_DIR, f"{job_id}_clip.mp4")
        command = [
            "ffmpeg", "-y",
            "-ss", "00:00:00",
            "-i", video_path,
            "-t", "30",
            "-c:v", "libx264",
            "-c:a", "aac",
            clip_path
        ]
        subprocess.run(command, check=True)

        # Transcribe
        jobs[job_id]["status"] = "transcribing"
        segments, info = model.transcribe(clip_path, beam_size=5)

        # Write SRT
        srt_path = os.path.join(OUTPUT_DIR, f"{job_id}.srt")
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments, start=1):
                f.write(f"{i}\n")
                f.write(f"{format_timestamp(seg.start)} --> {format_timestamp(seg.end)}\n")
                f.write(f"{seg.text.strip()}\n\n")

        # Burn captions into video
        jobs[job_id]["status"] = "rendering"
        final_path = os.path.join(OUTPUT_DIR, f"{job_id}_final.mp4")
        burn_command = [
            "ffmpeg", "-y",
            "-i", clip_path,
            "-vf", f"subtitles={srt_path}:force_style='FontName=Arial,FontSize=24,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,BorderStyle=1,Outline=2,Shadow=1'",
            "-c:a", "copy",
            final_path
        ]
        subprocess.run(burn_command, check=True)

        # Done
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["download_url"] = f"/download/{os.path.basename(final_path)}"
        jobs[job_id]["captions_url"] = f"/download/{os.path.basename(srt_path)}"

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


@app.route("/process", methods=["POST"])
def process():
    data = request.json
    media_url = data.get("media_url")
    if not media_url:
        return jsonify({"error": "Missing media_url"}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued"}

    thread = threading.Thread(target=download_and_process, args=(job_id, media_url))
    thread.start()

    return jsonify({"job_id": job_id, "status": "queued"})


@app.route("/status/<job_id>")
def status(job_id):
    return jsonify(jobs.get(job_id, {"error": "Job not found"}))


@app.route("/download/<filename>")
def download(filename):
    return send_from_directory(OUTPUT_DIR, filename)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


def format_timestamp(seconds: float):
    """Convert seconds to SRT timestamp format"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
