# iOS App UX Specification

Status: active working spec

Last updated: 2026-03-12

## Purpose

This document defines the intended user-facing UX for the PortWorld iOS app as it moves from a developer-oriented runtime console to a publishable App Store product.

It is the active product and UX specification for the next iOS cleanup phase.

This document does not change the core runtime capabilities already in the codebase. It defines how those capabilities should be presented, gated, and explained to end users.

## Product Direction

PortWorld should feel like a minimal, Apple-style companion app for smart glasses.

The app should:

- be glasses-first in user-facing UX
- make backend self-hosting setup understandable and as light as possible
- guide first-time users through the required setup steps in the right order
- avoid exposing developer diagnostics, transport internals, or runtime logs in the main experience
- keep the day-to-day home screen extremely simple

The app should not behave like a debug dashboard.

## Primary UX Decisions

- The app remains glasses-first in the shipping UX.
- Existing phone-route and mock-device functionality are not removed yet, but they should be hidden from normal App Store-facing flows.
- The first-run flow should be resumable and stateful.
- Meta glasses connection is important, but it is not a hard blocker. Users may skip it and complete it later from Settings or Help.
- Backend setup must happen before wake-word practice and before the assistant-led profile onboarding, because both depend on a working backend connection.
- First-run config should expose only the fields truly required to make the app work.
- The canonical saved personalization contract should stay aligned with the existing backend profile schema for now.

## Design Principles

- Use a restrained visual style with large type, generous spacing, and low-chrome surfaces.
- Prefer native navigation and form patterns over custom control-heavy layouts.
- Use one primary accent color and subtle motion.
- Keep copy short, direct, and action-oriented.
- Hide technical complexity unless the user explicitly opens Settings or troubleshooting help.
- Do not show subsystem status panels, transport traces, or long error dumps in the primary UI.

## App Structure

The app should have three major user-facing surfaces:

1. First-run onboarding flow
2. Main home screen
3. Settings and Help

The app should use a single `NavigationStack`-based structure. A tab bar is not required.

## First-Run Flow

### 1. Splash

The existing black splash screen with the logo remains.

Its only job is brand recognition while app-scoped initialization completes.

### 2. Welcome

The first screen after splash should explain, in plain language:

- what PortWorld does
- that it is designed for Meta smart glasses
- that the user will need a self-hosted backend
- that setup takes a few short steps

This screen should be concise and visually clean, with a clear primary CTA to begin setup.

### 3. Backend Setup

This is the first real configuration step.

The first-run backend setup should ask only for:

- backend base URL
- optional bearer token

The app should not ask first-run users for:

- websocket path overrides
- vision path overrides
- wake phrase tuning values
- locale tuning values
- debug-only or development-only options

Those belong in advanced settings only if they remain exposed at all.

The backend step should:

- explain that PortWorld connects to the user’s own backend
- explain that a secure bearer token may be required
- validate the entered backend before allowing the user to continue

Validation behavior:

- call `GET /healthz` against the configured base URL
- when a bearer token is provided, also call authenticated `GET /readyz`
- show short actionable failures, not raw networking dumps

Persistence behavior:

- store the backend base URL in app-managed settings
- store the bearer token securely
- derive `/ws/session` and `/vision/frame` from the base URL by default

### 4. Meta Glasses Connection

This screen should explain the actual first-time Meta connection flow.

The user should be told to:

- install or open the Meta AI app
- ensure their glasses are already paired there
- keep Bluetooth enabled
- return to PortWorld after approving the connection

The primary CTA should launch the Meta registration flow already supported by the app.

When the user returns from Meta AI, PortWorld should continue in place and show progress for:

- registration complete or incomplete
- glasses discovered or not discovered
- compatibility ready or blocked

This step is skippable.

If skipped, the app should clearly say that the user can complete it later from Settings.

Important behavior:

- camera permission is not part of first Meta registration
- camera permission remains deferred until first actual glasses vision use
- the app should use production Meta credentials in the final shipping posture rather than developer-mode assumptions

### 5. Voice Command Practice

This step teaches the user how to control the assistant.

The app should explain the two phrases:

- `"Hey Mario"` starts the assistant
- `"Goodbye Mario"` ends the conversation

The practice flow should ask the user to complete:

- 3 successful `"Hey Mario"` detections
- 3 successful `"Goodbye Mario"` detections

The screen should show:

