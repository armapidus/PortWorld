# PRD - Son of Anton (v4)

## 1. Objective and Non-Goals

### Objective

Deliver a reliability-first iOS app that connects Meta Ray-Ban Gen 2 glasses to a backend service with:

- manual query trigger for MVP v4 (UI-driven trigger event),
- continuous photo uplink (`1 image/second` JPEG frames as base64 JSON),
- local rolling video and audio capture (not uploaded continuously),
- on-query bundle upload: audio (WAV) + video (MP4, 5s pre-wake context) as `multipart/form-data`,
- and assistant audio playback to glasses speakers via WebSocket.

### Non-Goals

- Continuous video/audio upload (only uploaded as part of query bundles).
- Full backend infrastructure design and deployment (backend is a black-box service).
- Final multi-agent orchestration policy (handled server-side).
- UI polish beyond operational controls and debug state.
- Production-grade privacy/compliance program.
- Guaranteed uninterrupted background runtime on iOS.

## 2. Product Scope and Flow

### In Scope

- Registration + callback flow with Meta AI app.
- Permission handling for camera and microphone paths.
- One-click activation flow for connection + live services.
- Manual query trigger that emits `wakeword.detected` compatibility events.
- End-of-query detection via VAD silence timeout (default `5s`).
- Continuous photo upload: 1 FPS JPEG frames as base64 JSON to `POST /vision/frame`.
- Local rolling video capture: H.264 buffer (not uploaded continuously).
- Local rolling audio capture: PCM buffer (not uploaded continuously).
- Query bundle upload: on manual trigger → VAD silence, bundle audio (WAV) + video (MP4, 5s pre-wake context) as `multipart/form-data` to `POST /query`.
- Assistant audio return stream and playback to glasses speakers.
- Reconnect and recovery behavior for control/audio interruptions.
- Session observability and event logging.

### End-to-End Flow

1. User opens app.
2. User registers app with Meta AI callback flow.
3. App confirms permission readiness.
4. User taps one activation action.
5. App opens control WebSocket and enters active listening state.
6. App begins capture:
   - Photo sampler sends `vision.frame` at 1 FPS to `POST /vision/frame`.
   - Video encoder captures locally as rolling H.264 buffer.
   - Audio capture runs locally as rolling PCM buffer.
7. User triggers query manually; app signals `wakeword.detected` (trigger source: manual) and marks query start.
8. User speaks; app marks query end when silence timeout is reached.
9. App extracts video segment (5s pre-wake + query duration), encodes to MP4.
10. App bundles audio (WAV) + video (MP4) and uploads to `POST /query` (multipart/form-data).
11. Backend processes bundle and streams assistant audio chunks.
12. App plays assistant audio on glasses speakers.
13. On drops/suspension, app reconnects/resumes when runtime allows.

## 3. Functional Requirements

- `FR-01` Registration and callback flow via Meta app.
- `FR-02` Permission handling for camera + mic path.
- `FR-03` One-click activation starts session, manual query trigger readiness, photo upload, and local video/audio capture.
- `FR-04` Query start is initiated by manual trigger in v4, while preserving `wakeword.detected` compatibility signaling.
- `FR-05` Query lifecycle uses VAD silence timeout (default `5s`) to detect query end.
- `FR-06` App uploads `vision.frame` photos at target `1 FPS` to `POST /vision/frame` (base64 JSON).
- `FR-07` App maintains local rolling video buffer (H.264) for query context extraction.
- `FR-08` App maintains local rolling audio buffer (PCM) for query audio extraction.
- `FR-09` On query end, app extracts video segment (5s pre-wake + query duration), encodes to MP4.
- `FR-10` On query end, app bundles audio (WAV) + video (MP4) and uploads to `POST /query` (multipart/form-data).
- `FR-11` Assistant audio return (`assistant.audio_chunk`) plays through glasses speakers.
- `FR-12` Reconnect restores control plane and playback continuity after interruptions.
- `FR-13` Debug surface shows session/wake/query/photo/playback state and key metrics.

## 4. Non-Functional Requirements

- `NFR-01` Zero crashes in core flow scenarios.
- `NFR-02` Resilient reconnect behavior for WebSocket and runtime resume paths.
- `NFR-03` Bounded queue/memory behavior under repeated wake/query cycles.
- `NFR-04` Reliable glasses-route playback for assistant audio when route is available.
- `NFR-05` Observable end-to-end lifecycle events with millisecond timestamps.
- `NFR-06` Query bundle encoding must not introduce excessive latency (target: bundle ready within 2s of query end).
- `NFR-07` Photo upload bandwidth: 1 FPS JPEG base64 must not exceed typical mobile network capacity.
- `NFR-08` Battery/CPU budget: local video capture + trigger/listening loop must be sustainable for extended sessions.
- `NFR-09` Rolling buffer memory: video + audio buffers must stay within reasonable RAM limits.

