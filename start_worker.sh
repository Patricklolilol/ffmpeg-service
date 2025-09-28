#!/usr/bin/env bash
set -e

# Ensure outputs dir exists
mkdir -p outputs

if [ -z "$REDIS_URL" ]; then
  echo "ERROR: REDIS_URL is not set"
  exit 1
fi

# Start an rq worker using the REDIS_URL env var
exec rq worker --url "$REDIS_URL" default
