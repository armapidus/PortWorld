# Backend (Loop A Mock)

FastAPI backend that bridges iOS websocket transport to OpenAI Realtime.

## What Changed (Current Architecture)

The backend now uses a session-oriented websocket runtime:

- Single websocket endpoint: `WS /ws/session`
- JSON control envelopes (for session/control state) + binary audio frames (for uplink/downlink PCM)
- Session lifecycle controls:
  - `session.activate`
  - `session.end_turn`
  - `session.deactivate`
- Binary audio transport:
  - iOS -> backend uses frame type `0x01` (`CLIENT_AUDIO_FRAME_TYPE`)
  - backend -> iOS uses frame type `0x02` (`SERVER_AUDIO_FRAME_TYPE`)
  - optional probe frame type `0x03` (`CLIENT_PROBE_FRAME_TYPE`)
- Per-session bridge implementation:
  - `IOSRealtimeBridge` (default): forwards audio to OpenAI Realtime and streams output audio back
  - `IOSMockCaptureBridge` (debug mode): captures inbound audio only, no OpenAI connection

### Backend Flow

1. Client sends `session.activate` envelope.
2. Backend validates declared client audio format (if provided):
   - `encoding=pcm_s16le`
   - `channels=1`
   - `sample_rate=24000`
3. Backend creates a session bridge and returns `session.state` with `{"state":"active"}`.
4. Client streams binary audio frames (`0x01`).
5. Backend forwards audio upstream and emits `transport.uplink.ack` on first frame and then every N frames.
6. Backend relays assistant PCM back as binary frames (`0x02`) and emits playback control envelopes.
7. On turn end or disconnect, backend closes bridge and session with `session.state` ended.

### Modules

- App wiring: `backend/api/app.py`
- WS entrypoint: `backend/api/routes/session_ws.py`
- Control dispatch: `backend/ws/control_dispatch.py`
- Binary dispatch/frame codec: `backend/ws/binary_dispatch.py`, `backend/ws/frame_codec.py`
- Session lifecycle/registry: `backend/ws/session_activation.py`, `backend/ws/session_runtime.py`, `backend/ws/session_registry.py`
- OpenAI realtime client/bridge: `backend/realtime/client.py`, `backend/realtime/bridge.py`, `backend/realtime/factory.py`

## API Surface

- `GET /healthz`
- `POST /vision/frame` with JSON body: `{"frame_id": "optional-id"}`
- `WS /ws/session` (control envelopes + binary audio frames)

## Setup

From repo root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Required vs Optional Environment

- Required for realtime mode:
  - `OPENAI_API_KEY`
- Optional runtime configuration:
  - `OPENAI_REALTIME_MODEL` (default: `gpt-realtime`)
  - `OPENAI_REALTIME_VOICE` (default: `ash`)
  - `OPENAI_REALTIME_INSTRUCTIONS`
  - `OPENAI_REALTIME_INCLUDE_TURN_DETECTION` (default: `true`)
  - `OPENAI_REALTIME_ENABLE_MANUAL_TURN_FALLBACK` (default: `true`)
  - `OPENAI_REALTIME_MANUAL_TURN_FALLBACK_DELAY_MS` (default: `900`, min `100`)
  - `OPENAI_REALTIME_UPLINK_ACK_EVERY_N_FRAMES` (default: `20`, min `1`)
  - `OPENAI_REALTIME_ALLOW_TEXT_AUDIO_FALLBACK` (default: `false`, deprecated compatibility path)
  - `OPENAI_DEBUG_DUMP_INPUT_AUDIO` (default: `false`)
  - `OPENAI_DEBUG_DUMP_INPUT_AUDIO_DIR` (code default: `backend/var/debug_audio`)
  - `OPENAI_DEBUG_MOCK_CAPTURE_MODE` (default: `false`)
  - `OPENAI_DEBUG_TRACE_WS_MESSAGES` (default: `false`)
  - `HOST` / `PORT` / `LOG_LEVEL` / `CORS_ORIGINS`

## Run

From repo root:

```bash
source backend/.venv/bin/activate
uvicorn backend.app:app --host 0.0.0.0 --port 8080 --log-level info --reload
```

Quick check:

```bash
curl http://127.0.0.1:8080/healthz
```

## WebSocket Usage Notes

- Activate session before sending binary frames; binary frames before activation are ignored.
- `client.audio` text/base64 envelopes are accepted only when:
  - `OPENAI_REALTIME_ALLOW_TEXT_AUDIO_FALLBACK=true`
  - This path is temporary and logs a deprecation warning.
- Empty audio payloads generate an error envelope.

## Local Probe

Use the probe script to validate control + binary framing:

```bash
source backend/.venv/bin/activate
python backend/scripts/ws_probe.py \
  --url ws://127.0.0.1:8080/ws/session \
  --session-id sess_probe \
  --frame-size-bytes 4080 \
  --frame-count 24 \
  --frame-duration-ms 85 \
  --frame-interval-ms 85 \
  --expect-ack-count 2
```

Optional deprecated text fallback probe:

```bash
python backend/scripts/ws_probe.py --send-text-fallback
```

## Debug Modes

### 1) Input audio dump

Enable raw inbound PCM16 WAV dumps:

```bash
OPENAI_DEBUG_DUMP_INPUT_AUDIO=true
OPENAI_DEBUG_DUMP_INPUT_AUDIO_DIR=backend/var/debug_audio
```

### 2) Mock capture mode (no OpenAI dependency)

Use this to isolate iPhone -> backend transport:

```bash
OPENAI_DEBUG_MOCK_CAPTURE_MODE=true
OPENAI_DEBUG_DUMP_INPUT_AUDIO=true
OPENAI_DEBUG_DUMP_INPUT_AUDIO_DIR=backend/var/debug_audio
```

Behavior in mock mode:

- `session.activate` works without `OPENAI_API_KEY`
- inbound client audio is acknowledged and captured
- `session.deactivate` emits `debug.capture.summary`
- no upstream OpenAI websocket is created

## TLS Diagnostics (macOS)

If OpenAI calls fail with `CERTIFICATE_VERIFY_FAILED`:

```bash
source backend/.venv/bin/activate
python -c "import certifi; print(certifi.where())"
export SSL_CERT_FILE="$(python -c 'import certifi; print(certifi.where())')"
```

If needed for python.org builds, run `Install Certificates.command` once for that Python version.
