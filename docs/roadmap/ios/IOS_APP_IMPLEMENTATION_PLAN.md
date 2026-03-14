# iOS App Screen-by-Screen Implementation Plan

Status: active working plan

Last updated: 2026-03-14

Related spec: `docs/roadmap/ios/IOS_APP_UX_SPEC.md`

## Summary

This document turns the iOS app UX specification into an implementation plan that can be executed in phases.

The goal is to replace the current developer-style runtime shell with:

- a persisted first-run onboarding flow
- a minimal main home screen
- a user-facing Settings screen
- a concise Help surface

The implementation should reuse the existing assistant runtime and wearables manager as much as possible. The rewrite is primarily about shell, navigation, persistence, and user-facing views.

The work should be delivered as phased vertical slices so the app stays usable after each milestone.

## Implementation Status

### Current implemented route order

The app currently routes through:

- `splash`
- `welcome`
- `features`
- `connectAgents`
- `backendSetup`
- `metaConnection`
- `wakePractice`
- `profileInterview`
- `legacyRuntime`

The old profile confirmation screen is no longer part of the active onboarding flow.

### Phase status as of 2026-03-14

- `Phase 1` complete
  - Root shell routing exists.
  - First-run persistence exists through `OnboardingStore` and `AppSettingsStore`.
  - Splash now routes into onboarding instead of dropping directly into the runtime shell.
- `Phase 2` complete
  - Backend setup screen is implemented.
  - Backend validation is implemented through `/healthz` and authenticated `/readyz`.
  - Runtime configuration now consumes persisted backend settings.
- `Phase 3` complete
  - Meta glasses onboarding is implemented on top of the existing DAT and wearables runtime.
  - Skip and continue paths are both supported.
- `Phase 4` complete
  - Wake phrase practice is implemented as a dedicated practice flow.
  - Practice is isolated from the live assistant runtime so wake tests do not start backend conversations.
- `Phase 5` complete with follow-up refinements
  - Guided profile onboarding is implemented.
  - The onboarding interview is now backend-owned through realtime session mode `profile_onboarding`.
  - Mario speaks first, defaults to English, and can complete onboarding even when users skip questions.
  - The review screen was removed; onboarding now continues directly after the backend emits readiness.
- Pending implementation
  - final minimal home screen
  - user-facing Settings screen
  - user-facing Help screen
  - cleanup/removal of legacy runtime-facing UI from the normal shipping path

## Implementation Principles

- Do not redesign the core assistant runtime while rebuilding the UI shell.
- Reuse existing DAT callback and readiness state logic.
- Keep the App Store-facing UX glasses-first.
- Hide phone-route and mock-device UI from normal users.
- Keep advanced developer settings out of first-run onboarding.
- Prefer a small number of clear state models over ad hoc flags spread across views.

## Target App Structure

The app should have these primary surfaces:

1. Splash
2. Onboarding flow
3. Main home
4. Settings
5. Help

The app should use a single root router from the current app shell.

Suggested route model:

- `splash`
- `welcome`
- `features`
- `connectAgents`
- `backendSetup`
- `metaConnection`
- `wakePractice`
- `profileInterview`
- `home`
- `settings`
- `help`

Suggested onboarding steps:

- `welcome`
- `features`
- `connectAgents`
- `backendSetup`
- `metaConnection`
- `wakePractice`
- `profileInterview`

## Shared State And Persistence

Before replacing screens, add app-facing state models that the UI can trust.

### App settings state

Persist:

- backend base URL
- bearer token
- backend validation status
- backend validation timestamp or freshness indicator
- hidden advanced overrides only if they remain supported

Behavior:

- bearer token should be stored securely
- base URL should be stored in app-managed preferences
- websocket and vision URLs should derive from the base URL by default

### Onboarding progress state

Persist:

- `welcomeSeen`
- `backendValidated`
- `metaCompleted`
- `metaSkipped`
- `wakePracticeCompleted`
- `profileCompleted`
- `isFullyOnboarded`

Behavior:

- relaunch should resume at the first incomplete onboarding step
- successful full onboarding should route future launches to home
- editing backend settings later should trigger revalidation, but should not wipe unrelated onboarding steps

### Home readiness state

Expose a single user-facing readiness model for the home screen that answers:

- is backend ready
- are glasses ready
- can assistant activation start now
- what action should the user take next

This should be derived from:

- backend validation state
- wearables registration and discovery state
- current assistant runtime state

## Screen Plan

### Screen 1: Splash

Purpose:

- show branding while app-scoped initialization finishes

Implementation:

- keep the existing black splash screen
- route away only when onboarding state and settings state are loaded and the wearables manager has enough state to route safely

Exit paths:

- first-time user goes to `welcome`
- returning user goes to `home`
- interrupted onboarding returns to the first incomplete step

### Screen 2: Welcome

Purpose:

- explain what PortWorld is
- explain that the product is glasses-first
- explain that setup requires a self-hosted backend

UI contents:

- short hero message
- short setup summary
- one primary CTA to begin setup

State effects:

- set `welcomeSeen = true` when the user continues

### Screen 3: Backend Setup

Purpose:

- collect the minimum client-side configuration required to use the app

Fields:

- backend base URL
- optional bearer token

Validation:

- `GET /healthz`
- if bearer token exists, authenticated `GET /readyz`

Success behavior:

- save values
- derive runtime endpoints from base URL
- mark `backendValidated = true`
- route to `metaConnection`

Failure behavior:

- remain on the same screen
- show short actionable error copy
- allow retry without resetting form state

Do not expose here:

- websocket path overrides
- vision path overrides
- wake phrase tuning
- locale tuning
- developer-only toggles

