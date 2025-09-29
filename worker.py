import os, time
from redis import Redis
from rq import Queue, Worker, Connection

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise SystemExit("REDIS_URL environment variable not set")

def wait_for_redis(url, timeout=60):
    r = Redis.from_url(url)
    for i in range(timeout):
        try:
            r.ping()
            return r
        except Exception:
            time.sleep(1)
    raise RuntimeError("Redis not reachable")

def main():
    r = wait_for_redis(REDIS_URL, timeout=60)
    with Connection(r):
        q = Queue("default")
        w = Worker([q])
        w.work()

if __name__ == "__main__":
    main()
