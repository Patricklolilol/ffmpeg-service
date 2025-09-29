import os
import json
import glob
import subprocess
import shlex
from pathlib import Path

import redis
from rq import Queue

import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError, ClientError

# Redis connection
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
redis_conn = redis.from_url(REDIS_URL)

# RQ queue
q = Queue("default", connection=redis_conn)

JOB_PREFIX = "job:"

# S3 / R2 config
S3_BUCKET = os.environ.get("S3_BUCKET_NAME") or os.environ.get("AWS_S3_BUCKET")  # allow either name
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL")  # eg for Cloudflare R2

# Build boto3 client (works with AWS or R2 endpoint_url override)
s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
    endpoint_url=AWS_ENDPOINT_URL if AWS_ENDPOINT_URL else None,
)


def _set_job_state(job_id: str, data: dict, ttl: int = 86400):
    """
    Save job state in Redis with TTL (default 1 day).
    """
    redis_conn.set(f"{JOB_PREFIX}{job_id}", json.dumps(data), ex=ttl)


def _get_first_downloaded(path_prefix: str):
    files = glob.glob(path_prefix + ".*")
    return files[0] if files else None


def run_cmd(cmd, timeout=None):
    """
    Run a shell command and log stdout/stderr.
    """
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)

    print(f"[RUN] {' '.join(cmd)}")
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    out = proc.stdout.decode("utf-8", errors="ignore")
    err = proc.stderr.decode("utf-8", errors="ignore")

    if out.strip():
        print(f"[STDOUT]\n{out}")
    if err.strip():
        print(f"[STDERR]\n{err}")

    return proc.returncode, out, err


def upload_to_s3(local_path: Path, s3_key: str) -> str | None:
    """
    Upload file to S3 / R2 and return a public URL (or None on failure).
    Attempts upload with ACL, then without (Cloudflare R2 doesn't support ACL).
    """
    if not S3_BUCKET:
        print("[ERROR] S3_BUCKET_NAME is not set")
        return None

    try:
        # Try with ACL first (works on AWS)
        print(f"[S3] Uploading {local_path} to s3://{S3_BUCKET}/{s3_key} (with ACL)")
        s3_client.upload_file(str(local_path), S3_BUCKET, s3_key, ExtraArgs={"ACL": "public-read"})
    except (ClientError, BotoCoreError, NoCredentialsError) as e:
        print(f"[S3] upload with ACL failed: {e}; trying without ExtraArgs ...")
        try:
            s3_client.upload_file(str(local_path), S3_BUCKET, s3_key)
        except (ClientError, BotoCoreError, NoCredentialsError) as e2:
            print(f"[S3] upload failed: {e2}")
            return None

    # Build public URL:
    if AWS_ENDPOINT_URL:
        # If custom endpoint (e.g. Cloudflare R2), endpoint_url likely includes scheme
        # Some providers require different URL shapes; this is a reasonable default.
        endpoint = AWS_ENDPOINT_URL.rstrip("/")
        return f"{endpoint}/{S3_BUCKET}/{s3_key}"
    else:
        return f"https://{S3_BUCKET}.s3.amazonaws.com/{s3_key}"


def _safe_remove(path: Path):
    try:
        path.unlink()
    except Exception as e:
        print(f"[WARN] Could not remove {path}: {e}")


def process_media(job_id: str, media_url: str, output_dir: str):
    """
    Worker task executed by RQ:
      1) download via yt-dlp
      2) transcode to mp4 (force single video+audio stream)
      3) upload to S3 (if configured)
      4) update Redis state
    """
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    _set_job_state(
        job_id,
        {"status": "downloading", "stage": "downloading", "progress": 0, "job_id": job_id},
    )

    # 1) download
    out_prefix = str(outdir / job_id)
    ytdlp_cmd = ["yt-dlp", "-f", "best", "-o", out_prefix + ".%(ext)s", media_url]
    code, _, err = run_cmd(ytdlp_cmd, timeout=300)
    if code != 0:
        _set_job_state(
            job_id,
            {"status": "failed", "stage": "download_failed", "error": err, "job_id": job_id},
        )
        return

    input_file = _get_first_downloaded(out_prefix)
    if not input_file:
        _set_job_state(
            job_id,
            {"status": "failed", "stage": "no_file", "error": "Download produced no file", "job_id": job_id},
        )
        return

    _set_job_state(
        job_id,
        {"status": "processing", "stage": "converting", "progress": 40, "job_id": job_id},
    )

    # 2) convert to mp4 (force one video + one audio stream)
    converted_mp4 = outdir / f"{job_id}_converted.mp4"
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", input_file,
        "-map", "0:v:0", "-map", "0:a:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-movflags", "+faststart",
        str(converted_mp4)
    ]
    code2, _, err2 = run_cmd(ffmpeg_cmd, timeout=900)
    if code2 != 0:
        print("[WARN] Primary conversion failed, retrying with fallback...")
        ffmpeg_cmd_fallback = [
            "ffmpeg", "-y", "-i", input_file,
            "-map", "0:v:0", "-map", "0:a:0",
            "-vf", "scale=1280:-2",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            str(converted_mp4)
        ]
        code2b, _, err2b = run_cmd(ffmpeg_cmd_fallback, timeout=900)
        if code2b != 0:
            _set_job_state(
                job_id,
                {"status": "failed", "stage": "convert_failed", "error": f"{err2}; fallback: {err2b}", "job_id": job_id},
            )
            return

    # 3) upload to S3 if bucket configured
    output_url = None
    if S3_BUCKET:
        s3_key = f"{job_id}/{converted_mp4.name}"
        output_url = upload_to_s3(converted_mp4, s3_key)
        if not output_url:
            _set_job_state(
                job_id,
                {"status": "failed", "stage": "upload_failed", "error": "S3 upload failed", "job_id": job_id},
            )
            return

    # 4) mark completed
    state = {
        "status": "completed",
        "stage": "completed",
        "progress": 100,
        "message": "Completed",
        "job_id": job_id,
        "output_file": converted_mp4.name,
    }
    if output_url:
        state["output_url"] = output_url

    _set_job_state(job_id, state)

    # 5) cleanup (optional) — remove local files to free disk, unless KEEP_OUTPUT_LOCAL is truthy
    keep_local = os.environ.get("KEEP_OUTPUT_LOCAL", "0") in ("1", "true", "True")
    try:
        if not keep_local:
            _safe_remove(Path(input_file))
            _safe_remove(converted_mp4)
    except Exception as e:
        print(f"[WARN] cleanup failed: {e}")

    return converted_mp4.name


def enqueue_job(job_id: str, media_url: str, output_dir: str = "outputs"):
    """
    Call this from app.py when receiving /process.
    Enqueues the RQ worker job and sets initial Redis state.
    """
    _set_job_state(job_id, {"status": "queued", "stage": "queued", "progress": 0, "job_id": job_id})

    return q.enqueue(
        process_media,
        job_id,
        media_url,
        output_dir,
        job_id=job_id,
        result_ttl=86400,
        ttl=86400
    )
