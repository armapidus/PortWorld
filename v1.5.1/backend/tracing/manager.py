from __future__ import annotations

from typing import Any

from backend.tracing.base import TraceBackend, TraceCollector
from backend.tracing.console import ConsoleTraceBackend
from backend.tracing.strands_backend import StrandsTraceBackend
from backend.tracing.weave_backend import WeaveTraceBackend


class TraceManager:
    def __init__(self, trace_config: dict[str, Any]) -> None:
        self.enabled = bool(trace_config.get("enabled", True))
        self.project = str(trace_config.get("project", "meta-glasses-template"))
        self.run_name = str(trace_config.get("run_name", "runtime"))
        backend_names = [str(item).strip().lower() for item in trace_config.get("backends", []) if str(item).strip()]
        if not backend_names:
            backend_names = ["console"]

        self.backends: list[TraceBackend] = self._build_backends(backend_names)
        actual_backend_names = [backend.name for backend in self.backends]
        self.collector = TraceCollector(enabled=self.enabled, backend_names=actual_backend_names)

    def _build_backends(self, names: list[str]) -> list[TraceBackend]:
        backends: list[TraceBackend] = []
        for name in names:
            if name == "console":
                backends.append(ConsoleTraceBackend())
                continue
            if name == "weave":
                backend = WeaveTraceBackend(project=self.project, run_name=self.run_name)
                if backend.available:
                    backends.append(backend)
                continue
            if name == "strands":
                backend = StrandsTraceBackend(run_name=self.run_name)
                if backend.available:
                    backends.append(backend)
                continue

        if not backends:
            backends.append(ConsoleTraceBackend())
        return backends

    async def event(self, stage: str, *, status: str = "ok", data: dict[str, Any] | None = None) -> None:
        if not self.enabled:
            return
        event = self.collector.add_event(stage=stage, status=status, data=data)
        for backend in self.backends:
            await backend.record(event)

    def export(self) -> dict[str, Any]:
        return self.collector.to_dict()


def build_trace_manager(trace_config: dict[str, Any]) -> TraceManager:
    return TraceManager(trace_config)
