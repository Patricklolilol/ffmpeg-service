import subprocess
import os
import uuid
import yt_dlp

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def process_video(media_url):
    job_id = str(uuid.uuid4())
    input_file = os.path.join(OUTPUT_DIR, f"{job_id}.mp4")
    output_file = os.path.join(OUTPUT_DIR, f"{job_id}_clip.mp4")

    # Download full video
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": input_file,
        "merge_output_format": "mp4"
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([media_url])

    # Re-encode to output file
    subprocess.run([
        "ffmpeg", "-y", "-i", input_file,
        "-c:v", "libx264", "-c:a", "aac",
        output_file
    ], check=True)

    return {"job_id": job_id, "output_file": output_file}
