# PortWorld iOS — Architecture (v1.0)

> **Status:** Target architecture. The current codebase is the hackathon baseline;
> the implementation plan in `IMPLEMENTATION_PLAN.md` describes how to reach this state.

---

## 1. Guiding Principles

1. **Single responsibility per module.** Each Swift file owns one concept. No God-ViewModels.
2. **Dependency injection over lazy singletons.** Every major service is passed in; nothing is created inside a class it cannot be tested without.
3. **One concurrency model.** `@MainActor` for UI state; Swift `actor` for thread-isolated services; `async/await` for all network calls. No bare `DispatchQueue` except inside the audio engine tap (AVFoundation requirement).
4. **Shared resources have a single owner.** `AVAudioSession` is arbitrated by `AudioSessionArbiter`. `AVAudioEngine` is owned by `AudioCollectionManager` and shared read-only with `AssistantPlaybackEngine`.
5. **Observable state is colocated.** All `@Published` / `@Observable` properties that drive UI live in `SessionStateStore`. Views read from the store; they do not reach into service classes.
6. **No secrets in source.** All backend URLs and API credentials are injected via xcconfig variables and read from Info.plist at runtime. Never committed.
7. **Production-safe logging.** All diagnostics use `os_log` or are gated by `#if DEBUG`. No bare `print()` in release builds.

---

## 2. Module Map

```
IOS/PortWorld/
├── App/
│   └── PortWorldApp.swift          @main — SDK init, root WindowGroup
│
├── DesignSystem/
│   ├── Colors.swift                Semantic colour tokens (light + dark)
│   ├── Typography.swift            Type scale (title/body/caption/label)
│   ├── Spacing.swift               Grid constants (4pt base grid)
│   └── Icons.swift                 SF Symbol name enum
│
├── Views/
│   ├── Onboarding/
│   │   ├── OnboardingContainerView.swift   Paged onboarding; permission requests
│   │   ├── OnboardingPage1View.swift       Value proposition
│   │   ├── OnboardingPage2View.swift       Microphone + speech permissions
│   │   └── OnboardingPage3View.swift       Connect glasses CTA
│   ├── Pairing/
│   │   └── DevicePairingView.swift         Animated connection state ring
│   ├── Session/
│   │   ├── SessionContainerView.swift      Root: onboarding ↔ pairing ↔ active session
│   │   ├── StandbyView.swift               Pre-activation — hold-to-activate card
│   │   ├── LiveSessionView.swift           Full-screen camera feed + HUD
│   │   └── SessionHUDView.swift            Status pill; chime ring animation
│   ├── Settings/
│   │   └── SettingsView.swift              Preferences + developer section
│   ├── Common/
│   │   ├── CircleButton.swift
│   │   ├── PrimaryButton.swift
│   │   ├── StatusBadge.swift
│   │   └── WaveformView.swift              Animated audio waveform pill
│   └── Photo/
│       └── PhotoPreviewView.swift          Full-screen preview + explicit share/save
│
├── ViewModels/
│   ├── SessionStateStore.swift     @Observable store for all UI-facing session state
│   ├── WearablesViewModel.swift    DAT SDK registration + device discovery
│   └── OnboardingViewModel.swift   Permission flow state machine
│
├── Coordinators/
│   ├── DeviceSessionCoordinator.swift  DAT StreamSession, photo capture, frame forwarding
│   └── RuntimeCoordinator.swift        Wires DeviceSessionCoordinator → SessionOrchestrator; owns AudioCollectionManager; scene-phase lifecycle
│
├── Runtime/
│   ├── SessionOrchestrator.swift       Central pipeline coordinator (see §4)
│   ├── SessionWebSocketClient.swift    Swift actor; WS connect/ping/reconnect
│   ├── WakeWordEngine.swift            Protocol + ManualWakeWordEngine + SFSpeechWakeWordEngine
│   ├── QueryEndpointDetector.swift     Silence-timeout VAD; actor-isolated timer
│   ├── QueryBundleBuilder.swift        async/await multipart POST /query
│   ├── VisionFrameUploader.swift       async/await 1 FPS POST /vision/frame
│   ├── RollingVideoBuffer.swift        UIImage → H.264 MP4; temp file cleanup
│   ├── AssistantPlaybackEngine.swift   AVAudioPlayerNode on shared engine
│   ├── EventLogger.swift               Circular in-memory + JSONL on-disk log
│   └── RuntimeConfig.swift             Reads SON_* keys from Info.plist
│
├── Audio/
│   ├── AudioSessionArbiter.swift       Single owner of AVAudioSession category
│   ├── AudioCollectionManager.swift    AVAudioEngine, HFP tap, WAV chunks
│   ├── AudioCollectionTypes.swift      State enums and metadata types
│   └── WavFileWriter.swift             Static RIFF WAV writer
│
├── Utilities/
│   ├── Clocks.swift                    Clocks.nowMs() — single timestamp source
│   ├── KeychainCredentialStore.swift   Secure credential persistence
│   └── NWReachability.swift            NWPathMonitor wrapper; async publisher
│
└── Runtime/
    └── RuntimeTypes.swift              Protocol types, WS payload structs, codec
```

