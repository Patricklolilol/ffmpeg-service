FROM python:3.10-slim

# Install dependencies
RUN apt-get update && apt-get install -y ffmpeg curl && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
WORKDIR /app
COPY . .

# Default to API service (Railway will override this for worker)
CMD ["gunicorn", "-b", "0.0.0.0:${PORT}", "app:app"]
