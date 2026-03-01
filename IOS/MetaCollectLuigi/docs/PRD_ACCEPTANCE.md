# PRD Acceptance - Son of Anton (v4)

## 1. Reliability Gate (Release Blocker)

The MVP is accepted only if all are true:

- Zero crashes across core registration/session/wake/query/playback scenarios.
- Wake and query lifecycle events are deterministic and timestamped.
- `1 FPS` photo upload pipeline is validated (`POST /vision/frame`).
- Local video and audio rolling buffers are stable (no memory growth).
- Query bundle creation (video extraction + encoding) completes within target latency.
- Query bundle upload pipeline is validated (`POST /query` multipart/form-data).
- Assistant audio downlink is playable on glasses speakers.
- Reconnect/resume behavior is validated for socket loss and runtime suspension/resume.

## 2. Test Matrix

## T1 - Fresh Install Registration

- Steps: install app, run registration flow, return via callback.
- Expected: app enters `registered` state; no crash.
- Requirements: `FR-01`, `NFR-01`.

## T2 - One-Click Activation

- Steps: from registered state, press single activation control.
- Expected: session transitions to `active`, manual trigger path is ready, photo upload begins (1 FPS), video/audio local capture begins.
- Requirements: `FR-02`, `FR-03`, `FR-06`, `FR-07`, `FR-08`.

## T3 - Manual Trigger Positive

- Steps: use manual query trigger control while session is active.
- Expected: `wakeword.detected` (manual trigger source) emitted, query state transitions to `recording`.
- Requirements: `FR-04`, `NFR-05`.

## T4 - Spurious Trigger Negative

- Steps: keep active session running with ambient speech/noise and no manual trigger input.
- Expected: no spontaneous trigger events; no clip opened.
- Requirements: `FR-03`, `NFR-02`.

## T5 - Query End on Silence Timeout

- Steps: trigger query manually, ask short query, remain silent > `5s`.
- Expected: `query.ended` emitted with reason `silence_timeout`; query duration is valid.
- Requirements: `FR-05`, `NFR-05`.

## T6 - Query Bundle Creation and Upload

- Steps: trigger query manually, speak query, wait for silence timeout.
- Expected: query bundle is created (video extracted, encoded to MP4, bundled with WAV audio) and uploaded to `POST /query`; `query.bundle.uploaded` event confirms success.
- Requirements: `FR-09`, `FR-10`, `NFR-06`.

## T7 - Photo Upload Cadence

- Steps: hold active session for 3 minutes under stable network.
- Expected: effective photo upload rate near 1 FPS (`POST /vision/frame`) with timestamp continuity.
- Requirements: `FR-06`, `NFR-07`.

## T8 - Assistant Audio Downlink Playback

- Steps: backend streams `assistant.audio_chunk` response after query bundle upload.
- Expected: audio is heard through glasses speakers and playback controls are honored.
- Requirements: `FR-11`, `NFR-04`.

## T9 - WebSocket Disconnect Recovery

- Steps: force control socket drop mid-session.
- Expected: session enters `reconnecting`, then recovers and resumes active flow including photo upload and local capture.
- Requirements: `FR-12`, `NFR-02`.

## T10 - Background Best-Effort Runtime

- Steps: move app to background during active session and observe behavior.
- Expected: if iOS allows runtime, photo upload and local capture continue; if suspended, app resumes and reconnects on foreground.
- Requirements: `FR-12`, `NFR-02`.

## T11 - Repeated Wake/Query Soak

- Steps: execute repeated manual-trigger + query cycles for extended run.
- Expected: no crash, bounded memory and queue growth, stable state transitions.
- Requirements: `NFR-01`, `NFR-03`.

## T12 - End-to-End Latency Monitoring

- Steps: measure clip-end to first assistant-audio-byte across multiple runs.
- Expected: latency events are recorded; no missing telemetry points.
- Requirements: `NFR-05`.

## T13 - Rolling Video Buffer Stability

- Steps: hold active session for 5 minutes under stable conditions.
- Expected: video buffer maintains rolling content, memory usage is bounded, no buffer overflow or underflow errors.
- Requirements: `FR-07`, `NFR-09`.

## T12b - Query Bundle Latency

- Steps: trigger query manually, speak 5-second query, measure time from query end to bundle upload complete.
- Expected: bundle creation + upload completes within target latency (< 2s for bundle creation).
- Requirements: `FR-09`, `FR-10`, `NFR-06`.

## 3. Pass/Fail Checklist

- [ ] All tests `T1-T13` pass.
- [ ] No unrecoverable crash in test logs.
- [ ] Wake and query lifecycle events are emitted with correlated `session_id` and `query_id`.
- [ ] Photo upload confirmed at effective 1 FPS cadence (`POST /vision/frame`).
- [ ] Query bundle creation and upload confirmed (`POST /query` with audio + video).
- [ ] Rolling video/audio buffers remain stable with bounded memory.
- [ ] Assistant audio playback on glasses is validated.
- [ ] Reconnect/resume behavior observed for disconnect and suspension scenarios.
- [ ] Debug state surface reflects true runtime wake/session/query/photo/buffer/playback state.

## 4. Required Test Artifacts

- Session logs with millisecond timestamps.
- Wake/query lifecycle logs (`wakeword.detected`, `query.started`, `query.ended`, `query.bundle.uploaded`).
- Photo upload cadence logs (`POST /vision/frame` timing and success/failure).
- Query bundle creation logs (video extraction, encoding, bundling timing).
- Query bundle upload logs (`POST /query` timing and success/failure).
- Rolling buffer status logs (video/audio buffer duration, memory usage).
- Reconnect timing logs (attempt count and recovery duration).
- Playback route and continuity evidence for glasses speakers.

## 5. Exit Criteria for Implementation Handoff

- PRD, interface appendix, and acceptance matrix are aligned and internally consistent.
- No unresolved blockers in required v4 contracts.
- Backend endpoints are available and documented (`POST /vision/frame`, `POST /query`, WebSocket).
- Open questions are tracked and explicitly non-blocking for first v4 implementation sprint.
