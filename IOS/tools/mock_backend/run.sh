#!/usr/bin/env bash
set -euo pipefail

# Environment variables:
#   ELEVENLABS_API_KEY - Required for TTS greeting. Falls back to mock tone if not set.
#   ELEVENLABS_VOICE_ID - Voice ID (default: JBFqnCBsd6RMkjVDRZzb = George)
#   GREETING_TEXT - Greeting message (default: "Hey Pierre, how can I help you today?")
#   HOST - Server host (default: 0.0.0.0)
#   PORT - Server port (default: 8080)

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR/tools/mock_backend"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt >/dev/null

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"

exec uvicorn server:app --host "$HOST" --port "$PORT"
