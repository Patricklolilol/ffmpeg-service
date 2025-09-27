import os
import subprocess

def process_video(job_id, media_url, output_dir):
    try:
        input_path = os.path.join(output_dir, f"{job_id}.mp4")
        output_path = os.path.join(output_dir, f"{job_id}_clip.mp4")

        # Download video
        result = subprocess.run(
            ["yt-dlp", "-f", "mp4", "-o", input_path, media_url],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Download failed: {result.stderr}")

        # Cut a 30s clip (placeholder until smart clipping)
        result = subprocess.run(
            ["ffmpeg", "-y", "-ss", "00:00:00", "-i", input_path,
             "-t", "30", "-c", "copy", output_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed: {result.stderr}")

        return os.path.basename(output_path)

    except Exception as e:
        raise RuntimeError(str(e))
