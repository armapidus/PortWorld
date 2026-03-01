from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from backend.core.debug import sanitize_debug_value


@dataclass(slots=True)
class TraceEvent:
    ts_utc: str
    stage: str
    status: str
    data: dict[str, Any]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TraceBackend:
    name = "base"

    async def record(self, event: TraceEvent) -> None:
        return None


class NullTraceBackend(TraceBackend):
    name = "null"


class TraceCollector:
    def __init__(self, *, enabled: bool, backend_names: list[str]) -> None:
        self.enabled = enabled
        self.backend_names = backend_names
        self.events: list[TraceEvent] = []

    def add_event(self, *, stage: str, status: str, data: dict[str, Any] | None = None) -> TraceEvent:
        event = TraceEvent(
            ts_utc=utc_now_iso(),
            stage=stage,
            status=status,
            data=sanitize_debug_value(data or {}),
        )
        self.events.append(event)
        return event

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "backends": self.backend_names,
            "events": [
                {
                    "ts_utc": event.ts_utc,
                    "stage": event.stage,
                    "status": event.status,
                    "data": event.data,
                }
                for event in self.events
            ],
        }
