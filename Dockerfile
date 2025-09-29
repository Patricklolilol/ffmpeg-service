FROM python:3.10-slim

# Install ffmpeg + deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl git build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install requirements
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy code
WORKDIR /app
COPY . .

# Expose port
EXPOSE 8080

# Run app with gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
