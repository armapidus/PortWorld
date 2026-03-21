# File-Only Memory Design

## Summary

Adopt a fixed, file-only memory contract with Markdown as the canonical source of truth. Do not use SQL in v1. Keep the memory surface small, deterministic, and easy to inspect locally or in cloud object storage. Retrieval should be deterministic first, with optional small-model summarization only when a write or compaction step needs it.

## Memory Files

Store memory under a stable per-user workspace root.

Required files:

- `memory/USER.md`
  - Stable user facts and preferences that persist across sessions.
  - Only store facts with high confidence or explicit user confirmation.
- `memory/CROSS_SESSION.md`
  - Rolling cross-session context that is useful beyond a single session.
  - Keep this concise and summary-like, not a raw event log.
- `memory/sessions/<session_id>/SHORT_TERM.md`
  - Current visual or interaction context from the last seconds or minutes.
  - Ephemeral within the session; rewritten frequently.
- `memory/sessions/<session_id>/LONG_TERM.md`
  - Session-level durable summary of what the user has been doing in this session.
  - Rewritten periodically during the session and finalized when the session ends.

Optional file:

- `memory/sessions/<session_id>/EVENTS.ndjson`
  - Raw append-only event journal only if debugging or auditability is needed.
  - Do not read this in normal retrieval paths.

## File Structure And Write Rules

Use predictable Markdown sections in every `.md` file so retrieval and updates do not depend on free-form parsing.

`USER.md` sections:

- `# User`
- `## Identity`
- `## Preferences`
- `## Stable Facts`
- `## Open Questions`

`CROSS_SESSION.md` sections:

- `# Cross-Session Memory`
- `## Active Themes`
- `## Ongoing Projects`
- `## Important Recent Facts`
- `## Follow-Up Items`

`SHORT_TERM.md` sections:

- `# Short-Term Memory`
- `## Current View`
- `## Recent Changes`
- `## Current Task Guess`
- `## Timestamp`

`LONG_TERM.md` sections:

- `# Session Memory`
- `## Session Goal`
- `## What Happened`
- `## Important Facts Learned`
- `## Pending Follow-Ups`
- `## Last Updated`

Write policy:

- `SHORT_TERM.md` is full-rewrite only.
- `LONG_TERM.md` is full-rewrite only.
- `CROSS_SESSION.md` is full-rewrite only.
- `USER.md` is full-rewrite only.
- Avoid in-place section patching in v1; always regenerate the full file to keep logic simple.
- Only one active writer may mutate memory for a given session/workspace at a time.
- On session end, finalize `LONG_TERM.md`, then selectively promote durable facts into `USER.md` and `CROSS_SESSION.md`.

## Retrieval Contract

Use deterministic retrieval rules instead of search/index infrastructure.

Default read order:

- Always read `USER.md`
- Read `memory/sessions/<active_session_id>/SHORT_TERM.md` when the request depends on current or recent visual/session context
- Read `memory/sessions/<active_session_id>/LONG_TERM.md` for session continuity
- Read `CROSS_SESSION.md` only when the request depends on prior sessions, ongoing projects, or durable context

Rules:

- Do not read all session files.
- Do not scan historical sessions during normal runtime.
- Do not use a helper model to choose files in v1.
- A small helper model may be used only for:
  - summarizing raw session activity into `LONG_TERM.md`
  - promoting facts into `USER.md` or `CROSS_SESSION.md`
  - compacting oversized files

Historical session access:

- Historical `LONG_TERM.md` files are archive artifacts, not default runtime context.
- If later needed, add an explicit archival retrieval workflow rather than changing the default read path.

## Limits And Compaction

Keep files small enough to remain cheap to read.

Defaults:

- `USER.md`: target under 8 KB
- `CROSS_SESSION.md`: target under 12 KB
- `SHORT_TERM.md`: target under 6 KB
- `LONG_TERM.md`: target under 12 KB

Compaction rules:

- `SHORT_TERM.md` is rewritten from recent state and never compacted incrementally.
- `LONG_TERM.md` should be summarized back to target size whenever it exceeds the limit.
- `CROSS_SESSION.md` should remain a compressed summary, not a growing log.
- `USER.md` should contain only durable facts, not narrative history.

## Cloud Storage Shape

Use the same logical contract locally and in cloud.

Local:

- Files stored on local disk under the backend data root.

Cloud:

- Files stored as ordinary objects under a predictable prefix in object storage.
- Do not rely on mounted object storage as a POSIX-like writable filesystem.
- Read and write files explicitly through the storage layer using full-object reads/writes.

## Public Interfaces

Memory API/storage contract should expose only:

- `read_user_memory() -> USER.md contents`
- `read_cross_session_memory() -> CROSS_SESSION.md contents`
- `read_short_term_memory(session_id) -> SHORT_TERM.md contents`
- `read_session_memory(session_id) -> LONG_TERM.md contents`
- `write_short_term_memory(session_id, markdown)`
- `write_session_memory(session_id, markdown)`
- `write_user_memory(markdown)`
- `write_cross_session_memory(markdown)`

No manifest, search, or SQL-backed query API in v1.

## Test Plan

Validate these scenarios:

- New user bootstrap creates the four canonical files with empty section templates.
- Session activity repeatedly rewrites `SHORT_TERM.md` without touching durable files.
- Session rollup rewrites `LONG_TERM.md` and preserves required sections.
- Session finalization promotes only durable facts into `USER.md` and `CROSS_SESSION.md`.
- Runtime retrieval reads only the expected files for active-session requests.
- Historical session files are ignored in default retrieval.
- Cloud object-store backend preserves exact file paths and full-file overwrite behavior.
- File compaction keeps each file under its size target without dropping required sections.

## Assumptions

- One active writer per session/workspace is enforced by application flow.
- Memory remains a fixed small set of canonical files, not a dynamic corpus.
- Deterministic retrieval is preferred over semantic search in v1.
- Per-session `LONG_TERM.md` files are archival artifacts; only the active session file is part of runtime context by default.
- SQL, vector search, and async memory pipelines are out of scope for v1.
