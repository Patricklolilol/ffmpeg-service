#!/bin/sh
# simple worker entrypoint for Railway worker container
echo "Starting RQ worker with REDIS_URL=${REDIS_URL}"
exec rq worker --url "${REDIS_URL}" default
