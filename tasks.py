import subprocess
import os

OUTPUTS_DIR = "outputs"
os.makedirs(OUTPUTS_DIR, exist_ok=True)

def process_media(media_url, job_id):
    input_file = f"{OUTPUTS_DIR}/{job_id}.mp4"
    output_file = f"{OUTPUTS_DIR}/{job_id}_clip.mp4"

    # Step 1: Download media with yt-dlp
    download_cmd = [
        "yt-dlp", "-f", "bestvideo+bestaudio/best",
        "-o", input_file, media_url
    ]
    subprocess.run(download_cmd, check=True)

    if not os.path.exists(input_file):
        raise Exception("Download failed")

    # Step 2: Clip first 30s with ffmpeg
    clip_cmd = [
        "ffmpeg", "-ss", "00:00:00", "-i", input_file,
        "-t", "30", "-c", "copy", output_file, "-y"
    ]
    subprocess.run(clip_cmd, check=True)

    if not os.path.exists(output_file):
        raise Exception("Processing failed")

    return {"output_file": output_file}
