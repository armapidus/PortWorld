# PRD Appendix - Interfaces and State Machines (v4)

## 1. Interface Scope

This appendix defines contract interfaces between iOS client and backend service for:

- Control and signaling (WebSocket `wss://<host>/ws/session`).
- Continuous photo uplink (`POST /vision/frame`, 1 FPS).
- Query bundle uplink (`POST /query`, multipart/form-data with audio + video).
- Assistant audio downlink (`assistant.audio_chunk` via WebSocket).

## 2. Control Plane (WebSocket)

### 2.1 Envelope

All control and realtime signaling messages use this envelope:

```json
{
  "type": "string",
  "session_id": "string",
  "seq": 123,
  "ts_ms": 1740777600000,
  "payload": {}
}
```

Required fields:

- `type`: message type.
- `session_id`: active session identifier.
- `seq`: monotonic message sequence per direction.
- `ts_ms`: unix epoch milliseconds.
- `payload`: type-specific body.

### 2.2 Message Types

Client -> backend:

- `session.activate`
- `session.deactivate`
- `wakeword.detected`
- `query.started`
- `query.ended`
- `query.bundle.uploaded`
- `health.ping`
- `health.stats`
- `error`

Backend -> client:

- `session.state`
- `health.pong`
- `assistant.audio_chunk`
- `assistant.playback.control`
- `error`

## 3. HTTP Uplink Contracts

## 3.1 `POST /vision/frame` (Continuous Photo Upload)

Purpose: lightweight continuous visual context for backend scene understanding.

Cadence requirement:

- Target: `1 frame/second` while session is active.
- Temporary drops may occur under suspension or transport loss and must be logged.

Request:

```http
POST /vision/frame HTTP/1.1
Content-Type: application/json

{
  "session_id": "sess_123",
  "ts_ms": 1740777601000,
  "frame_id": "frame_1740777601000",
  "capture_ts_ms": 1740777600990,
  "width": 1280,
  "height": 720,
  "frame_b64": "<base64 encoded JPEG>"
}
```

Response:

```json
{
  "status": "ok",
  "frame_id": "frame_1740777601000"
}
```

## 3.2 `POST /query` (Query Bundle Upload)

Purpose: self-contained query bundle with audio and video context for processing.

Trigger: wake word detected (`Hey Mario`) → VAD silence timeout (default `5s`).

Request:

```http
POST /query HTTP/1.1
Content-Type: multipart/form-data; boundary=----QueryBoundary

------QueryBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{
  "session_id": "sess_123",
  "query_id": "query_abc123",
  "wake_ts_ms": 1740777602000,
  "query_start_ts_ms": 1740777602100,
  "query_end_ts_ms": 1740777607000,
  "video_start_ts_ms": 1740777597000,
  "video_end_ts_ms": 1740777607000
}
------QueryBoundary
Content-Disposition: form-data; name="audio"; filename="query.wav"
Content-Type: audio/wav

<binary WAV data: PCM 16-bit, 8kHz or 16kHz, mono>
------QueryBoundary
Content-Disposition: form-data; name="video"; filename="context.mp4"
Content-Type: video/mp4

<binary MP4 data: H.264, 5s pre-wake + query duration>
------QueryBoundary--
```

Response:

```json
{
  "status": "ok",
  "query_id": "query_abc123",
  "processing": true
}
```

Notes:

- Video includes 5 seconds of context before wake word detection.
- Audio covers only the query period (wake → VAD silence).
- Bundle is self-contained; no server-side timestamp correlation needed.

## 4. Downlink Contracts

## 4.1 `assistant.audio_chunk`

Purpose: stream assistant response audio for playback on glasses speakers.

```json
{
  "type": "assistant.audio_chunk",
  "session_id": "sess_123",
  "seq": 610,
  "ts_ms": 1740777610000,
  "payload": {
    "response_id": "resp_87",
    "chunk_id": "resp_87_1",
    "codec": "pcm_s16le",
    "sample_rate": 16000,
    "channels": 1,
    "duration_ms": 180,
    "is_last": false,
    "bytes_b64": "..."
  }
}
```

## 4.2 `assistant.playback.control`

Purpose: playback orchestration signals.

Allowed commands:

- `start_response`
- `stop_response`
- `cancel_response`

## 5. Event Lifecycle Contracts (WebSocket)

## 5.1 Wake lifecycle