---

## 3. Layering and Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│  Views  (read SessionStateStore; trigger actions on VMs)     │
└────────────────────────┬────────────────────────────────────┘
                         │ @Observable bindings
┌────────────────────────▼────────────────────────────────────┐
│  ViewModels + SessionStateStore  (@MainActor)                │
│  WearablesViewModel  OnboardingViewModel  SessionStateStore  │
└────────────────────────┬────────────────────────────────────┘
                         │ delegate/async calls
┌────────────────────────▼────────────────────────────────────┐
│  Coordinators  (@MainActor)                                  │
│  DeviceSessionCoordinator      RuntimeCoordinator            │
└────────────────────────┬────────────────────────────────────┘
                         │ frames / audio PCM / lifecycle
┌────────────────────────▼────────────────────────────────────┐
│  Runtime Services                                            │
│  SessionOrchestrator  AudioCollectionManager                 │
│  AssistantPlaybackEngine  AudioSessionArbiter                │
└────────────────────────┬────────────────────────────────────┘
                         │ network I/O
┌────────────────────────▼────────────────────────────────────┐
│  Transport                                                   │
│  SessionWebSocketClient   QueryBundleBuilder                 │
│  VisionFrameUploader      NWReachability                     │
└─────────────────────────────────────────────────────────────┘
```

### Full End-to-End Pipeline

```
DAT Camera (24fps UIImage)
  ─► DeviceSessionCoordinator.handleFrame()
       ├─► RollingVideoBuffer.append()        [local H.264 ring buffer]
       └─► VisionFrameUploader.submit()       [rate-limited to 1fps; async/await]
                                              POST /vision/frame

Bluetooth HFP (AVAudioEngine inputTap)
  ─► AudioCollectionManager
       ├─► AudioChunkProcessor                [500ms WAV chunks → disk]
       ├─► RMS speech-activity                [publishes lastSpeechActivityMs]
       │     ─► SessionOrchestrator.recordSpeechActivity()
       │     ─► QueryEndpointDetector.recordSpeechActivity()
       └─► PCM frame                          [→ SFSpeechWakeWordEngine]

Wake Detection
  ManualWakeWordEngine.triggerManualWake()  [button / hold-to-activate]
  SFSpeechWakeWordEngine transcript match   ["hey mario" + variants]
    ─► SessionOrchestrator.handleWakeDetected()
         ├─► AssistantPlaybackEngine.cancelResponse()
         ├─► play 660Hz chime
         ├─► WS send: wakeword.detected
         └─► QueryEndpointDetector.beginQuery()

Query Active
  QueryEndpointDetector silence timer (200ms tick, default 5s timeout)
    ─► SessionOrchestrator.handleQueryEnded()
         ├─► play 880Hz chime
         ├─► WS send: query.ended
         ├─► AudioCollectionManager.flushPendingChunks()
         ├─► AudioCollectionManager.exportWAVClip(window)   ─► WAV file
         ├─► RollingVideoBuffer.exportInterval(wake-5s..end) ─► MP4 file
         ├─► QueryBundleBuilder.uploadBundle(meta, wav, mp4) POST /query
         │     └─► on success: WS send: query.bundle.uploaded
         └─► temp file cleanup (WAV + MP4 deleted after successful upload)

WebSocket Downlink
  assistant.audio_chunk
    ─► AssistantPlaybackEngine.appendChunk()
         ─► AVAudioPlayerNode.scheduleBuffer()
              ─► HFP route → glasses speakers

  assistant.playback.control  ─► cancel / stop / start response
  session.state               ─► SessionStateStore update
  health.pong                 ─► acknowledged

Health Emission (every 10s)
  SessionOrchestrator ─► WS send: health.stats
    { ws_latency_ms, audio_buffer_duration_ms, frame_drop_rate,
      reconnect_attempts, app_version, device_model, os_version }
```

---

## 4. `SessionOrchestrator` — Detailed Design

`SessionOrchestrator` is the central runtime coordinator. It owns no UI state and no network transport directly — both are injected.

### Dependencies struct (injected at init)

```swift
struct Dependencies {
    var webSocketClient: SessionWebSocketClientProtocol
    var visionFrameUploader: VisionFrameUploaderProtocol
    var rollingVideoBuffer: RollingVideoBufferProtocol
    var queryBundleBuilder: QueryBundleBuilderProtocol
    var eventLogger: EventLoggerProtocol
    var audioBufferDurationProvider: () -> Int        // capture queue depth
    var clock: () -> Int64                            // Clocks.nowMs()

