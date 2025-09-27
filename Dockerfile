FROM python:3.10-slim

# Install ffmpeg + yt-dlp dependencies
RUN apt-get update && apt-get install -y ffmpeg curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app
COPY . .

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
