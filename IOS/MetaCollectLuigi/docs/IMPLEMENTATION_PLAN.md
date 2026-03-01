# Implementation Plan - Son of Anton (v4)

## 1. Purpose

Define a dependency-aware, parallelizable implementation plan to deliver the v4 PRD in this repository without changing backend ownership.

This plan operationalizes:

- `PRD.md` (requirements and scope)
- `PRD_APPENDIX_INTERFACES.md` (wire contracts and state machines)
- `PRD_ACCEPTANCE.md` (release gate and test matrix)

## 2. Scope and Decision Lock

### Locked decisions for this implementation cycle

- Scope is `MVP v4 Core` only.
- Delivery model is `subsystem workstreams` with explicit dependencies.
- Backend auth for MVP is `none` (no `Authorization` header/token on `/vision/frame`, `/query`, or WebSocket handshake).
- Query start in v4 is manual trigger; automatic wake is deferred to `v4.1+`.

### In scope

- One-click activation flow.
- Manual query trigger compatibility runtime (`wakeword.detected` + `query.started`).
- VAD-based query end detection (`5s` default silence timeout).
- Continuous `POST /vision/frame` at target `1 FPS`.
- Local rolling video and audio buffers.
- Query bundle creation (`WAV + MP4`) and upload to `POST /query`.
- WebSocket control/downlink (`assistant.audio_chunk`) and glasses playback.
- Reconnect/resume behavior and observability.
- Validation against tests `T1-T13`.

### Out of scope

- Backend architecture changes.
- Non-iOS platforms.
- UI polish beyond operational/debug readiness.
- Optional transcript features and advanced UX extras.

## 3. Current Starting Point (Repository)

Already present in this repo:

- DAT registration/callback and camera streaming baseline.
- Photo capture flow from stream sessions.
- Audio collection foundation with HFP-oriented setup and local WAV chunk persistence.
- UI surfaces for registration/stream/audio controls.
- Runtime v4 foundation files are now implemented (`RuntimeConfig`, `RuntimeTypes`, `SessionOrchestrator`, `WakeWordEngine`, `QueryEndpointDetector`, `VisionFrameUploader`, `RollingVideoBuffer`, `QueryBundleBuilder`, `SessionWebSocketClient`, `AssistantPlaybackEngine`, `EventLogger`).

Primary gap to close:

- Move from "feature implemented" to "acceptance-ready":
  - finalize reliability policies (retry/backoff, route recovery, bounded resources),
  - wire lifecycle/background handling to runtime state machine,
  - complete health/telemetry emissions and release evidence,
  - execute and document `T1-T13` pass artifacts.

## 4. External Constraints to Respect

- DAT camera streams are session-state driven and should be handled via observed stream/session transitions.
- DAT stream quality is Bluetooth-bandwidth constrained; requested quality is not guaranteed.
- HFP audio route should be configured before stream/audio workflows that rely on device audio.
- DAT microphone input is 8kHz mono; v4 avoids 16kHz wake-engine assumptions.
- iOS background execution is best-effort and may suspend app runtime; design for resume/reconnect, not uninterrupted guarantees.

## 5. Workstream Breakdown

### WS0 - Contract Confirmation and Runtime Config Baseline

Goal: remove ambiguity before parallel implementation.

Tasks:

1. Confirm endpoint configuration model (`ws`, `/vision/frame`, `/query`) and environment mapping.
2. Confirm event schema fields and error catalog against `PRD_APPENDIX_INTERFACES.md`.
3. Confirm first-pass media parameters:
   - photo target resolution/quality envelope,
   - rolling video context window,
   - WAV sample rate/channel contract for query upload.
4. Record unresolved non-blocking tunables (VAD thresholds, bitrate tuning) in a tracked backlog.

Outputs:

- Confirmed interface contract checklist.
- Runtime configuration matrix for dev/test/prod.

Dependencies: none.

### WS1 - Runtime Orchestrator and State Machine Unification

Goal: establish a single app runtime coordinator that drives all feature streams.

Tasks:

1. Introduce a central session coordinator aligned to PRD states:
   - registration,
   - permissions,
   - session,
   - wake/query,
   - upload/buffer/playback.
