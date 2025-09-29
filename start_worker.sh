#!/bin/sh
set -e

echo "Starting RQ worker (waiting for Redis)..."
echo "REDIS_URL=$REDIS_URL"

# ensure outputs dir exists
mkdir -p /app/outputs

# small wait loop for Redis to be reachable (best-effort)
i=0
until python - <<'PY'
import os, sys, redis, time
url = os.getenv("REDIS_URL")
if not url:
    print("REDIS_URL not set", file=sys.stderr); sys.exit(2)
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
  i=$((i+1))
  if [ $i -ge 10 ]; then
    echo "Redis did not become ready after tries. Continuing anyway..."
    break
  fi
  sleep 1
done

# start worker (use long option --url to avoid parsing ambiguities)
exec python -m rq worker --url "$REDIS_URL" default