    static var live: Dependencies { /* default production values */ }
}
```

### State machine

```
          ┌────────────┐
          │   idle     │◄──────────────────────────────────────┐
          └─────┬──────┘                                       │
         activate()                                      deactivate()
                │                                             │
          ┌─────▼──────┐                             ┌────────┴───────┐
          │ connecting │                             │   deactivating │
          └─────┬──────┘                             └────────────────┘
         WS connected                                         ▲
                │                                             │
          ┌─────▼──────┐       socket drop              ┌────┴───────┐
          │   active   │──────────────────────────────►  │reconnecting│
          └─────┬──────┘                                └────────────┘
          wake detected                                       │
                │                                      path restored
          ┌─────▼──────┐                                     │
          │  querying  │◄─────────────────────────────────────┘
          └─────┬──────┘
         silence timeout / forceEnd
                │
          ┌─────▼──────────┐
          │ uploading_bundle│
          └─────┬───────────┘
         upload complete / failed
                │
          back to active ──► repeat
```

### Outbound message buffer

During `reconnecting`, outbound messages (wake events, query events, health stats) are held in an in-memory queue (max 20 messages, FIFO). On reconnect, buffered messages are drained in order before resuming normal emission. Messages older than 60s are discarded.

---

## 5. Audio Session Ownership

`AudioSessionArbiter` is the single point of `AVAudioSession` category configuration.

```
AudioSessionArbiter (singleton)
  ├── requestSession(for: .playAndRecordHFP)  ← AudioCollectionManager
  │     configures .playAndRecord + allowBluetoothHFP + allowBluetooth
  └── returns the configured session lease

AssistantPlaybackEngine
  attaches its playerNode to the shared AVAudioEngine (no session reconfiguration)

DeveloperPipelineTester (dev scheme only)
  requestSession(for: .playback)  ← only valid when capture is not leased
```

Rules:
- Only `AudioCollectionManager` holds the `.playAndRecord` lease during an active session.
- `AssistantPlaybackEngine` never reconfigures the category — it relies on the lease already set.
- Playback-only tools (dev pipeline tester) can only acquire a lease when no capture lease is held.

---

## 6. Concurrency Model

| Layer | Model | Rationale |
|-------|-------|-----------|
| All Views | `@MainActor` | SwiftUI requirement |
| `SessionStateStore` | `@MainActor @Observable` | binds to views |
| `WearablesViewModel`, `OnboardingViewModel` | `@MainActor @ObservableObject` | DAT SDK callbacks arrive on main |
| `DeviceSessionCoordinator`, `RuntimeCoordinator` | `@MainActor final class` | orchestrate UI-touching state |
| `SessionOrchestrator` | `@MainActor final class` | drives state machine; all callbacks arrive here |
| `SessionWebSocketClient` | `actor` | protects URLSession task isolation |
| `QueryEndpointDetector` | `actor` | timer + state isolated from main |
| `AudioCollectionManager` / `AudioChunkProcessor` | `@MainActor` + inner `DispatchQueue` for AVAudioEngine tap | AVFoundation tap runs on audio thread; all observable state back on main |
| `AssistantPlaybackEngine` | `@MainActor` | player graph managed on main |
| `VisionFrameUploader` | `actor` | upload-in-flight flag; async/await |
| `RollingVideoBuffer` | `actor` | frame ring and AVAssetWriter isolated |
| `QueryBundleBuilder` | stateless `struct` + task | no stored state; cancellable via `Task` |
| `EventLogger` | `@MainActor` | observers always on main |
| `AudioSessionArbiter` | `actor` | single serialised entry point |

**Banned patterns in this codebase:**
- `DispatchQueue.sync` outside audio tap
- Bare `print()` in non-`#if DEBUG` context
- `@unchecked Sendable` except in `AudioChunkProcessor` (documented exception)
- `try?` that silently discards errors on I/O paths

---

## 7. Configuration and Secrets

All runtime configuration is loaded by `RuntimeConfig.load(from:)` from Info.plist.

| Info.plist key | xcconfig variable | Description |
|---------------|-------------------|-------------|
| `SON_BACKEND_BASE_URL` | `BACKEND_BASE_URL` | Base HTTP URL; ws/wss derived |
| `SON_WS_PATH` | `WS_PATH` | WebSocket path (default `/ws/session`) |
| `SON_VISION_FRAME_PATH` | `VISION_FRAME_PATH` | POST path |
| `SON_QUERY_PATH` | `QUERY_PATH` | POST path |
| `SON_API_KEY` | `API_KEY` | From Keychain after first launch |
| `SON_SILENCE_TIMEOUT_MS` | `SILENCE_TIMEOUT_MS` | Default `5000` |
| `SON_VIDEO_PRE_WAKE_SECONDS` | `VIDEO_PRE_WAKE_S` | Default `5` |