## 5. Transport Architecture (Control and Data)

### Control Plane (WebSocket)

Purpose: session orchestration, health, wake events, playback control.
Endpoint: `wss://<host>/ws/session`

### HTTP Endpoints

#### `POST /vision/frame` (Continuous Photo Upload)

- Cadence: 1 frame/second
- Content-Type: `application/json`
- Body: `{ "session_id": "...", "ts_ms": ..., "frame_b64": "<base64 JPEG>" }`

#### `POST /query` (Query Bundle Upload)

- Trigger: manual query trigger event → VAD silence timeout
- Content-Type: `multipart/form-data`
- Parts:
  - `metadata` (JSON): session_id, wake_ts_ms, query_start_ts_ms, query_end_ts_ms, video_start_ts_ms
  - `audio` (WAV): query audio clip
  - `video` (MP4): video segment (5s pre-wake + query duration)

### Downlink

- `assistant.audio_chunk`: streamed via WebSocket for playback

### Backend Service Model

- Photos go to `POST /vision/frame` for continuous scene understanding.
- Query bundles go to `POST /query` for self-contained query processing.
- No server-side timestamp correlation needed; query bundle is self-contained.
- WebSocket streaming is required for server -> app assistant audio.

## 6. Interface Contracts and Message Schemas

Normative contracts are defined in [PRD_APPENDIX_INTERFACES.md](./PRD_APPENDIX_INTERFACES.md).

## 7. Session and Runtime State Machines

Normative state machines are defined in [PRD_APPENDIX_INTERFACES.md](./PRD_APPENDIX_INTERFACES.md).

## 8. Wake, Clip, and Timeout Strategy

- Query trigger engine: manual UI trigger in v4.
- Clip open condition: manual trigger detected.
- Clip close condition: VAD silence timeout default `5000ms`.
- Automatic wake-word detection is deferred to v4.1+ and does not block v4 release. Planned approach: Apple on-device `SFSpeechRecognizer` in continuous local-recognition mode with keyword matching against `"hey mario"` (see §12 Deferred for rationale).

## 9. Failure Modes and Recovery

- Control socket drop: reconnect with exponential backoff and heartbeat recovery.
- Runtime suspension in background: recover session and reconnect on resume.
- Audio route loss: report route error and attempt glasses-route recovery.
- Protocol or unrecoverable transport failure: fail fast with visible error state.

## 10. Observability and Debug Requirements

- Live states: registration, permission, session, wake, query, photo upload, video buffer, audio buffer, playback route.
- Metrics/log events:
  - manual query trigger count
  - accidental trigger count (from test corpus)
  - query start/end timings
  - query bundle creation time (video extraction + encoding)
  - query bundle upload success/failure and latency
  - effective photo upload cadence (`POST /vision/frame` fps)
  - photo upload success/failure counts
  - rolling buffer status (video/audio duration available)
  - reconnect attempt count and latency
  - query-end to first-audio-byte latency
- Event logs timestamped in ms.

## 11. Acceptance Criteria and Test Matrix

Normative acceptance criteria and test matrix are defined in [PRD_ACCEPTANCE.md](./PRD_ACCEPTANCE.md).

## 12. Risks, Dependencies, Open Questions

### Risks

- Manual trigger UX may reduce hands-free ergonomics until auto-wake v4.1+.
- iOS background runtime limits may suspend active session loops.
- Backend contract drift if schema governance is weak.
- Query bundle creation latency (video extraction + encoding) may delay response.
- Rolling buffer memory pressure on device.
- Photo upload bandwidth on poor networks.

### Dependencies

- Meta DAT iOS SDK + device compatibility.
- Backend endpoints: `POST /vision/frame`, `POST /query`, WebSocket.
- AVAssetWriter / VideoToolbox for H.264 encoding and MP4 muxing.

### Open Questions

- Final VAD threshold tuning per environment profile.
- Video encoding parameters for query bundle: resolution, bitrate, keyframe interval.
- Rolling buffer duration (currently 5s pre-wake; may need tuning).
- Final payload size limits for photos (base64 overhead ~33%).
- Retention/deletion policy for photos and query bundles (server-side).

## 13. Milestones (v4)

