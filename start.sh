#!/usr/bin/env bash
set -e

# Ensure outputs dir exists
mkdir -p outputs

# Bind to Railway provided PORT if present, else 8080
PORT=${PORT:-8080}
GUNICORN_WORKERS=${GUNICORN_WORKERS:-1}
GUNICORN_TIMEOUT=${GUNICORN_TIMEOUT:-120}

exec gunicorn -b 0.0.0.0:${PORT} app:app --workers ${GUNICORN_WORKERS} --timeout ${GUNICORN_TIMEOUT}
