import os
import subprocess

def process_media(media_url, job_id):
    os.makedirs("outputs", exist_ok=True)

    input_template = f"outputs/{job_id}.%(ext)s"
    output_file = f"outputs/{job_id}_clip.mp4"

    try:
        # Step 1: Download video
        result = subprocess.run(
            ["yt-dlp", "-f", "best", "-o", input_template, media_url],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise Exception(f"yt-dlp failed: {result.stderr}")

        # Find downloaded file
        downloaded = None
        for f in os.listdir("outputs"):
            if f.startswith(job_id) and not f.endswith("_clip.mp4"):
                downloaded = os.path.join("outputs", f)
                break
        if not downloaded:
            raise Exception("Download did not produce a file")

        # Step 2: Process with ffmpeg (first 30s clip for now)
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-ss", "00:00:00", "-i", downloaded,
                "-t", "30", "-c:v", "libx264", "-c:a", "aac", output_file
            ],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise Exception(f"ffmpeg failed: {result.stderr}")

        return {"download_url": f"/download/{os.path.basename(output_file)}"}

    except Exception as e:
        raise Exception(f"Processing failed: {e}")
