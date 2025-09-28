# ffmpeg-service (single service: API + worker)

## Files added / changed
- Dockerfile
- requirements.txt
- start.sh
- app.py
- tasks.py

## Railway setup (important)
1. In your Railway project, pick the single service that should run this repo (the one with the ffmpeg-service code).
2. Add environment variable:
   - `REDIS_URL` = `redis://default:<PASSWORD>@<HOST>:<PORT>` (your Railway Redis provided URL)
     - Example: `redis://default:eHQyuqwUljCiXdWqjhbLBwpSnNLSbdkc@redis.railway.internal:6379`
   - DO NOT leave templated strings like `${{Redis.REDIS_URL}}` in the value — add the full Redis URL.
3. Railway sets `PORT` automatically — the container uses `${PORT}`. No need to manually set `PORT`.
4. Start command (Railway) — leave blank if using Dockerfile (Railway will use the Dockerfile `CMD`). If you use the "Start Command" field, use:
