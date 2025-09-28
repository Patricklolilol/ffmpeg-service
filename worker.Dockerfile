FROM python:3.10-slim

RUN apt-get update && apt-get install -y ffmpeg curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app
COPY . .

# Show Redis URL at startup (debugging)
CMD echo "Worker starting with REDIS_URL=$REDIS_URL" && rq worker --url $REDIS_URL default
