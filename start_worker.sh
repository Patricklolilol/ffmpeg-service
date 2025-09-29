#!/usr/bin/env bash
set -euo pipefail
echo "Starting RQ worker (waiting for Redis)..."
# Python wait+start (keeps logs readable)
python - <<'PY'
import os, time, sys
from redis import Redis
url = os.getenv("REDIS_URL", "")
if not url:
    print("REDIS_URL is not set", file=sys.stderr)
    sys.exit(1)
for i in range(60):
    try:
        Redis.from_url(url).ping()
        print("redis reachable")
        sys.exit(0)
    except Exception as e:
        print("waiting for redis...", e)
        time.sleep(1)
print("redis not reachable after timeout", file=sys.stderr)
sys.exit(1)
PY

# exec the programmatic worker (replaces invocation of CLI)
exec python worker.py
