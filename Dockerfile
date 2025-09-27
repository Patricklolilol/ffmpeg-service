FROM python:3.10-slim

RUN apt-get update && apt-get install -y ffmpeg curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app
COPY . .

# Default command (API service)
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
