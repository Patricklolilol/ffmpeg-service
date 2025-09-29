import os
import logging
from flask import Flask, request, jsonify, abort

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# API Key (set in Railway environment)
API_KEY = os.getenv("FFMPEG_API_KEY")

@app.before_request
def require_api_key():
    if API_KEY:  # Enforce only if key exists
        key = request.headers.get("x-api-key")
        if key != API_KEY:
            abort(401, description="Invalid or missing API key")

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/process", methods=["POST"])
def process():
    try:
        data = request.get_json(force=True)
        app.logger.info(f"Received payload: {data}")

        media_url = data.get("media_url")
        if not media_url:
            return jsonify({"status": "error", "message": "media_url missing"}), 400

        # TODO: Call ffmpeg, whisper, etc. Here we just return a mock response
        return jsonify({
            "status": "success",
            "message": f"Processing started for {media_url}"
        }), 200

    except Exception as e:
        app.logger.error(f"Error in /process: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

# Lovable sometimes expects /jobs
@app.route("/jobs", methods=["POST"])
def jobs_alias():
    return process()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
