#!/bin/sh
set -e

echo "Starting RQ worker (waiting for Redis)..."
echo "REDIS_URL=$REDIS_URL"

# ensure outputs dir exists
mkdir -p /app/outputs

# wait loop for Redis to be reachable (best-effort)
TRIES=0
MAX_TRIES=10
until python - <<'PY'
import os, sys, redis
url = os.getenv("REDIS_URL")
if not url:
    print("REDIS_URL not set", file=sys.stderr)
    sys.exit(2)
try:
    r = redis.from_url(url)
    r.ping()
    print("redis reachable")
    sys.exit(0)
except Exception as e:
    print("redis not ready:", e)
    sys.exit(1)
PY
do
  TRIES=$((TRIES+1))
  if [ "$TRIES" -ge "$MAX_TRIES" ]; then
    echo "Redis did not become ready after $MAX_TRIES tries, continuing anyway..."
    break
  fi
  sleep 1
done

# Start the rq worker using the console script (do NOT use python -m rq)
# Use exec so the process id is the worker (better container behavior)
exec rq worker --url "$REDIS_URL" default
