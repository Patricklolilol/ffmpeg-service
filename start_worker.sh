#!/bin/sh
set -eu

: "${REDIS_URL:?Environment variable REDIS_URL must be set}"

echo "Starting rq worker with REDIS_URL=${REDIS_URL#*://*****@}"

exec rq worker -u "$REDIS_URL" default