2. Replace independent control toggles with one activation/deactivation action.
3. Implement consistent lifecycle hooks for foreground/background transitions.
4. Add deterministic event emission points (ms timestamps, session/query IDs).

Outputs:

- Single activation flow entering stable `active` mode.
- Canonical state transition map used across all streams.

Dependencies: WS0.

### WS2 - Wake and Query Boundary Pipeline

Goal: implement reliable query lifecycle boundaries.

Tasks:

1. Implement manual trigger loop with dedicated runtime ownership and failure handling.
2. Connect manual trigger to `wakeword.detected` compatibility signaling and `query.started`.
3. Implement VAD silence timeout endpointing (`5s` default), emitting `query.ended`.
4. Add guardrails for duplicate trigger events and overlap suppression.

Outputs:

- Deterministic trigger-to-query lifecycle events.
- Tunable wake/VAD parameters surfaced via config.

Dependencies: WS1, WS0.

### WS3 - Continuous Vision Uplink

Goal: maintain `1 FPS` photo upload during active runtime.

Tasks:

1. Build a frame sampler from DAT stream frames at `1 FPS` effective cadence.
2. Implement JPEG encoding plus base64 payload shaping for `POST /vision/frame`.
3. Add retry/backoff and drop accounting without unbounded queue growth.
4. Instrument cadence, success/failure, and payload size metrics.

Outputs:

- Stable `vision.frame` pipeline with bounded memory behavior.

Dependencies: WS1, WS0.

### WS4 - Rolling Media Buffers

Goal: create query-context media sources locally without continuous upload.

Tasks:

1. Audio: evolve existing chunked capture into query-addressable rolling buffer semantics.
2. Video: implement rolling H.264 buffer with timestamped segment index.
3. Normalize shared clock/timestamp strategy between audio and video tracks.
4. Define buffer eviction policy to cap memory/storage usage.

Outputs:

- Time-addressable rolling audio and video stores.

Dependencies: WS1, WS0.

### WS5 - Query Bundle Builder and Upload

Goal: create and upload self-contained query bundle after endpointing.

Tasks:

1. On `query.ended`, extract:
   - audio interval: query start to query end,
   - video interval: wake-5s to query end.
2. Finalize audio artifact as WAV and video artifact as MP4.
3. Build multipart request (`metadata`, `audio`, `video`) for `POST /query`.
4. Emit `query.bundle.uploaded` with status/bytes/latency.
5. Enforce bundle-time budget and failure categorization.

Outputs:

- End-to-end query bundle pipeline meeting latency targets.

Dependencies: WS2, WS4, WS0.

### WS6 - WebSocket Control and Assistant Audio Playback

Goal: stabilize bidirectional control signaling and downlink audio playback.

Tasks:

1. Implement WebSocket client lifecycle (`connect`, heartbeat, reconnect backoff, protocol validation).
2. Support required message types and sequencing rules.
3. Implement `assistant.audio_chunk` ingest and playback queueing.
4. Guarantee glasses-preferred route handling and route-loss recovery behavior.
5. Support playback control messages (`start_response`, `stop_response`, `cancel_response`).

Outputs:

- Reliable control plane and assistant audio downlink path.

Dependencies: WS1, WS0.

### WS7 - Reliability, Recovery, and Observability Hardening

Goal: satisfy release blocker reliability criteria.

Tasks:

1. Implement interruption handling strategy:
   - socket drops,
   - route changes,
   - app background/suspend/resume.
2. Add bounded-queue/memory protection checks across upload and buffering.
3. Finalize structured telemetry for all required metrics in PRD.
4. Build failure triage debug surfaces/log views for soak testing.

Outputs:

- Hardened runtime behavior with actionable telemetry.

Dependencies: WS2, WS3, WS4, WS5, WS6.

### WS8 - Acceptance Execution and Release Gate

Goal: run and pass the normative acceptance matrix.

Tasks:

