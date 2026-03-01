from __future__ import annotations

from typing import Any

from backend.tracing.base import TraceBackend, TraceEvent


class WeaveTraceBackend(TraceBackend):
    name = "weave"

    def __init__(self, *, project: str, run_name: str) -> None:
        self.project = project
        self.run_name = run_name
        self.available = False
        self._weave: Any | None = None

        try:
            import weave  # type: ignore

            self._weave = weave
            self.available = True
            init_fn = getattr(weave, "init", None)
            if callable(init_fn):
                init_fn(project)
        except Exception:
            self.available = False
            self._weave = None

    async def record(self, event: TraceEvent) -> None:
        if not self.available or self._weave is None:
            return

        try:
            attrs_fn = getattr(self._weave, "attributes", None)
            if callable(attrs_fn):
                attrs_fn(
                    {
                        "trace_backend": "weave",
                        "run_name": self.run_name,
                        "stage": event.stage,
                        "status": event.status,
                        "ts_utc": event.ts_utc,
                        "data": event.data,
                    }
                )
                return

            log_fn = getattr(self._weave, "log", None)
            if callable(log_fn):
                log_fn(
                    {
                        "run_name": self.run_name,
                        "stage": event.stage,
                        "status": event.status,
                        "ts_utc": event.ts_utc,
                        "data": event.data,
                    }
                )
        except Exception:
            return