`wakeword.detected` — sent when wake phrase is recognized:

```json
{
  "type": "wakeword.detected",
  "session_id": "sess_123",
  "seq": 230,
  "ts_ms": 1740777602100,
  "payload": {
    "wake_phrase": "hey mario",
    "engine": "sfspeech_keyword",
    "confidence": 1.0
  }
}
```

## 5.2 Query lifecycle events

These events inform the backend of query state. The actual query data is uploaded via `POST /query`.

`query.started` — sent when wake word triggers query mode:

```json
{
  "type": "query.started",
  "session_id": "sess_123",
  "seq": 231,
  "ts_ms": 1740777602200,
  "payload": {
    "query_id": "query_abc123"
  }
}
```

`query.ended` — sent when VAD silence timeout triggers query end:

```json
{
  "type": "query.ended",
  "session_id": "sess_123",
  "seq": 239,
  "ts_ms": 1740777607000,
  "payload": {
    "query_id": "query_abc123",
    "reason": "silence_timeout",
    "silence_timeout_ms": 5000,
    "duration_ms": 4800
  }
}
```

`query.bundle.uploaded` — sent after `POST /query` completes:

```json
{
  "type": "query.bundle.uploaded",
  "session_id": "sess_123",
  "seq": 241,
  "ts_ms": 1740777608500,
  "payload": {
    "query_id": "query_abc123",
    "upload_status": "ok",
    "audio_bytes": 76800,
    "video_bytes": 2457600
  }
}
```

## 6. State Machines

## 6.1 Registration State

- `unregistered -> pending -> registered -> failed`

### 6.2 Permission State

- `unknown -> requested -> granted_once | granted_always | denied`

### 6.3 Session State

- `idle -> connecting -> active -> reconnecting -> ended | failed`

### 6.4 Wake State

- `listening -> triggered -> listening`

### 6.5 Query State

- `idle -> recording -> processing_bundle -> uploading -> idle | failed`

### 6.6 Photo Upload State

- `idle -> uploading -> idle | failed`

### 6.7 Video Buffer State

- `idle -> capturing -> idle`

### 6.8 Audio Buffer State

- `idle -> capturing -> idle`

### 6.9 Runtime State

- `foreground_active -> background_best_effort -> suspended -> resumed`

## 7. Error Catalog (Minimum)

- `META_CALLBACK_TIMEOUT`
- `PERMISSION_DENIED_CAMERA`
- `PERMISSION_DENIED_MIC`
- `WAKE_ENGINE_UNAVAILABLE`
- `QUERY_TIMEOUT`
- `QUERY_BUNDLE_ENCODING_FAILED`
- `QUERY_BUNDLE_UPLOAD_FAILED`
- `PHOTO_UPLOAD_FAILED`
- `VIDEO_BUFFER_ERROR`
- `AUDIO_BUFFER_ERROR`
- `WS_DISCONNECTED`
- `WS_PROTOCOL_ERROR`
- `AUDIO_PLAYBACK_ROUTE_ERROR`

Error payload:

```json
{
  "type": "error",
  "session_id": "sess_123",
  "seq": 900,
  "ts_ms": 1740777612000,
  "payload": {
    "code": "WS_DISCONNECTED",
    "retriable": true,
    "message": "Control socket disconnected"
  }
}
```

## 8. Health and Observability

- Client sends `health.ping` on interval.
- Backend responds with `health.pong`.
- Client emits `health.stats` including:
  - `wake_state`
  - `query_state`
  - `queries_completed`
  - `query_bundles_uploaded`
  - `query_bundles_failed`
  - `photo_upload_rate_effective`
  - `photos_uploaded`
  - `photos_failed`
  - `video_buffer_duration_ms`
  - `audio_buffer_duration_ms`
  - `ws_reconnect_attempts`
  - `playback_route`

## 9. Contract Rules

- Unknown `type` must be ignored safely and logged.
- Out-of-order `seq` is tolerated with warning unless ordering constraints are violated for audio playback.
- Parse failures must not crash app runtime.
- Photos are uploaded continuously to `POST /vision/frame` (1 FPS).
- Query bundles are uploaded to `POST /query` only when a query occurs (wake → VAD silence).
- Query bundles are self-contained (audio + video); no server-side timestamp correlation needed.
- WebSocket is used for control plane and assistant audio delivery only.
- WebSocket streaming is required for server -> app assistant audio delivery.