1. Execute `T1-T13` with artifacts required by `PRD_ACCEPTANCE.md`.
2. Track failures to owning workstreams and close regressions.
3. Produce release evidence pack (logs, metrics, pass/fail checklist).
4. Complete final PRD/appendix/acceptance alignment review.

Outputs:

- Release gate sign-off package.

Dependencies: WS7.

## 6. File-Level Ownership Matrix

### Existing files to modify

- `MetaCollectLuigi/ViewModels/StreamSessionViewModel.swift`: orchestrator integration, single activation state binding, lifecycle event wiring.
- `MetaCollectLuigi/Audio/AudioCollectionManager.swift`: rolling buffer query-window extraction support and runtime hooks.
- `MetaCollectLuigi/Views/NonStreamView.swift`: shift from separate controls to one-click activation/deactivation plus debug state.
- `MetaCollectLuigi/Views/StreamView.swift`: playback and runtime status overlay integration.
- `MetaCollectLuigi/ViewModels/WearablesViewModel.swift`: registration/session state bridge to orchestrator.
- `MetaCollectLuigi/MetaCollectLuigiApp.swift`: top-level runtime configuration injection.

### Runtime/service files now present (already added)

- `MetaCollectLuigi/Runtime/RuntimeConfig.swift`
- `MetaCollectLuigi/Runtime/RuntimeTypes.swift`
- `MetaCollectLuigi/Runtime/SessionOrchestrator.swift`
- `MetaCollectLuigi/Runtime/WakeWordEngine.swift`
- `MetaCollectLuigi/Runtime/QueryEndpointDetector.swift`
- `MetaCollectLuigi/Runtime/VisionFrameUploader.swift`
- `MetaCollectLuigi/Runtime/RollingVideoBuffer.swift`
- `MetaCollectLuigi/Runtime/QueryBundleBuilder.swift`
- `MetaCollectLuigi/Runtime/SessionWebSocketClient.swift`
- `MetaCollectLuigi/Runtime/AssistantPlaybackEngine.swift`
- `MetaCollectLuigi/Runtime/EventLogger.swift`

### Remaining high-impact files for release gate hardening

- `MetaCollectLuigi/Runtime/SessionOrchestrator.swift`: health ping/stats emission, lifecycle hooks, error taxonomy propagation.
- `MetaCollectLuigi/Runtime/SessionWebSocketClient.swift`: reconnect observability counters and protocol hardening.
- `MetaCollectLuigi/Runtime/VisionFrameUploader.swift`: retry/backoff, timeout policy, failure classification.
- `MetaCollectLuigi/Runtime/QueryBundleBuilder.swift`: retry/backoff, timeout policy, upload failure categorization.
- `MetaCollectLuigi/Runtime/RollingVideoBuffer.swift`: stronger bounded-memory strategy for soak runs.
- `MetaCollectLuigi/Runtime/AssistantPlaybackEngine.swift`: route verification and route-loss recovery signaling.
- `MetaCollectLuigi/MetaCollectLuigiApp.swift`: foreground/background lifecycle wiring.
- `MetaCollectLuigi/docs/PRD.md`, `MetaCollectLuigi/docs/PRD_ACCEPTANCE.md`: status/evidence synchronization.

## 7. Interface and Type Checklist

### Runtime configuration

- `RuntimeConfig`
  - `visionFrameURL`
  - `queryURL`
  - `webSocketURL`
  - `photoFps`
  - `silenceTimeoutMs`
  - `preWakeVideoMs`
  - `speechRMSThreshold`
  - `speechActivityDebounceMs`

### State and identity

- `SessionState`
- `WakeState`
- `QueryState`
- `PhotoUploadState`
- `VideoBufferState`
- `AudioBufferState`
- `RuntimeState`
- `session_id` and `query_id` generators and propagation rules

### WebSocket contracts

- `WSMessageEnvelope` (`type`, `session_id`, `seq`, `ts_ms`, `payload`)
- Outbound payload types:
  - `session.activate`
  - `session.deactivate`
  - `wakeword.detected`
  - `query.started`
  - `query.ended`
  - `query.bundle.uploaded`
  - `health.ping`
  - `health.stats`
  - `error`
