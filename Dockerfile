FROM python:3.10-slim

# system deps (ffmpeg + fonts + deps for opencv / drawing text)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    ffmpeg curl git build-essential libgl1 libglib2.0-0 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

# install python deps
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app
COPY . /app

# make start script executable
RUN chmod +x /app/start.sh

# Railway provides $PORT; use 8080 as fallback locally
ENV PORT=8080

# run both worker (background) and gunicorn
CMD ["sh", "/app/start.sh"]