- `M1` v4 PRD and contract freeze.
- `M2` Manual trigger + query lifecycle implementation (manual trigger + VAD).
- `M3` 1 FPS photo upload implementation (`POST /vision/frame`).
- `M4` Local rolling video buffer implementation.
- `M5` Local rolling audio buffer implementation.
- `M6` Query bundle creation (video extraction + MP4 encoding + WAV bundling).
- `M7` Query bundle upload implementation (`POST /query` multipart/form-data).
- `M8` WebSocket client and assistant audio downlink.
- `M9` Assistant audio playback stabilization.
- `M10` Reliability test matrix sign-off.

## 14. Implementation Status (as of March 1, 2026) - Baseline Lock

### Completed in this repo (preserved from v1 baseline)

- [x] DAT SDK app bootstrap and registration callback flow.
- [x] CameraAccess-style app structure replicated (views, view models, flow gating).
- [x] Local streaming session controls (start/stop) and live frame rendering.
- [x] Photo capture flow with preview/share UI.
- [x] DEBUG mock-device tooling removed (no longer needed).
- [x] iOS project alignment for replication (`iOS 17.0` minimum, package pinned to `0.4.0`).
- [x] DAT config placeholders wired through build settings (`META_APP_ID`, `CLIENT_TOKEN`, `DEVELOPMENT_TEAM`).
- [x] Audio collection foundation implemented (glasses/HFP-oriented audio session setup + microphone permission flow).
- [x] Separate audio controls added to app UI (prepare/start/stop independent from video streaming controls).
- [x] Local rolling audio chunk persistence implemented (`.wav` chunks + `index.jsonl` metadata in app Documents sandbox).
- [x] Audio collection runtime state and metrics surfaced in UI (state, chunks written, bytes, session path, last error).
- [x] Runtime endpoint configuration model implemented (`SON_WS_URL`, `SON_VISION_URL`, `SON_QUERY_URL`, `SON_PHOTO_FPS` via `RuntimeConfig`).
- [x] Unified runtime orchestration flow introduced (`SessionOrchestrator`) and wired to app view model.
- [x] Manual wake trigger engine and query endpoint detector integrated for v4 trigger lifecycle.
- [x] Vision frame uploader implemented for continuous JSON `POST /vision/frame` uploads.
- [x] Rolling video buffer + MP4 interval export implemented.
- [x] Query bundle builder implemented for multipart `POST /query` (`metadata` + `audio` + `video`).
- [x] WebSocket client implemented with reconnect loop, ping support, inbound message decoding.
- [x] Assistant PCM chunk playback engine implemented for `assistant.audio_chunk`.

### v4 Alignment Notes (remaining gaps to release gate)

- [x] One-click activation flow that combines connection state, wake listener startup, and capture.
- [x] Manual query trigger path and deterministic `wakeword.detected` compatibility signaling finalized for v4.
- [x] VAD-based query end detection with default `5s` silence timeout.
- [x] 1 FPS photo upload to `POST /vision/frame` (base64 JPEG in JSON).
- [x] Local rolling video buffer with MP4 export for query interval.
- [x] Local rolling audio buffer and WAV query-window export.
- [x] Query bundle creation: extract video segment (5s pre-wake + query), encode to MP4.
- [x] Query bundle upload to `POST /query` (multipart/form-data: audio WAV + video MP4).
- [x] WebSocket client for control plane and audio downlink.
- [x] Backend endpoint configuration (`/vision/frame`, `/query`, WebSocket).
- [x] Realtime downlink `assistant.audio_chunk` playback route hardening to guarantee glasses-preferred routing and recovery on route loss.
- [x] Best-effort background continuity + resume/reconnect policy implementation.
- [x] Health telemetry completion (`health.ping`, `health.stats`) and required metric rollups for acceptance evidence.
- [x] Upload reliability policies (retry/backoff/timeout classification) for vision and query uploads.
- [ ] Rolling video memory boundedness proof under soak (`T11`, `T13`) and potential ring-buffer hardening.
- [ ] Reliability test matrix execution (`T1` to `T13`) and release gate evidence.

### Deferred to v4.1+

- [ ] Automatic on-device wake-word detection via **Apple `SFSpeechRecognizer`** (continuous local recognition) + keyword match on `"hey mario"`.
  - Rationale: Porcupine requires 16kHz input and is incompatible with the 8kHz glasses audio pipeline. Upsampling 8kHz→16kHz degrades recognition accuracy. `SFSpeechRecognizer` with `requiresOnDeviceRecognition = true` handles the raw audio natively, avoids any server round-trip, and has no sample-rate constraint from the client side.
  - Acceptance bar: false-trigger rate < 1/hour in ambient noise soak; detection latency < 2s p95.
