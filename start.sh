#!/bin/sh
set -e

# quick env check
if [ -z "$REDIS_URL" ]; then
  echo "ERROR: REDIS_URL environment variable is not set. Set it in Railway variables."
  exit 1
fi

# Start RQ worker in background (will connect to REDIS_URL). The 'rq' CLI will fail
# if REDIS_URL is missing; we already checked above.
echo "Starting RQ worker..."
rq worker -u "$REDIS_URL" default &

# Start Gunicorn (allow Railway's $PORT). Use shell form so ${PORT} expands.
echo "Starting Gunicorn on port ${PORT:-8080}..."
exec gunicorn -b 0.0.0.0:${PORT:-8080} app:app
