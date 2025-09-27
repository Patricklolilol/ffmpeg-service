import os
import subprocess
import uuid

def process_media(media_url, job_id):
    os.makedirs("outputs", exist_ok=True)

    input_file = f"outputs/{job_id}.%(ext)s"
    output_file = f"outputs/{job_id}_clip.mp4"

    try:
        # Step 1: Download with yt-dlp
        subprocess.run(
            ["yt-dlp", "-f", "best", "-o", input_file, media_url],
            check=True
        )

        # Find the downloaded file (yt-dlp replaces %(ext)s)
        for f in os.listdir("outputs"):
            if f.startswith(job_id):
                downloaded = os.path.join("outputs", f)
                break
        else:
            raise Exception("Download did not produce file")

        # Step 2: Clip with ffmpeg (first 30s as example)
        subprocess.run(
            [
                "ffmpeg", "-y", "-ss", "00:00:00",
                "-i", downloaded, "-t", "30",
                "-c:v", "libx264", "-c:a", "aac",
                output_file
            ],
            check=True
        )

        return {"download_url": f"/download/{os.path.basename(output_file)}"}

    except subprocess.CalledProcessError as e:
        raise Exception(f"Command failed: {e}")
