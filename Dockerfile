# Dockerfile - single image used for both API and worker (override start command on Railway for worker)
FROM python:3.10-slim

# system deps for ffmpeg, fonts (for burned captions), yt-dlp, build tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ffmpeg curl git build-essential fonts-dejavu-core libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

# copy & install python deps
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app
COPY . .

# Ensure outputs dir exists and worker script is executable
RUN mkdir -p /app/outputs && chmod +x /app/start_worker.sh

# Default command (API service)
CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${PORT:-8080} app:app"]
