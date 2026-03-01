from __future__ import annotations

from typing import Any

from backend.tracing.base import TraceBackend, TraceEvent


class StrandsTraceBackend(TraceBackend):
    name = "strands"

    def __init__(self, *, run_name: str) -> None:
        self.run_name = run_name
        self.available = False
        self._module: Any | None = None

        try:
            import strands  # type: ignore

            self._module = strands
            self.available = True
        except Exception:
            self.available = False
            self._module = None

    async def record(self, event: TraceEvent) -> None:
        if not self.available or self._module is None:
            return

        try:
            trace_fn = getattr(self._module, "trace", None)
            if callable(trace_fn):
                trace_fn(
                    run_name=self.run_name,
                    stage=event.stage,
                    status=event.status,
                    ts_utc=event.ts_utc,
                    data=event.data,
                )
        except Exception:
            return
