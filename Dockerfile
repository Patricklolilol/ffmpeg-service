FROM python:3.10-slim

# install system deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl git build-essential && \
    rm -rf /var/lib/apt/lists/*

# copy and install python deps
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# app
WORKDIR /app
COPY . /app

# create outputs dir
RUN mkdir -p /app/outputs

# start via shell so $PORT can be used by Railway
ENV PORT 8080
CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${PORT:-8080} app:app"]
