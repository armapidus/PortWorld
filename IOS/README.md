# MetaCollectLuigi

**Son of Anton** — An iOS companion app for Meta Ray-Ban Gen 2 smart glasses, enabling hands-free voice-activated workflows with AI-powered visual context.

## Overview

MetaCollectLuigi is designed for professionals who need hands-free assistance while working—initially targeting plumbers who often have their hands occupied. The app leverages Meta Ray-Ban Gen 2 glasses to provide:

- **Continuous visual context** — Captures frames for real-time scene understanding
- **Voice-activated queries** — Wake word detection triggers AI assistance
- **Audio streaming** — Two-way audio between glasses and backend AI
- **Local media buffering** — Rolling video and audio capture for query context

## Features

### Implemented

- **Meta Registration** — OAuth-style authentication via Meta AI app callback
- **Device Discovery** — Automatic detection of compatible Meta wearables
- **Live Video Streaming** — Real-time feed from glasses camera (low resolution, 24 fps)
- **Photo Capture** — JPEG capture with preview and iOS share sheet
- **Audio Collection** — Bluetooth HFP capture at 8 kHz mono PCM16 in 500ms chunks
- **Audio Persistence** — WAV chunks stored locally with metadata indexing
- **Permission Handling** — Graceful camera and microphone permission flows
- **Error Recovery** — Comprehensive error handling and user feedback

### Planned

- One-tap activation (connection + wake word + capture)
- Porcupine wake-word detection ("Hey Mario")
- VAD-based query end detection (5s silence timeout)
- 1 FPS photo upload to vision endpoint
- Local rolling video buffer (H.264)
- Query bundle creation and upload
- WebSocket client for control and audio downlink
- Assistant audio playback to glasses speakers

## Requirements

### Hardware

- iPhone running iOS 17.0+
- Meta Ray-Ban Gen 2 smart glasses

### Development

- Xcode 15.0+
- Swift 5.0
- Apple Developer account with appropriate entitlements

### Meta Developer Setup

You'll need to configure the following in your build settings:

| Setting | Description |
|---------|-------------|
| `META_APP_ID` | Your Meta application ID |
| `CLIENT_TOKEN` | Meta client token |
| `DEVELOPMENT_TEAM` | Apple Developer Team ID |

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-username/MetaCollectLuigi.git
   cd MetaCollectLuigi
   ```

2. **Open in Xcode**
   ```bash
   open MetaCollectLuigi.xcodeproj
   ```

3. **Configure Meta credentials**
   
   Update the build settings with your Meta App ID and Client Token from the [Meta Developer Portal](https://developers.facebook.com/).

4. **Build and run**
   
   Select your target device and run the project (⌘R).

## Architecture

The app follows the **MVVM** (Model-View-ViewModel) pattern with SwiftUI and Combine.

```
MetaCollectLuigi/
├── MetaCollectLuigiApp.swift      # App entry point & SDK configuration
├── Views/                          # SwiftUI views
│   ├── MainAppView.swift          # Root navigation controller
│   ├── HomeScreenView.swift       # Onboarding & connection
│   ├── RegistrationView.swift     # Meta OAuth callback handler
│   ├── StreamSessionView.swift    # Stream state router
│   ├── StreamView.swift           # Live video feed & controls
│   ├── NonStreamView.swift        # Pre-stream setup & audio controls
│   ├── PhotoPreviewView.swift     # Captured photo preview
│   └── Components/                # Reusable UI components
├── ViewModels/
│   ├── WearablesViewModel.swift   # DAT SDK & device management
│   └── StreamSessionViewModel.swift # Streaming & audio state
├── Audio/
│   ├── AudioCollectionManager.swift  # AVAudioEngine capture
│   ├── AudioCollectionTypes.swift    # State & metadata types
│   └── WavFileWriter.swift           # WAV file encoding
└── docs/                           # Product documentation
```

### Key Components

| Component | Responsibility |
|-----------|----------------|
| **WearablesViewModel** | Meta DAT SDK integration, device discovery, registration flow |
| **StreamSessionViewModel** | Video streaming, photo capture, audio collection coordination |
| **AudioCollectionManager** | Bluetooth HFP audio routing, chunk-based recording |

### Dependencies

- [meta-wearables-dat-ios](https://github.com/facebook/meta-wearables-dat-ios) v0.4.0 — Meta Wearables Device Access Toolkit

## User Flow

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  HomeScreenView │────▶│  RegistrationView │────▶│  NonStreamView  │
│   (Onboarding)  │     │  (Meta OAuth)     │     │  (Setup)        │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                                                          ▼
                                                ┌─────────────────┐
                                                │   StreamView    │
                                                │ (Live Capture)  │
                                                └─────────────────┘
```

