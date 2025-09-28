# Dockerfile
FROM python:3.10-slim

# Install system deps including ffmpeg
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl git build-essential && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Create app directory
WORKDIR /app
COPY . /app

# Make scripts executable
RUN chmod +x /app/start.sh /app/start_worker.sh || true

# default command is start.sh (API). For worker service set start command to start_worker.sh in Railway.
CMD ["./start.sh"]