- Inbound payload types:
  - `session.state`
  - `health.pong`
  - `assistant.audio_chunk`
  - `assistant.playback.control`
  - `error`

### HTTP contracts

- `VisionFrameRequest` for `POST /vision/frame`.
- `QueryMetadata` plus multipart builder for `POST /query` (`metadata`, `audio`, `video`).

### Observability contracts

- `AppEvent` (`name`, `session_id`, optional `query_id`, `ts_ms`, `fields`).
- `HealthStatsPayload` aligned to appendix metrics.

## 8. Dependency Graph

Node key:

- `A` WS0 Contract Confirmation
- `B` WS1 Runtime Orchestrator
- `C` WS2 Wake and Query Boundary
- `D` WS3 Continuous Vision Uplink
- `E` WS4 Rolling Media Buffers
- `F` WS5 Query Bundle Builder and Upload
- `G` WS6 WebSocket and Playback
- `H` WS7 Reliability and Observability
- `I` WS8 Acceptance and Release Gate

Edges:

- `A -> B`
- `A -> C`
- `A -> D`
- `A -> E`
- `A -> F`
- `A -> G`
- `B -> C`
- `B -> D`
- `B -> E`
- `B -> G`
- `C -> F`
- `E -> F`
- `C -> H`
- `D -> H`
- `E -> H`
- `F -> H`
- `G -> H`
- `H -> I`

Critical path:

- `A -> B -> E -> F -> H -> I`

## 9. Parallelization Plan by Phase

### Phase P0 - Alignment (short, blocking)

- Run: `A`
- Exit condition: contracts and runtime config baseline confirmed.

### Phase P1 - Foundation (blocking)

- Run: `B`
- Exit condition: one-click activation and unified state machine live.

### Phase P2 - Parallel Build (major parallel window)

- Run in parallel: `C`, `D`, `E`, `G`
- Exit condition:
  - wake/query lifecycle stable,
  - photo uplink stable,
  - rolling buffers stable,
  - websocket/downlink baseline stable.

### Phase P3 - Integration

- Run: `F`
- Exit condition: query bundle creation/upload and lifecycle signaling complete.

### Phase P4 - Hardening

- Run: `H`
- Exit condition: reconnect/resume, bounded resources, complete telemetry.

### Phase P5 - Validation and Ship

- Run: `I`
- Exit condition: `T1-T13` pass with artifacts.

## 10. Acceptance Traceability

| Workstream | Primary FR/NFR Coverage | Acceptance Tests | Required Artifacts |
| --- | --- | --- | --- |
| WS0 | FR-01, FR-02 (contract readiness), NFR-05 | T1, T2 (preconditions) | Contract checklist, runtime config matrix |
| WS1 | FR-03, FR-12, FR-13, NFR-02 | T2, T9, T10 | State transition logs, reconnect lifecycle logs |
| WS2 | FR-04, FR-05, NFR-05 | T3, T4, T5 | `wakeword.detected` (manual), `query.started`, `query.ended` logs |
| WS3 | FR-06, NFR-07 | T7 | Photo cadence logs, upload success/failure logs |
| WS4 | FR-07, FR-08, NFR-03, NFR-09 | T11, T13 | Buffer duration logs, memory/queue boundedness logs |
| WS5 | FR-09, FR-10, NFR-06 | T6, T12b | Bundle creation timing logs, multipart upload logs |
| WS6 | FR-11, FR-12, NFR-04, NFR-02 | T8, T9 | WebSocket heartbeat/reconnect logs, playback route logs |
| WS7 | NFR-01 through NFR-09 | T9, T10, T11, T12 | Soak logs, failure/recovery logs, full telemetry stream |
| WS8 | Release gate completeness | T1-T13 | Pass/fail checklist and evidence pack |

## 10.1 FR and NFR to Code Traceability Baseline

This section locks where each requirement is primarily implemented as of March 1, 2026.

### Functional requirements

- `FR-01` Registration + callback:
  - `MetaCollectLuigi/ViewModels/WearablesViewModel.swift`
  - `MetaCollectLuigi/Views/RegistrationView.swift`