1. **Unregistered** — User sees tips and "Connect my glasses" button
2. **Registration** — Redirects to Meta AI app, handles callback
3. **Pre-Stream** — Device detection, audio setup, "Start streaming" button
4. **Streaming** — Live video feed with photo capture and controls

## Permissions

The app requires the following permissions:

| Permission | Usage |
|------------|-------|
| Bluetooth | Connect to Meta Ray-Ban glasses |
| Microphone | Capture audio from glasses |
| Photo Library | Save captured photos |

## Configuration

### URL Schemes

- `metacollectluigi://` — Custom scheme for Meta OAuth callback
- `fb-viewapp` — Queried scheme for Meta app detection

### Background Modes

- `bluetooth-peripheral` — Maintain glasses connection
- `external-accessory` — Meta wearables protocol support

### Entitlements

- Associated Domains: `applinks:www.didro.dev`

## Documentation

Additional documentation is available in the `docs/` directory:

- [PRD.md](MetaCollectLuigi/docs/PRD.md) — Product Requirements Document
- [CONTEXT.md](MetaCollectLuigi/docs/CONTEXT.md) — Project context and background
- [IMPLEMENTATION_PLAN.md](MetaCollectLuigi/docs/IMPLEMENTATION_PLAN.md) — Technical implementation details

## Local Mock Backend

For v4 reliability loops (tests deferred), use the local Python mock backend:

```bash
./tools/mock_backend/run.sh
```

References:
- [tools/mock_backend/README.md](tools/mock_backend/README.md)
- [MetaCollectLuigi/docs/evidence/v4/MOCK_VALIDATION_RUNBOOK.md](MetaCollectLuigi/docs/evidence/v4/MOCK_VALIDATION_RUNBOOK.md)

## Open Source Backend Setup (Lean)

For contributors, networking is now configured with one base URL plus path defaults in `Info.plist`:

- `SON_BACKEND_BASE_URL` (example: `http://127.0.0.1:8080`)
- `SON_WS_PATH` (default: `/ws/session`)
- `SON_VISION_PATH` (default: `/vision/frame`)
- `SON_QUERY_PATH` (default: `/query`)

Optional auth:

- `SON_API_KEY` -> sent as header `X-API-Key`
- `SON_BEARER_TOKEN` -> sent as header `Authorization: Bearer ...`

Optional explicit endpoint overrides (advanced only):

- `SON_WS_URL`
- `SON_VISION_URL`
- `SON_QUERY_URL`

Verification:

1. Launch app and activate runtime.
2. Check Runtime Status panel.
3. Confirm `Backend:` line matches your target host/paths.

Note: the iOS client currently uses the v4 contracts (`/vision/frame`, `/query`, `ws/session`). If your backend exposes a different API shape, add an adapter/proxy preserving those contracts.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is proprietary software. All rights reserved.

## Acknowledgments

- [Meta Wearables DAT SDK](https://github.com/facebook/meta-wearables-dat-ios) for glasses integration
- Built during a hackathon with focus on hands-free AI assistance
