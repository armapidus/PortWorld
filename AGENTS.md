# AGENTS.md

> Heavy iOS-specific guidance lives in `IOS/AGENTS.md`.
> This root file contains only stable, repo-wide rules that apply to every task.

---

## Platform Scope

- Primary platform: **iOS 17.0+**
- Target device: iPhone + Meta Ray-Ban Gen 2 smart glasses
- Assume iOS-first decisions unless a task explicitly asks for another platform.

---

## Codebase State

The codebase is a **hackathon MVP being refactored toward a consumer-quality iOS assistant**.

- The active near-term direction for the iOS assistant is documented in `docs/IOS_AUDIO_ONLY_ASSISTANT_PLAN.md`.
- Archived iOS planning/spec documents live in `IOS/docs/archived/` and are **historical context only** unless the user explicitly asks to consult them.
- Do not treat archived phase language or archived target-state docs as the implementation authority for new work.

**Golden rules (always enforce):**

1. Do not add features until the active plan or milestone explicitly calls for them.
2. Always leave the app compilable after every change.
3. No secrets (API keys, tokens, IP addresses) in source — use xcconfig injection.

---

## Canonical Verification Workflow

Run these checks (in order) after any non-trivial change:

```
1. Build:       xcodebuild build — zero errors, zero new warnings
2. Unit tests:  xcodebuild test (terminal) — DO NOT use test_sim
3. UI smoke:    Manual-only gate (user-requested): one coordinator agent may run
                xcodebuild boot simulator → install → launch → screenshot
```

For small, localised fixes (single file, no API or concurrency surface change) a build-only check is sufficient.

### Backend Test Policy

- Do not add backend pytest files by default.
- Do not run backend pytest by default.
- Backend regression tests are deferred unless the user explicitly asks for them.
- For backend server changes, prefer implementation work, local inspection, and manual/runtime validation over authoring or maintaining pytest coverage.

### Simulator Launch Guard (Mandatory)

To prevent sub-agent fan-out launching multiple simulators:

- Do not boot/install/launch Simulator unless the user explicitly asks for UI smoke validation.
- Sub-agents must never run simulator launch commands.
- Only one coordinator agent may run simulator commands when explicitly requested.
- In parallel work, verification defaults to build only.

> **NEVER call `test_sim`.** It is unconditionally banned — no exceptions, no user overrides. Running the test suite via the simulator hangs the agent, consumes simulator slots, and produces unreliable results in this codebase. Use `xcodebuild test` in the terminal if test execution is required.

---

## Concurrency Rules (Mandatory — never deviate)

| Where | Primitive |
|---|---|
| UI state, ViewModels, Coordinators, SessionOrchestrator | `@MainActor` |
| Thread-isolated services (WebSocket, uploader, buffer, arbiter) | `actor` |
| AVAudioEngine tap callback (AVFoundation requirement) | dedicated `DispatchQueue` — no other use |
| All network calls | `async/await` with `URLSession` |

**Banned patterns:**

- `DispatchQueue.sync` outside the audio engine tap
- Bare `print()` outside `#if DEBUG`
- `try?` that silently discards errors on I/O paths
- `@unchecked Sendable` without an explanatory comment

---

## MCP Tools

Use these tools if available. If a tool is not available, use the closest equivalent and note the substitute in your response.

| Tool | Use for |
|---|---|
| **xcodebuild** | All Xcode build, test, simulator, and UI automation tasks |
| **Ref MCP** | Third-party library docs, Swift packages, any API where local docs may be outdated |
| **Apple Docs MCP** | All Apple framework questions (`AVFoundation`, `SwiftUI`, `URLSession`, etc.) |

---

## Implementation Policy

- For active iOS assistant runtime work, keep changes aligned first with `docs/IOS_AUDIO_ONLY_ASSISTANT_PLAN.md`.
- Use `IOS/docs/archived/PRD.md`, `IOS/docs/archived/ARCHITECTURE.md`, and `IOS/docs/archived/IMPLEMENTATION_PLAN.md` only as historical background or for migration context.
- If archived docs conflict with `docs/IOS_AUDIO_ONLY_ASSISTANT_PLAN.md`, follow the new root `docs/` plan unless the user explicitly directs otherwise.

---

## Output Expectations (Non-Trivial Changes)

State the following in your response:

1. **Docs consulted** — file paths or URLs.
2. **MWDAT module touched** (if DAT SDK involved) — `MWDATCore`, `MWDATCamera`, or `MWDATMockDevice`.
3. **MCP tools used** — which tools provided research and what they returned.
4. **Assumptions made** — iOS lifecycle, integration, or API behaviour assumptions.
5. **Plan / milestone** — which active plan document governs the change (for example `docs/IOS_AUDIO_ONLY_ASSISTANT_PLAN.md`).

---

> See `IOS/AGENTS.md` for the full iOS implementation guide: docs map, DAT SDK rules, concurrency examples, and pattern reference.
