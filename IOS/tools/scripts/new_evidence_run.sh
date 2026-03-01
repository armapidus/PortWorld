#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
EVIDENCE_ROOT="$ROOT_DIR/MetaCollectLuigi/docs/evidence/v4"
RUN_ID="run-$(date +%Y%m%d-%H%M)"

mkdir -p "$EVIDENCE_ROOT/checklists/$RUN_ID" \
         "$EVIDENCE_ROOT/logs/$RUN_ID" \
         "$EVIDENCE_ROOT/metrics/$RUN_ID" \
         "$EVIDENCE_ROOT/media/$RUN_ID"

cat > "$EVIDENCE_ROOT/checklists/$RUN_ID/T1-T13.md" <<'CHECKLIST'
# T1-T13 Manual Validation Checklist

- [ ] T1 Fresh install registration
- [ ] T2 One-click activation
- [ ] T3 Manual trigger positive
- [ ] T4 Spurious trigger negative
- [ ] T5 Query end on silence timeout
- [ ] T6 Query bundle creation and upload
- [ ] T7 Photo upload cadence (3 min)
- [ ] T8 Assistant audio downlink playback
- [ ] T9 WebSocket disconnect recovery
- [ ] T10 Background best-effort runtime
- [ ] T11 Repeated wake/query soak
- [ ] T12 End-to-end latency monitoring
- [ ] T12b Query bundle latency
- [ ] T13 Rolling video buffer stability

## Notes
- Fault profile used:
- Device/simulator:
- Outcome summary:
CHECKLIST

cat > "$EVIDENCE_ROOT/logs/$RUN_ID/runtime.log" <<'LOGS'
# Runtime log capture notes
# 1. Start mock backend and paste startup line here.
# 2. Capture app runtime events (wake/query/upload/ws/recovery) here.
LOGS

cat > "$EVIDENCE_ROOT/metrics/$RUN_ID/summary.md" <<'METRICS'
# Metrics Summary

- Photo upload rate effective:
- Query bundle upload success/fail:
- Reconnect attempts and recovery latency:
- Query-end to first-audio-byte latency:
- Buffer duration/memory observations:
METRICS

printf 'Initialized evidence run: %s\n' "$RUN_ID"
printf 'Checklist: %s\n' "$EVIDENCE_ROOT/checklists/$RUN_ID/T1-T13.md"
printf 'Logs: %s\n' "$EVIDENCE_ROOT/logs/$RUN_ID/runtime.log"
printf 'Metrics: %s\n' "$EVIDENCE_ROOT/metrics/$RUN_ID/summary.md"
