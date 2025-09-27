import os
import subprocess

def process_video(media_url, job_id):
    """
    Downloads a video from YouTube, clips first 30s, saves it.
    """
    os.makedirs("outputs", exist_ok=True)
    input_path = f"outputs/{job_id}.mp4"
    output_path = f"outputs/{job_id}_clip.mp4"

    # 1. Download with yt-dlp
    cmd_dl = ["yt-dlp", "-f", "best", "-o", input_path, media_url]
    subprocess.run(cmd_dl, check=True)

    # 2. Clip with ffmpeg
    cmd_ffmpeg = ["ffmpeg", "-y", "-ss", "00:00:00", "-i", input_path, "-t", "30", "-c", "copy", output_path]
    subprocess.run(cmd_ffmpeg, check=True)

    return output_path
