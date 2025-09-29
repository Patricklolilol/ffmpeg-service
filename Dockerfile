FROM python:3.10-slim

# System deps for ffmpeg, fonts (for burned captions), yt-dlp, build tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ffmpeg curl git build-essential fonts-dejavu-core libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

# Copy & install python deps
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app
COPY . .

# Ensure outputs dir exists
RUN mkdir -p /app/outputs

# Copy worker start script
COPY start_worker.sh /start_worker.sh
RUN chmod +x /start_worker.sh

# Default to API service (Flask via Gunicorn)
# Railway can override CMD in Settings → Start Command
CMD ["gunicorn", "-b", "0.0.0.0:${PORT:-8080}", "app:app"]
