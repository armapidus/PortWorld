# SwiftUI File Mapping And UI Refresh Plan

Status: active working plan

Last updated: 2026-03-13

Related docs:

- `docs/IOS_APP_UX_SPEC.md`
- `docs/IOS_APP_IMPLEMENTATION_PLAN.md`

## Summary

- Replace the current runtime-first shell with an onboarding-first router, while reusing the existing assistant runtime and wearables manager under the hood.
- Reuse the existing splash, runtime controller, wearables state, and a few button/card patterns; replace the current runtime console, glasses sheet flow, and blue-heavy visual styling.
- Adopt a strict monochrome theme: black, charcoal, graphite, soft gray, white, and system red only for destructive actions.

## Key Changes

### Root shell replacement

- Replace `IOS/PortWorld/Views/MainAppView.swift` as the app router.
- Stop presenting `IOS/PortWorld/Views/AssistantRuntimeView.swift` immediately on launch.
- Stop using a sheet for glasses setup.
- Keep `IOS/PortWorld/PortWorldApp.swift` as the app entry point.
- Keep `WearablesRuntimeManager` ownership and `.onOpenURL` callback handling in `PortWorldApp.swift`.

### Keep and reuse

- Reuse `IOS/PortWorld/Views/StartupLoadingView.swift` as the splash layer, with only monochrome cleanup if needed.
- Reuse `IOS/PortWorld/ViewModels/AssistantRuntimeViewModel.swift` as the bridge into assistant activation, deactivation, wearables readiness, and wake/sleep runtime behavior.
- Reuse `IOS/PortWorld/FutureHardware/Runtime/WearablesRuntimeManager.swift` as the source of Meta registration, discovery, compatibility, and session readiness.
- Reuse `IOS/PortWorld/Runtime/Config/AssistantRuntimeConfig.swift` as the runtime config constructor, but refactor it later to accept app-managed settings overrides instead of relying only on bundle values.
- Reuse `IOS/PortWorld/Views/Components/CustomButton.swift` and `IOS/PortWorld/Views/Components/TipRowView.swift` as styleable primitives after a monochrome redesign.

### Replace or heavily rewrite

- Replace `IOS/PortWorld/Views/AssistantRuntimeView.swift` with the new minimal home screen for normal users.
- Remove its developer panels, route picker, subsystem stats, and blue gradient from the shipping path.
- Replace `IOS/PortWorld/FutureHardware/Views/FutureHardwareSetupView.swift` as a standalone sheet flow.
- Reuse its initialization and retry subviews inside the onboarding Meta step if useful.
- Rewrite `IOS/PortWorld/FutureHardware/Views/HomeScreenView.swift` into the new Meta connection screen.
- Reuse its progress-row and status-card ideas, but remove phone-route copy, mock-device prominence, and developer-readiness framing.
- De-emphasize or retire `IOS/PortWorld/Views/Components/CircleButton.swift` from the main UX.

### Add new app-facing state and services

- Add an onboarding state store that persists:
  - welcome seen
  - backend validated
  - Meta completed or skipped
  - wake practice completed
  - profile completed
  - fully onboarded
- Add an app settings store that persists:
  - backend base URL
  - bearer token
  - backend validation result
  - hidden advanced overrides if they remain supported
- Add a small HTTP client layer for:
  - `/healthz`
  - `/readyz`
  - `GET /profile`
  - `PUT /profile`
- Add a home-readiness model derived from backend validation, wearables readiness, and current assistant runtime state.

### New screen inventory

- Add `WelcomeView`
- Add `BackendSetupView`
- Build `MetaConnectionView` by reusing the DAT state machinery and selected UI patterns from the current `HomeScreenView`
- Add `WakePracticeView`
- Add `ProfileInterviewView`
- Add `ProfileConfirmationView`
- Add `HomeView`
- Add `SettingsView`
- Add `HelpView`

### Theme and component system

- Replace the inline blue gradients in `AssistantRuntimeView.swift` and `HomeScreenView.swift` with a monochrome surface system.
- Replace the current `appPrimaryColor` asset and the purple destructive palette with semantic neutral tokens:
  - background
  - surface
  - elevated surface
  - primary text
  - secondary text
  - border
  - disabled fill
  - destructive
- Keep `StartupLoadingView` black-led.
- All other screens should use charcoal and graphite surfaces with white or near-white text, plus system red only for destructive intent.
- Centralize the theme in one new SwiftUI theme/token file instead of continuing to hardcode colors inside view bodies.

### Migration order

#### Phase 1 mapping

- Route `MainAppView.swift` through splash, onboarding state, and placeholder home.
- Keep the old runtime screen reachable only from an internal fallback path if needed.

#### Phase 2 mapping

- Add Welcome and Backend Setup.
- Refactor `AssistantRuntimeConfig.swift` to consume persisted settings.

#### Phase 3 mapping

- Transform `HomeScreenView.swift` into `MetaConnectionView`.
- Absorb the useful initialization and error states from `FutureHardwareSetupView.swift`.

#### Phase 4 mapping

- Add Wake Practice using `AssistantRuntimeViewModel.swift` as the runtime bridge.

#### Phase 5 mapping

- Add Profile Interview using a backend-owned onboarding session mode and auto-complete handoff.
- Swap in the final monochrome `HomeView`.

## Test Plan

- Launch still shows the existing splash and then routes to onboarding rather than the runtime console.
- Backend setup can validate a reachable backend and reject a bad URL or bad bearer token.
- Meta callback still works through the existing `PortWorldApp` URL path after the shell rewrite.
- Skipping Meta setup still allows routing forward, but home activation remains disabled until glasses readiness is satisfied.
- Wake Practice can observe real wake and sleep success counts without exposing developer panels.
- Profile onboarding can persist the expanded backend profile schema without a separate review screen.
- Re-theming removes blue, orange, and purple from user-facing screens and shared button styles, while preserving readability and destructive affordances.

## Assumptions

- The existing runtime and wearables managers remain the core engines.
- The legacy runtime console may temporarily remain available behind an internal-only fallback during migration, but it is no longer part of normal user navigation.
- The new visual direction is strictly monochrome.
- No backend API changes are needed beyond adding the iOS-side HTTP client layer for endpoints that already exist.
