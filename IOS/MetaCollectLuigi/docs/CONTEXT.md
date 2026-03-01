# Son of Anton - Project Context

## 1) Mission

Build a reliable iOS companion app for Meta Ray-Ban glasses that supports hands-free plumbing workflows by:

- supporting manual query trigger for MVP v4,
- uploading lightweight visual context (`1 photo/second`) for continuous scene understanding,
- capturing video and audio locally as a rolling buffer,
- on query: bundling audio (WAV) + video (MP4, including pre-wake context) and uploading together,
- and streaming assistant audio responses back to glasses speakers.

## 2) Project Summary

`Son of Anton` is a hackathon MVP focused on integration reliability first.
The product direction is continuous photo context with on-demand query bundles.

Core pipeline:

1. App <-> glasses registration and permission readiness.
2. Manual local query trigger path (v4), with automatic wake deferred.
3. Continuous photo uplink: `POST /vision/frame` at 1 FPS (base64 JPEG in JSON).
4. Local rolling capture of video (H.264) and audio (PCM) — not uploaded continuously.
5. On query (wake → VAD silence): bundle audio (WAV) + video (MP4, 5s pre-wake + query duration) and upload via `POST /query` (multipart/form-data).
6. Backend processes query bundle and streams assistant audio response.
7. Assistant audio downlink streamed to glasses speakers over WebSocket.

## 3) Target Platform and Device

- iOS only (iPhone 16 Pro target for MVP)
- Meta Ray-Ban Gen 2 glasses
- Meta Wearables Device Access Toolkit (DAT) for iOS (`MWDATCore`, `MWDATCamera`)

## 4) MVP Scope

### In scope

- Meta registration callback flow and permission handling.
- One-click user action to connect glasses and activate realtime services.
- Manual query trigger path (`wakeword.detected` compatibility event).
- End-of-query detection using VAD silence timeout (default: `5s`).
- Continuous photo upload: 1 FPS JPEG frames as base64 JSON to `POST /vision/frame`.
- Local rolling video capture: H.264 buffer (no continuous upload).
- Local rolling audio capture: PCM buffer (no continuous upload).
- Query bundle upload: on manual trigger → VAD silence, bundle audio (WAV) + video (MP4, 5s pre-wake context) as `multipart/form-data` to `POST /query`.
- WebSocket-based assistant audio streaming back to glasses speakers.
- Best-effort background runtime with reconnect/resume on foreground recovery.
- Reliability observability (trigger events, query lifecycle, photo upload cadence, query bundle upload metrics).

### Out of scope (for now)

- Continuous video/audio upload (only uploaded as part of query bundle).
- Final production AI orchestration logic (backend handles model routing).
- Advanced UI/visual polish.
- Full production privacy/compliance implementation.
- Non-iOS platforms.
- Hard guarantee of uninterrupted background execution (iOS does not guarantee this).

## 5) User and Usage Assumptions

- Primary user: plumbers (hackathon scope).
- Hands are often occupied; wearable-first interaction is required.
- UX is operational: connect/activate status, trigger/query state, clip state, and error/debug visibility.

## 6) High-Level Product Flow (v4)

1. User opens app.
2. User connects/registers glasses (if needed).
3. User taps one action to activate session services.
4. App keeps a control WebSocket alive and enables manual query trigger.
5. App begins capture:
   - Uploads `vision.frame` photos at 1 FPS (base64 JSON to `POST /vision/frame`).
   - Captures video locally as rolling H.264 buffer (not uploaded).
   - Captures audio locally as rolling PCM buffer (not uploaded).
6. User triggers query manually; app enters query mode.
7. App records user speech until silence timeout (`5s`) indicates query end.
8. App extracts video segment (5s pre-wake + query duration), encodes to MP4.
9. App bundles audio (WAV) + video (MP4) and uploads via `POST /query` (multipart/form-data).
10. Backend processes bundle and streams assistant audio chunks over WebSocket.
11. App plays assistant audio on glasses speakers.
12. On network/session drops or app suspension, app attempts reconnect/resume when allowed.

## 7) Technical Direction

