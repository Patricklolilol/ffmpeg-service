import os
import subprocess

def process_video(media_url, job_id):
    """
    Downloads the video and creates a short clip.
    """
    input_file = f"outputs/{job_id}.mp4"
    output_file = f"outputs/{job_id}_clip.mp4"

    # Step 1: Download video
    cmd_download = ["yt-dlp", "-f", "mp4", "-o", input_file, media_url]
    subprocess.run(cmd_download, check=True)

    # Step 2: Create 30s clip
    cmd_clip = ["ffmpeg", "-y", "-ss", "00:00:00", "-i", input_file, "-t", "30", "-c", "copy", output_file]
    subprocess.run(cmd_clip, check=True)

    return {"download_url": f"/download/{job_id}_clip.mp4"}