**Developer override:** create `Config.local.xcconfig` (gitignored) and set `BACKEND_BASE_URL = http://192.168.x.x:8080`. Never commit a LAN IP.

---

## 8. Persistence and Storage

| Data | Storage | Lifecycle |
|------|---------|-----------|
| API credentials | Keychain (`kSecClassGenericPassword`) | Persistent; user can clear in Settings |
| User preferences (silence timeout, wake phrase) | `UserDefaults` | Persistent |
| WAV chunk files | `FileManager.temporaryDirectory/chunks/` | Deleted after successful query upload; swept on launch |
| MP4 query clips | `FileManager.temporaryDirectory/clips/` | Deleted after successful upload; swept on launch |
| Event log JSONL | `FileManager.default.applicationSupportDirectory/logs/events-N.jsonl` | Rolling, max 5MB per file, 3 files retained |
| Developer export | User-chosen path via `UIDocumentPickerViewController` | User-controlled |

---

## 9. Navigation Structure

```
PortWorldApp
└── WindowGroup
    └── SessionContainerView  (@MainActor, reads WearablesViewModel + SessionStateStore)
         ├── OnboardingContainerView     (isOnboardingComplete == false)
         │    ├── OnboardingPage1View
         │    ├── OnboardingPage2View   ← requests mic + speech permissions
         │    └── OnboardingPage3View   ← registration CTA; onOpenURL handler here
         ├── DevicePairingView          (onboarded, device not connected)
         ├── StandbyView                (device connected, session inactive)
         │    └── .sheet → SettingsView
         └── LiveSessionView            (session active)
              └── .sheet → PhotoPreviewView
```

---

## 10. Design System

All visual tokens are defined in `DesignSystem/`. Views import nothing directly from `UIKit`.

### Colour roles (adaptive — light + dark)

| Token | Purpose |
|-------|---------|
| `DS.Colors.background` | App background |
| `DS.Colors.surface` | Card / sheet surface |
| `DS.Colors.surfaceElevated` | Elevated surface (modals) |
| `DS.Colors.primary` | Interactive / brand accent |
| `DS.Colors.destructive` | Destructive actions |
| `DS.Colors.labelPrimary` | Body text |
| `DS.Colors.labelSecondary` | Secondary/supporting text |
| `DS.Colors.labelTertiary` | Hints / timestamp text |

### Type scale

| Token | Size | Weight | Usage |
|-------|------|--------|-------|
| `DS.Type.largeTitle` | 34 | Regular | Screen titles |
| `DS.Type.title1` | 28 | Bold | Section headers |
| `DS.Type.body` | 17 | Regular | Body copy |
| `DS.Type.callout` | 16 | Medium | Chips / badges |
| `DS.Type.caption` | 12 | Regular | Timestamps; hints |

All text supports Dynamic Type via `.font(.custom(...).dynamic())`.

### Motion

- All state transitions use `withAnimation(.spring(duration: 0.35))`.
- No third-party animation libraries.
- Onboarding page transitions: `AnyTransition.asymmetric(insertion: .move(edge: .trailing), removal: .move(edge: .leading))`.

---

## 11. Error Handling Strategy

Every error surface has three properties:
1. **User message** — short, friendly, actionable (`"Connection lost. Tap to retry."`)
2. **CTA** — a button (`"Retry"`, `"Reconnect"`, `"Open Settings"`)
3. **Log event** — written to `EventLogger` with full technical detail

Raw system error strings (e.g. `"The operation couldn't be completed (NSURLErrorDomain error -1009)"`) are never shown to users.

`SessionStateStore` holds `var alertError: SessionError?` which the root view hierarchy observes as an `.alert` modifier.

---

## 12. App Store Compliance Checklist

- [ ] `NSMicrophoneUsageDescription` — present and meaningful
- [ ] `NSSpeechRecognitionUsageDescription` — present and meaningful
- [ ] `NSCameraUsageDescription` — present and meaningful (DAT SDK)
- [ ] `UIBackgroundModes` — includes `audio`
- [ ] `NSAppTransportSecurity` — `NSAllowsLocalNetworking: true` only in Debug scheme; release scheme uses HTTPS-only
- [ ] Privacy manifest (`PrivacyInfo.xcprivacy`) — declares all accessed API categories
- [ ] No LAN IPs committed to repo
- [ ] No API keys in source or Info.plist (xcconfig injection only)
- [ ] Unused `applinks` entitlement removed
- [ ] Minimum deployment target: iOS 17.0