- Primary stack: native Swift + DAT SDK.
- Runtime architecture: thin on-device client + backend service.
- Realtime transport: WebSocket for control plane and assistant audio downlink.
- Query trigger mode: manual in v4.
- Endpointing: VAD silence timeout default `5s`.
- Photo upload: 1 FPS JPEG frames, base64 encoded in JSON, to `POST /vision/frame`.
- Video capture: local rolling H.264 buffer via `AVAssetWriter` or `VideoToolbox` (not uploaded continuously).
- Audio capture: local rolling PCM buffer (existing implementation).
- Query bundle: on manual trigger → VAD, extract video segment (5s pre-wake + query), encode to MP4, bundle with WAV audio, upload as `multipart/form-data` to `POST /query`.
- Optional local transcript support: Apple Speech framework for UX/debug assist only (not required for v4 trigger correctness).

## 8) Reliability Requirements

Priority: reliability over polish.

Minimum acceptance expectations:

- No crashes in registration/session/trigger/clip/playback loop.
- Reconnect and resume behavior for control socket and playback path.
- Deterministic trigger + clip boundary logging.
- Audio playback route remains glasses-first when available.

## 9) Background Runtime Policy

The app targets best-effort background continuity:

- Keep audio session + WebSocket active while iOS background execution permits.
- If iOS suspends runtime, app must recover session state and reconnect when execution resumes.
- Docs and tests must not assume a hard always-on guarantee in background.

## 10) Current Data and Privacy Position (MVP)

- Integration reliability is prioritized over productized governance.
- Photo frames are uploaded at 1 FPS; local buffering is minimal.
- Video is captured locally as a rolling buffer; only uploaded when bundled with a query.
- Audio is captured locally as a rolling buffer; only uploaded when bundled with a query.
- Query bundles (audio + video) are uploaded only when user explicitly triggers manually in v4.
- Retention policy (server-side) remains implementation-defined and must be formalized before production.

## 11) Development and Testing Approach

- Validate on real Ray-Ban Meta Gen 2 hardware.
- Emphasize soak reliability for repeated trigger/query cycles.
- Instrument event logs with timestamps for:
  - trigger detection,
  - query start/end (VAD boundaries),
  - query bundle creation (video extraction, encoding),
  - query bundle upload (`POST /query`),
  - photo frame upload cadence (`POST /vision/frame`),
  - assistant audio response start,
  - assistant playback completion,
  - reconnect attempts and latency.

## 12) Team Collaboration Expectations

`CONTEXT.md` remains shared source of truth.
Companion docs must remain aligned:

- `PRD.md` (requirements)
- `PRD_APPENDIX_INTERFACES.md` (wire contracts)
- `PRD_ACCEPTANCE.md` (release gate)

## 13) Decision Log (2026-03-01)

- Project codename: `Son of Anton`
- Platform: iOS only
- Device target: iPhone 16 Pro + Meta Ray-Ban Gen 2
- Stack: Swift native + DAT SDK
- Wake phrase compatibility event: `Hey Mario` label retained for protocol compatibility
- Trigger mode: manual for v4
- End-of-query policy: VAD silence timeout (default `5s`)
- Capture and upload strategy:
  - Photos: 1 FPS JPEG frames uploaded continuously as base64 JSON (`POST /vision/frame`)
  - Video: local rolling H.264 buffer, NOT uploaded continuously
  - Audio: local rolling PCM buffer, NOT uploaded continuously
- Query bundle strategy:
  - On manual trigger → VAD silence: extract video (5s pre-wake + query duration), encode to MP4
  - Bundle audio (WAV) + video (MP4) as `multipart/form-data`
  - Upload to `POST /query`
- Rationale: avoids server-side timestamp correlation; query bundle is self-contained
- Backend architecture: separate endpoints for photos and queries
- Downlink audio transport: WebSocket streaming (`assistant.audio_chunk`)
- Background runtime stance: best-effort continuity
- Priority: reliability over polish
- Deferred: automatic wake-word detection in v4.1+

## 14) Open Items

- Exact VAD thresholds/tuning for silence timeout across noisy plumbing environments. *(Speech-activity threshold and debounce are now runtime-configurable via `RuntimeConfig.speechRMSThreshold` / `speechActivityDebounceMs`; profile presets for specific environments remain open.)*
- Backend endpoint URLs and auth strategy (`/vision/frame`, `/query`, WebSocket).
- Video encoding parameters for query bundle: bitrate, resolution, keyframe interval.
- Rolling buffer duration for video (currently 5s pre-wake + query; may need tuning).
- Retention/deletion policy for photo frames and query bundles (server-side).
- Battery/CPU budget thresholds for local video capture + trigger/listening loop.
- Photo upload bandwidth budget (1 FPS JPEG, base64 ~33% overhead).
