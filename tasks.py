import os, json, subprocess
from yt_dlp import YoutubeDL
from rq import get_current_job  # <-- NEW

OUTPUT_DIR = os.path.join(os.getcwd(), "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def write_info(job_id: str, info: dict):
    path = os.path.join(OUTPUT_DIR, f"{job_id}.json")
    with open(path, "w") as f:
        json.dump(info, f)

    # also update Redis metadata so /info can read it
    job = get_current_job()
    if job:
        job.meta.update(info)
        job.save_meta()


def find_downloaded_file(job_id: str):
    for f in os.listdir(OUTPUT_DIR):
        if f.startswith(job_id) and not f.endswith(".json"):
            return f
    return None


def process_media(job_id: str, media_url: str):
    """
    Worker function executed by RQ. Steps:
     - Download via yt-dlp to outputs/jobid.ext
     - Make a thumbnail
     - Make a 30s clip (fallback to re-encode if copy fails)
     - Update outputs/jobid.json AND job.meta with progress/stage/status
    """
    info = {"job_id": job_id, "status": "processing", "stage": "downloading", "progress": 0}
    write_info(job_id, info)

    out_template = os.path.join(OUTPUT_DIR, f"{job_id}.%(ext)s")
    ydl_opts = {"format": "best", "outtmpl": out_template, "quiet": True}

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([media_url])
    except Exception as e:
        info.update({"status": "failed", "stage": "download_failed", "error": str(e)})
        write_info(job_id, info)
        raise

    downloaded = find_downloaded_file(job_id)
    if not downloaded:
        info.update({"status": "failed", "stage": "no_downloaded_file", "error": "no file found"})
        write_info(job_id, info)
        raise FileNotFoundError("No downloaded file found")

    input_path = os.path.join(OUTPUT_DIR, downloaded)

    # thumbnail
    info.update({"progress": 40, "stage": "creating_thumbnail"})
    write_info(job_id, info)
    thumb_fname = f"{job_id}_thumb1.jpg"
    thumb_path = os.path.join(OUTPUT_DIR, thumb_fname)
    try:
        subprocess.check_call(["ffmpeg", "-y", "-i", input_path, "-ss", "00:00:01", "-vframes", "1", thumb_path])
    except Exception as e:
        info.update({"status": "failed", "stage": "thumbnail_failed", "error": str(e)})
        write_info(job_id, info)
        raise

    # clip (first 30s) - try stream copy first
    info.update({"progress": 70, "stage": "creating_clip"})
    write_info(job_id, info)
    clip_fname = f"{job_id}_clip.mp4"
    clip_path = os.path.join(OUTPUT_DIR, clip_fname)
    try:
        subprocess.check_call(["ffmpeg", "-y", "-ss", "00:00:00", "-i", input_path, "-t", "30", "-c", "copy", clip_path])
    except Exception:
        # fallback to re-encode if copy didn't work
        try:
            subprocess.check_call([
                "ffmpeg", "-y", "-ss", "00:00:00", "-i", input_path, "-t", "30",
                "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-b:a", "128k", clip_path
            ])
        except Exception as e:
            info.update({"status": "failed", "stage": "clip_failed", "error": str(e)})
            write_info(job_id, info)
            raise

    # done
    info.update({
        "status": "completed",
        "stage": "completed",
        "progress": 100,
        "conversion": {"file": clip_fname},
        "screenshots": [thumb_fname]
    })
    write_info(job_id, info)
    return clip_fname