### Screen 4: Meta Glasses Connection

Purpose:

- guide the user through one-time Meta registration and glasses discovery

UI contents:

- prerequisites list
- current registration state
- discovery and compatibility status
- primary connect CTA
- skip CTA
- troubleshooting link or inline help

Flow:

- launch the existing DAT registration
- return through the current URL callback path
- refresh on-screen readiness after callback

Completion rules:

- mark Meta setup complete when registration is complete and a compatible device is discovered
- if the user skips, mark `metaSkipped = true` and continue

Important behavior:

- activation on home remains disabled until glasses readiness is truly satisfied
- camera permission stays deferred until first actual glasses vision use

### Screen 5: Wake Practice

Purpose:

- verify that the user can successfully use the wake and sleep phrases

Phrases:

- `"Hey Mario"`
- `"Goodbye Mario"`

Requirements:

- 3 successful wake detections
- 3 successful sleep detections

UI contents:

- phrase explanation
- live counters
- success and failure feedback
- retry action

Permissions requested here:

- microphone
- speech recognition

Completion rules:

- only mark `wakePracticeCompleted = true` after all required detections succeed

Implementation note:

- use the real assistant runtime, but expose only guided onboarding feedback rather than raw runtime diagnostics

### Screen 6: Profile Interview

Purpose:

- collect first-pass personalization using the live assistant

Implementation note:

- The confirmation/review step has been removed from the active flow.
- The backend now owns onboarding behavior through realtime session mode `profile_onboarding`.
- The interview auto-completes into the app once the backend emits the onboarding-ready event.

Conversation rules:

- model-led
- short and proactive
- one question at a time
- stop once enough profile data is gathered

For v1, save only the existing backend profile fields:

- `name`
- `job`
- `company`
- `preferred_language`
- `location`
- `intended_use`
- `preferences`
- `projects`

Save flow:

- run the live assistant interview
- update the persisted profile incrementally during the conversation
- let the backend decide when enough context has been collected
- auto-continue once onboarding is marked ready

Completion rules:

- only mark `profileCompleted = true` after the backend emits onboarding readiness
- if the interview fails before completion, preserve retry behavior from the interview screen

### Screen 7: Main Home

Purpose:

- become the daily-use screen after onboarding

UI contents:

- assistant status summary
- one dominant activate or deactivate control
- concise backend readiness summary
- concise glasses readiness summary
- wake and sleep phrase reminder
- Settings entry
- Help entry

Behavior:

- if backend is not valid, disable activation and point to Settings
- if glasses are not ready, disable activation and point to Meta setup
- do not show route pickers, transport metrics, or vision counters

### Screen 8: Settings

Purpose:

- allow maintenance and recovery without re-running full onboarding unless needed

Contents:

- backend base URL
- bearer token management
- backend revalidation action
- glasses reconnect or disconnect actions
- replay wake-practice action
- replay profile-onboarding action
- full onboarding reset

If advanced settings remain supported:

- place them in a separate advanced section
- keep them out of the default path

### Screen 9: Help

Purpose:

- provide clear user-facing instructions and troubleshooting

Contents:

- what the app does
- how Meta connection works
- wake and sleep phrase guidance
- backend troubleshooting
- glasses discovery troubleshooting
- permission troubleshooting

This should stay static and lightweight.

## Delivery Phases

### Phase 1: Foundation

Deliver:

- root router
- settings persistence
- onboarding persistence
- splash-to-route logic
- placeholder home shell

Goal:

- stop routing every launch directly into the current runtime console

### Phase 2: Welcome And Backend Setup

Deliver:

- welcome screen
- backend setup screen
- backend validation flow
- backend settings editing and revalidation path

Goal:

- establish a working app-managed client configuration surface

### Phase 3: Meta Connection And Help

Deliver:

- Meta connection screen
- skip and resume behavior
- callback-aware readiness refresh
- Help screen

Goal:

- make glasses onboarding understandable without exposing developer internals

### Phase 4: Wake Practice

Deliver:

- wake-practice screen
- permission requests
- replay path from Settings

Goal:

- verify wake and sleep behavior in a guided way before the user reaches the final home experience

### Phase 5: Profile Interview And Final Home

Deliver:

- assistant-led interview screen
- backend-owned onboarding session mode
- realtime profile updates
- final home state and polish

Goal:

- finish the first functional onboarding release with live personalization included

## Public Interfaces And Integration Notes

Add app-facing types for:

- route selection
- onboarding step selection
- onboarding persistence
- backend settings
- backend validation state
- home readiness state
- profile draft state

Reuse the current backend APIs:

- `GET /healthz`
- `GET /readyz`
- `GET /profile`
- `PUT /profile`
- current websocket session flow
- current DAT callback flow

Do not expand the backend profile schema in this implementation plan.

## Test Plan

Validate at minimum:

- fresh install routes to onboarding after splash
- interrupted onboarding resumes at the first incomplete step
- invalid backend URL blocks progression
- invalid bearer token blocks authenticated readiness
- Meta step supports successful completion and explicit skip
- DAT callback returns the user to the correct step
- wake-practice counters complete only after 3 wake and 3 sleep successes
- denied microphone or speech permissions keep the user on wake practice with recovery guidance
- profile interview save failures preserve draft state and allow retry
- home disables activation when backend or glasses readiness is missing
- settings edits trigger backend revalidation without wiping unrelated onboarding progress
- completed onboarding relaunches to home rather than onboarding

## Assumptions

- The shipping user-facing app remains glasses-first.
- Phone-route and mock-device behavior remain in code but stay hidden from normal UX.
- The live assistant-led profile interview is part of the first functional onboarding release.
- Production Meta credentials and release posture are handled outside this plan.
