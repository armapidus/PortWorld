# Mock Validation Runbook (Tests Deferred)

This runbook covers manual reliability loops using the local Python mock backend.

## 1. Start mock backend

```bash
./tools/mock_backend/run.sh
```

Optional fault profile examples:

```bash
FAULT_PROFILE="latency_ms=400" ./tools/mock_backend/run.sh
FAULT_PROFILE="query_5xx_every=2" ./tools/mock_backend/run.sh
FAULT_PROFILE="ws_drop_after=4,malformed_ws_once=true" ./tools/mock_backend/run.sh
```

## 2. Initialize structured evidence folders

```bash
./tools/scripts/new_evidence_run.sh
```

This creates:
- `checklists/run-YYYYMMDD-HHMM/T1-T13.md`
- `logs/run-YYYYMMDD-HHMM/runtime.log`
- `metrics/run-YYYYMMDD-HHMM/summary.md`
- `media/run-YYYYMMDD-HHMM/`

## 3. App endpoint configuration

The app already defaults to:
- `SON_WS_URL=ws://localhost:8080/ws/session`
- `SON_VISION_URL=http://localhost:8080/vision/frame`
- `SON_QUERY_URL=http://localhost:8080/query`

For physical device testing, replace `localhost` with your machine LAN IP.

## 4. Manual loop sequence

1. Activate runtime (`T2`).
2. Trigger manual query (`T3`) and wait for silence timeout (`T5`).
3. Verify `/query` upload success (`T6`) and assistant audio chunk playback (`T8`).
4. Run 3-minute vision cadence session (`T7`).
5. Run reconnect/background scenarios (`T9`, `T10`).
6. Run repeated wake/query soak (`T11`, `T13`).
7. Record latency observations (`T12`, `T12b`).

## 5. Artifact discipline

For each run:
- Mark pass/fail boxes in `T1-T13.md`.
- Copy key runtime lines into `runtime.log`.
- Update `metrics/summary.md` with measured values and failure notes.

