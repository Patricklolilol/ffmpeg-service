#!/bin/bash

# FFmpeg Service Startup Script
# Railway-compatible version

echo "FFmpeg Service Startup Script"
echo "=============================="

# Set defaults if not provided
FLASK_PORT=${FLASK_PORT:-8080}
GUNICORN_WORKERS=${GUNICORN_WORKERS:-4}
GUNICORN_WORKER_CLASS=${GUNICORN_WORKER_CLASS:-sync}
GUNICORN_TIMEOUT=${GUNICORN_TIMEOUT:-120}
GUNICORN_MAX_REQUESTS=${GUNICORN_MAX_REQUESTS:-1000}
GUNICORN_MAX_REQUESTS_JITTER=${GUNICORN_MAX_REQUESTS_JITTER:-100}

# Check if Gunicorn is installed
if command -v gunicorn >/dev/null 2>&1; then
    echo "Starting FFmpeg Service with Gunicorn..."
    echo "Workers: $GUNICORN_WORKERS"
    echo "Worker Class: $GUNICORN_WORKER_CLASS"
    echo "Timeout: $GUNICORN_TIMEOUT"
    echo "Max Requests: $GUNICORN_MAX_REQUESTS (+ jitter $GUNICORN_MAX_REQUESTS_JITTER)"
    echo "Port: $FLASK_PORT"
    
    exec gunicorn \
        --bind 0.0.0.0:$FLASK_PORT \
        --workers $GUNICORN_WORKERS \
        --worker-class $GUNICORN_WORKER_CLASS \
        --timeout $GUNICORN_TIMEOUT \
        --max-requests $GUNICORN_MAX_REQUESTS \
        --max-requests-jitter $GUNICORN_MAX_REQUESTS_JITTER \
        --access-logfile - \
        --error-logfile - \
        --log-level info \
        app:app
else
    echo "Gunicorn not found, starting Flask development server..."
    echo "Port: $FLASK_PORT"
    echo "Debug: ${FLASK_DEBUG:-false}"
    python app.py
fi
