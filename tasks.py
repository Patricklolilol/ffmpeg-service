import os
import subprocess
import glob
import json
import traceback
from typing import List

# for face detection
try:
    import cv2
    OPENCV_AVAILABLE = True
except Exception:
    OPENCV_AVAILABLE = False

# optional: faster-whisper (only if installed)
try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except Exception:
    FASTER_WHISPER_AVAILABLE = False

OUTPUT_DIR = os.path.join(os.getcwd(), "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def run_cmd(cmd, timeout=None):
    """Run a shell command (list form) and raise CalledProcessError on failure."""
    print("RUN:", " ".join(cmd))
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    if proc.returncode != 0:
        print("STDOUT:", proc.stdout)
        print("STDERR:", proc.stderr)
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=proc.stdout, stderr=proc.stderr)
    return proc.stdout


def download_media(media_url: str, job_id: str) -> str:
    """
    Download best video+audio as mp4 (yt-dlp tries to give us a file).
    Returns path to downloaded file (or raises).
    """
    # download to outputs/<job_id>.%(ext)s
    out_template = os.path.join(OUTPUT_DIR, f"{job_id}.%(ext)s")
    cmd = ["yt-dlp", "-f", "best[ext=mp4]/best", "-o", out_template, media_url]
    run_cmd(cmd, timeout=300)  # may take time
    # find file produced
    patterns = glob.glob(os.path.join(OUTPUT_DIR, f"{job_id}.*"))
    if not patterns:
        raise RuntimeError("Download did not produce file")
    # prefer mp4 if present
    for p in patterns:
        if p.lower().endswith(".mp4"):
            return p
    return patterns[0]


def ensure_mp4(input_path: str, job_id: str) -> str:
    """Re-encode to a friendly mp4 for ffmpeg operations (libx264/aac)."""
    out = os.path.join(OUTPUT_DIR, f"{job_id}.mp4")
    if os.path.exists(out):
        return out
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-movflags", "+faststart",
        out
    ]
    run_cmd(cmd, timeout=600)
    return out


def make_clip(input_mp4: str, start_sec: float, duration: float, out_path: str):
    cmd = ["ffmpeg", "-y", "-ss", f"{start_sec:.3f}", "-i", input_mp4, "-t", f"{duration:.3f}",
           "-c", "copy", out_path]
    # if copy fails (timestamp / codec issues) fallback to reencode
    try:
        run_cmd(cmd, timeout=120)
    except Exception:
        cmd2 = ["ffmpeg", "-y", "-ss", f"{start_sec:.3f}", "-i", input_mp4, "-t", f"{duration:.3f}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", out_path]
        run_cmd(cmd2, timeout=300)


def detect_face_timestamps(video_path: str, sample_rate_sec: float = 1.0) -> List[float]:
    """
    Naive face detector: sample frames every sample_rate_sec and return timestamps where
    at least one face is detected. Requires OpenCV to be installed.
    """
    if not OPENCV_AVAILABLE:
        return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = total_frames / fps if fps else 0

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)

    timestamps = []
    t = 0.0
    while t < duration:
        frame_idx = int(t * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            t += sample_rate_sec
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        if len(faces) > 0:
            timestamps.append(t)
        t += sample_rate_sec
    cap.release()
    # deduplicate close timestamps
    merged = []
    for ts in timestamps:
        if not merged or ts - merged[-1] > 3.0:
            merged.append(ts)
    return merged


def transcribe_with_faster_whisper(mp4_path: str) -> List[dict]:
    """
    Use faster-whisper if installed. Returns list of segments with start, end, text.
    If faster-whisper is not available, returns [].
    """
    if not FASTER_WHISPER_AVAILABLE:
        return []
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, info = model.transcribe(mp4_path, beam_size=5)
    results = []
    for seg in segments:
        results.append({"start": seg.start, "end": seg.end, "text": seg.text})
    return results


def write_srt(segments, srt_path):
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            start = seg["start"]
            end = seg["end"]
            def fmt_time(t):
                h = int(t // 3600)
                m = int((t % 3600) // 60)
                s = int(t % 60)
                ms = int((t - int(t)) * 1000)
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
            f.write(f"{i}\n{fmt_time(start)} --> {fmt_time(end)}\n{seg['text']}\n\n")


def burn_subtitles_into_video(input_mp4: str, srt_path: str, out_path: str):
    # ffmpeg subtitles filter expects a path; fonts are provided by 'fonts-dejavu-core' installed in Dockerfile
    cmd = ["ffmpeg", "-y", "-i", input_mp4, "-vf", f"subtitles={srt_path}", "-c:a", "copy", out_path]
    try:
        run_cmd(cmd, timeout=300)
    except Exception:
        # fallback: re-encode
        cmd2 = ["ffmpeg", "-y", "-i", input_mp4, "-vf", f"subtitles={srt_path}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", out_path]
        run_cmd(cmd2, timeout=600)


def process_media(media_url: str, job_id: str, options: dict):
    """
    Main job function run by RQ worker.
    Returns a dict with output_file or raises on error.
    """
    try:
        downloaded = download_media(media_url, job_id)
        mp4 = ensure_mp4(downloaded, job_id)

        # Basic clip: make a short clip at start as a fallback
        clip_path = os.path.join(OUTPUT_DIR, f"{job_id}_clip.mp4")
        make_clip(mp4, start_sec=0.0, duration=30.0, out_path=clip_path)

        # Face-based highlights (naive): detect timestamps and produce small clips
        face_ts = detect_face_timestamps(mp4, sample_rate_sec=1.0)
        highlight_paths = []
        for idx, t in enumerate(face_ts[:5]):  # cap to first 5 highlights
            start = max(0.0, t - 2.0)
            outp = os.path.join(OUTPUT_DIR, f"{job_id}_face_{idx}.mp4")
            make_clip(mp4, start_sec=start, duration=8.0, out_path=outp)
            highlight_paths.append(outp)

        # Transcription (if available)
        segments = transcribe_with_faster_whisper(mp4)
        if segments:
            srt_path = os.path.join(OUTPUT_DIR, f"{job_id}.srt")
            write_srt(segments, srt_path)
            subtitled_out = os.path.join(OUTPUT_DIR, f"{job_id}_subtitled.mp4")
            burn_subtitles_into_video(clip_path, srt_path, subtitled_out)
            result_file = subtitled_out
        else:
            result_file = clip_path

        # Return a structured result
        return {"output_file": result_file, "highlights": highlight_paths, "transcript_segments": segments}
    except Exception as e:
        # bubble up error so job.is_failed is True and contains exception info
        traceback.print_exc()
        raise
