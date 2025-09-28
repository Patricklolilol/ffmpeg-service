# worker.py
import os
import redis
from rq import Worker, Queue, Connection

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
redis_conn = redis.from_url(REDIS_URL)

if __name__ == "__main__":
    with Connection(redis_conn):
        q = Queue("default")
        worker = Worker([q], connection=redis_conn)
        worker.work()
