# v4 Acceptance Evidence

This directory is the canonical location for MVP v4 release-gate artifacts.

## Directory layout

- `checklists/` - pass/fail checklists for `T1-T13` and `T12b`.
- `logs/` - session logs and lifecycle event logs with millisecond timestamps.
- `metrics/` - summaries for cadence, latency, reconnect, and buffer behavior.
- `media/` - optional screenshots/recordings that support test evidence.

## Run-folder convention

Create one folder per execution run:

- `run-YYYYMMDD-HHMM/`

Example:

- `checklists/run-20260301-1430/T1-T13.md`
- `logs/run-20260301-1430/runtime.log`
- `metrics/run-20260301-1430/T7-photo-cadence.json`

To initialize a new run folder automatically:

```bash
tools/scripts/new_evidence_run.sh
```

Manual validation runbook:

- `docs/evidence/v4/MOCK_VALIDATION_RUNBOOK.md`

## Required artifacts by acceptance scope

- `T1-T13` checklist with explicit pass/fail per test.
- Wake/query lifecycle event log excerpts:
  - `wakeword.detected`
  - `query.started`
  - `query.ended`
  - `query.bundle.uploaded`
- Photo upload cadence evidence (`POST /vision/frame`).
- Query bundle creation/upload timing evidence (`POST /query`).
- Reconnect/resume evidence for socket drop and app background/foreground.
- Playback route evidence for assistant audio on glasses speakers.
