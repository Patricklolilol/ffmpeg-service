#!/bin/sh
set -eu

# Prefer REDIS_URL environment variable (Railway shared var name)
: "${REDIS_URL:?Environment variable REDIS_URL must be set}"

# Optional: log which redis url is being used (be careful if exposing secrets)
echo "Starting rq worker with REDIS_URL=${REDIS_URL#*://*****@}"

# Exec the worker so it receives signals correctly
exec rq worker -u "$REDIS_URL" default