- `FR-02` Permission handling:
  - `MetaCollectLuigi/ViewModels/StreamSessionViewModel.swift` (`activateAssistantRuntime`)
  - `MetaCollectLuigi/Audio/AudioCollectionManager.swift` (`prepareAudioSession`)
  - `Info.plist`
- `FR-03` One-click activation:
  - `MetaCollectLuigi/Views/NonStreamView.swift`
  - `MetaCollectLuigi/ViewModels/StreamSessionViewModel.swift`
  - `MetaCollectLuigi/Runtime/SessionOrchestrator.swift`
- `FR-04` Manual trigger + `wakeword.detected`:
  - `MetaCollectLuigi/Runtime/WakeWordEngine.swift`
  - `MetaCollectLuigi/Runtime/SessionOrchestrator.swift`
  - `MetaCollectLuigi/Views/StreamView.swift`
- `FR-05` VAD silence endpoint:
  - `MetaCollectLuigi/Runtime/QueryEndpointDetector.swift`
  - `MetaCollectLuigi/Audio/AudioCollectionManager.swift`
- `FR-06` 1 FPS vision upload:
  - `MetaCollectLuigi/Runtime/VisionFrameUploader.swift`
  - `MetaCollectLuigi/ViewModels/StreamSessionViewModel.swift`
- `FR-07` Rolling video context:
  - `MetaCollectLuigi/Runtime/RollingVideoBuffer.swift`
  - `MetaCollectLuigi/Runtime/SessionOrchestrator.swift`
- `FR-08` Rolling audio context:
  - `MetaCollectLuigi/Audio/AudioCollectionManager.swift`
  - `MetaCollectLuigi/ViewModels/StreamSessionViewModel.swift`
- `FR-09` Query-time video extraction:
  - `MetaCollectLuigi/Runtime/SessionOrchestrator.swift`
  - `MetaCollectLuigi/Runtime/RollingVideoBuffer.swift`
- `FR-10` Query bundle upload:
  - `MetaCollectLuigi/Runtime/SessionOrchestrator.swift`
  - `MetaCollectLuigi/Runtime/QueryBundleBuilder.swift`
- `FR-11` Assistant downlink playback:
  - `MetaCollectLuigi/Runtime/SessionWebSocketClient.swift`
  - `MetaCollectLuigi/Runtime/AssistantPlaybackEngine.swift`
- `FR-12` Reconnect + resume behavior:
  - `MetaCollectLuigi/Runtime/SessionWebSocketClient.swift`
  - `MetaCollectLuigi/Runtime/SessionOrchestrator.swift`
- `FR-13` Debug runtime surface:
  - `MetaCollectLuigi/Views/NonStreamView.swift`
  - `MetaCollectLuigi/Views/StreamView.swift`
  - `MetaCollectLuigi/ViewModels/StreamSessionViewModel.swift`

### Non-functional requirements

- `NFR-01` Zero crashes in core flow: no dedicated test coverage yet; requires `T1-T13` evidence.
- `NFR-02` Resilient reconnect/resume:
  - partially in `SessionWebSocketClient`; app lifecycle resume wiring still pending.
- `NFR-03` Bounded queue/memory:
  - partially in uploader latest-frame policy and video frame eviction; soak proof pending.
- `NFR-04` Glasses-route playback reliability:
  - basic implementation in `AssistantPlaybackEngine`; route recovery hardening pending.
- `NFR-05` Lifecycle observability with `ts_ms`:
  - event logging in `EventLogger` + orchestrator; health/stats completeness pending.
- `NFR-06` Bundle latency target:
  - clip creation/upload implemented; latency budget enforcement and evidence pending.
- `NFR-07` Photo bandwidth sustainability:
  - 1 FPS upload pipeline implemented; long-run bandwidth evidence pending.
- `NFR-08` Battery/CPU sustainability:
  - not yet characterized; requires prolonged acceptance runs.
- `NFR-09` Rolling buffer memory bounds:
  - partial (eviction by duration); boundedness evidence for T13 pending.

## 11. Suggested Team Lanes (Parallel Execution)

### Lane 1 - Runtime and Control

