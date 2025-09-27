FROM python:3.10-slim

# Install ffmpeg + system deps
RUN apt-get update && apt-get install -y ffmpeg curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app
COPY . .

# Run with Gunicorn in WSGI mode for Flask
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
