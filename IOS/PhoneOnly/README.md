# PhoneOnly

Reference-only standalone source slice for the current working phone-only assistant runtime.

Included:
- app entry and root view
- phone-only runtime view model and store
- wake detection, backend websocket client, phone audio, and playback
- audio capture support used by the current runtime

Deliberately excluded:
- DAT / Meta wearables onboarding
- device session coordinator
- camera / photo / video upload flows
- archived assistant runtime stack

To make this buildable as its own app target, wire these sources into a separate Xcode target and provide:
- `Info.plist` keys:
  - `SON_BACKEND_BASE_URL`
  - `SON_WS_PATH` or `SON_WS_URL`
  - optional `SON_API_KEY`
  - optional `SON_BEARER_TOKEN`
  - optional wake-word overrides (`SON_WAKE_PHRASE`, `SON_SLEEP_PHRASE`, `SON_WAKE_MODE`, `SON_WAKE_LOCALE`)
- iOS permission strings:
  - `NSMicrophoneUsageDescription`
  - `NSSpeechRecognitionUsageDescription`
