FROM python:3.10-slim

# System deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ffmpeg curl git build-essential fonts-dejavu-core libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app
COPY . .

# Ensure outputs dir exists
RUN mkdir -p /app/outputs

# Run API with Gunicorn (Railway injects $PORT)
CMD ["gunicorn", "-b", "0.0.0.0:${PORT:-8080}", "app:app"]
