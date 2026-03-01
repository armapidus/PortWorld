from __future__ import annotations

import json
import sys

from backend.tracing.base import TraceBackend, TraceEvent


class ConsoleTraceBackend(TraceBackend):
    name = "console"

    async def record(self, event: TraceEvent) -> None:
        payload = {
            "trace": {
                "ts_utc": event.ts_utc,
                "stage": event.stage,
                "status": event.status,
                "data": event.data,
            }
        }
        print(json.dumps(payload, ensure_ascii=True), file=sys.stderr, flush=True)