- Owns: `B`, `G`, portions of `H`
- Skills: app lifecycle, websocket resilience, playback routing.

### Lane 2 - Wake and Audio Intelligence

- Owns: `C`, audio portions of `E`, portions of `F`
- Skills: low-latency audio, manual trigger path, endpointing.

### Lane 3 - Vision and Media Packaging

- Owns: `D`, video portions of `E`, portions of `F`
- Skills: frame pipelines, encoding, timestamped media extraction.

### Lane 4 - QA, Observability, and Reliability

- Owns: `H`, `I`
- Skills: soak testing, metrics validation, failure triage.

## 12. Milestone Checklist (Execution Order)

1. Confirm backend and media contract baseline (`A`).
2. Land unified runtime orchestrator and one-click activation (`B`).
3. Land parallel streams (`C`, `D`, `E`, `G`) with integration stubs.
4. Land query bundle extraction plus multipart upload (`F`).
5. Complete reliability hardening and recovery (`H`).
6. Pass acceptance matrix and compile release evidence (`I`).

## 13. Delivery Definition of Done

All must be true:

- Functional requirements `FR-01` to `FR-13` are demonstrably implemented.
- Non-functional requirements `NFR-01` to `NFR-09` are evidenced by logs/metrics.
- Acceptance matrix `T1-T13` passes with required artifacts.
- No unresolved P0/P1 defects in wake/query/upload/playback/recovery paths.

## 14. Assumptions and Defaults

- Backend auth is not included in MVP.
- Silence timeout default: `5000ms`.
- Pre-wake video context: `5000ms`.
- Photo upload target cadence: `1 FPS`.
- Background continuity is best-effort; resume/reconnect is mandatory after suspension.
- Automatic wake-word detection is out of scope for v4 and tracked for v4.1+.

## 15. Open Questions (Non-Blocking for MVP)

- Final VAD threshold tuning profile for noisy environments. *(RMS threshold and debounce are now configurable via `RuntimeConfig`; environment-specific preset values remain open.)*
- Final video encoding tuning (bitrate, keyframe interval, quality).
- Final retention and deletion policy for uploaded frames and query bundles (backend-side).
- Final battery and CPU threshold budget for extended sessions.

## 16. Reference Sources

### Local docs

- `docs/PRD.md`
- `docs/PRD_APPENDIX_INTERFACES.md`
- `docs/PRD_ACCEPTANCE.md`
- `docs/CONTEXT.md`
- `docs/Wearables DAT SDK.md`

### External docs

- Meta Wearables iOS SDK README: <https://raw.githubusercontent.com/facebook/meta-wearables-dat-ios/main/README.md>
- Meta Wearables iOS SDK changelog: <https://raw.githubusercontent.com/facebook/meta-wearables-dat-ios/main/CHANGELOG.md>
- Meta Wearables session lifecycle docs: <https://wearables.developer.meta.com/docs/lifecycle-events>
- Apple URLSession WebSocket API: <https://developer.apple.com/documentation/foundation/urlsessionwebsockettask>
- Apple AVAudioSession HFP option: <https://developer.apple.com/documentation/avfaudio/avaudiosession/categoryoptions-swift.struct/allowbluetoothhfp>
- Apple AVAssetWriter API: <https://developer.apple.com/documentation/avfoundation/avassetwriter>

## 17. Acceptance Artifact Directory Convention

Release evidence for v4 is stored under:

- `docs/evidence/v4/`

Required structure:

- `docs/evidence/v4/README.md` - index and run log.
- `docs/evidence/v4/checklists/` - test matrix pass/fail checklists (`T1-T13`, `T12b`).
- `docs/evidence/v4/logs/` - timestamped runtime and event logs.
- `docs/evidence/v4/metrics/` - cadence/latency/reconnect summary tables.
- `docs/evidence/v4/media/` - optional screenshots or short validation clips.

Naming convention:

- Run folder: `run-YYYYMMDD-HHMM/` (24-hour local time).
- Files prefixed by test id, for example:
  - `T7-photo-cadence.json`
  - `T9-reconnect.log`
  - `T12b-bundle-latency.csv`
