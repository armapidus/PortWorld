# Mock Backend (v4 Reliability)

This mock server implements the v4 client contracts:
- `POST /vision/frame`
- `POST /query`
- `WS /ws/session`

It supports fault injection through `FAULT_PROFILE` (env) and `X-Fault-Profile` (header on HTTP requests).

## Quick start

```bash
cd tools/mock_backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8080
```

## Fault profile format

Comma-separated flags and/or key-value entries:

- `latency` (shorthand for `latency_ms=500`)
- `flaky_vision` (shorthand for `vision_5xx_every=3`)
- `flaky_query` (shorthand for `query_5xx_every=2`)
- `drop_ws` (shorthand for `ws_drop_after=5`)
- `malformed` (shorthand for `malformed_ws_once=true`)
- `no_audio`
- `latency_ms=<int>`
- `vision_5xx_every=<int>`
- `query_5xx_every=<int>`
- `ws_drop_after=<int>`
- `malformed_ws_once=<bool>`

Examples:

```bash
FAULT_PROFILE="latency_ms=350,query_5xx_every=2" uvicorn server:app --host 0.0.0.0 --port 8080
FAULT_PROFILE="drop_ws,malformed" uvicorn server:app --host 0.0.0.0 --port 8080
```

## Data Capture

The server automatically stores all received data to disk for inspection:

```
captures/
  run-<timestamp>/
    vision/
      <session_id>/
        <frame_id>.jpg        ← decoded frame image
        <frame_id>.json       ← metadata sidecar
    query/
      <session_id>/
        <query_id>/
          metadata.json       ← parsed metadata
          audio.<ext>         ← raw audio file
          video.<ext>         ← raw video file
    ws/
      <session_id>/
        messages.jsonl        ← one JSON line per received message
```

Override the capture directory with `CAPTURE_DIR`:

```bash
CAPTURE_DIR=/tmp/my-test-run uvicorn server:app --host 0.0.0.0 --port 8080
```

**Inspecting captured data:**

```bash
# View vision frame metadata
cat captures/run-*/vision/*/frame-001.json | python3 -m json.tool

# Play captured audio (macOS)
afplay captures/run-*/query/*/*/audio.wav

# Pretty-print WebSocket messages
cat captures/run-*/ws/*/messages.jsonl | python3 -m json.tool

# Check video file info
file captures/run-*/query/*/*/video.*
```

## Notes

- The app already defaults to:
  - `SON_WS_URL=ws://localhost:8080/ws/session`
  - `SON_VISION_URL=http://localhost:8080/vision/frame`
  - `SON_QUERY_URL=http://localhost:8080/query`
- For physical iPhone testing, set these URLs to your machine LAN IP instead of `localhost`.
- Logs are JSON lines with `run_id`, `event`, `session_id`, and `query_id` where available.
- Captured data is stored even when fault injection returns errors (the data was received).