- current counters
- immediate success or failure feedback
- a retry path
- a short explanation of what to do if recognition is unreliable

Permissions requested here:

- microphone
- speech recognition

This screen should feel like guided setup, not a raw debug test harness.

### 6. Assistant-Led Profile Onboarding

After backend setup is working, the user should complete a first conversation with the realtime assistant.

This conversation should be model-led.

The assistant should:

- ask one question at a time
- keep the tone short and helpful
- collect only a small amount of useful personalization context
- stop once it has enough information

For v1, the saved profile should stay aligned with the current backend profile schema:

- `name`
- `job`
- `company`
- `preferences`
- `projects`

Examples of acceptable question intents:

- what should I call you
- what kind of work do you do
- what team or company context matters
- what kinds of situations should I be most helpful with
- what projects or workflows are you using PortWorld for

The canonical source of truth should be a compact confirmation step immediately after the conversation.

That confirmation step should:

- show the profile fields that will be saved
- allow quick edits
- write the confirmed result to `PUT /profile`

For now, do not extend the saved schema to include location or preferred language. Those can be revisited only if the backend profile contract is intentionally expanded.

## Main Home Screen

Once onboarding is complete, the user lands on a minimal home screen.

The main home should contain:

- a clear assistant status summary
- a single dominant activate or deactivate control
- a concise reminder of the wake and sleep phrases
- a small readiness summary for Backend and Glasses
- entry points to Settings and Help

The main home should not contain:

- detailed runtime panels
- route pickers for normal users
- transport metrics
- vision upload counters
- long notes or developer diagnostics

The home should answer only the questions a normal user actually has:

- is the app ready
- are my glasses connected
- can I activate the assistant now

## Settings

Settings should be the place for changes, maintenance, and recovery.

It should include:

- backend base URL
- bearer token management
- backend validation or re-check action
- connect or reconnect glasses
- wake-word practice replay
- profile onboarding replay
- onboarding reset

If advanced fields remain exposed, they should live behind a separate advanced section and should not clutter the default settings surface.

## Help

Help should be concise and practical.

It should include:

- what PortWorld does
- how Meta connection works
- the wake and sleep voice commands
- what to check when backend connection fails
- what to check when glasses are not discovered
- what to check when permissions are denied

Help should also include a short troubleshooting path for the most common cases:

- backend unreachable
- invalid bearer token
- Meta connection incomplete
- glasses not nearby or not paired
- speech recognition permission denied

## Persistence And Routing

The app should persist first-run progress.

At minimum, the app should be able to track:

- welcome seen
- backend configured and validated
- Meta connection completed or intentionally skipped
- wake-word practice completed
- profile onboarding completed
- onboarding fully completed

If the app is interrupted mid-flow, relaunch should return the user to the first incomplete step.

After onboarding is complete, relaunch should go directly to the main home screen.

## Backend Contract

The current intended client-facing backend contract is:

- `GET /healthz`
- `GET /readyz`
- `WS /ws/session`
- `POST /vision/frame`
- `GET /profile`
- `PUT /profile`

The iOS UX should assume:

- base URL is user-configurable
- bearer token may or may not be required depending on the user’s deployment
- profile personalization is backend-backed

No new backend API is required for this UX specification if the app stays within the current profile schema.

## Non-Goals

This phase does not:

- remove the existing phone route from the codebase
- remove mock-device support from the codebase
- redesign the backend protocol
- expand the backend profile schema
- add extensive in-app analytics or logging surfaces
- turn the app into a multi-tab dashboard

## Acceptance Criteria

This specification should be considered satisfied when the iOS app behaves like:

- a first-time user can understand the product quickly
- a first-time user can configure the backend without seeing developer internals
- a first-time user can connect Meta glasses with clear instructions
- a first-time user can learn and verify the wake and sleep phrases
- a first-time user can complete a short assistant-led personalization flow
- a returning user lands on a clean minimal home screen
- a normal user never has to interact with the current developer-console-style runtime view

## Working Implementation Notes

- Reuse the existing DAT callback handling and readiness state machinery.
- Reuse the existing backend profile API instead of inventing a new onboarding-specific profile endpoint.
- Keep App Store-facing copy centered on glasses usage, not on internal route selection.
- Treat developer-mode Meta setup, mock devices, and phone-route behavior as implementation details unless the user explicitly opens advanced or internal surfaces.
