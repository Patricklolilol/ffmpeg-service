FROM python:3.10-slim

# Install dependencies
RUN apt-get update && apt-get install -y ffmpeg curl && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app
COPY . .

# Default command (API service)
CMD ["gunicorn", "-b", "0.0.0.0:${PORT:-8080}", "app:app"]
