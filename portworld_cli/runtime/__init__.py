from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS: dict[str, str] = {
    "HealthSummary": "portworld_cli.runtime.reporting",
    "LiveServiceStatus": "portworld_cli.runtime.reporting",
    "LocalRuntimeStatus": "portworld_cli.runtime.reporting",
    "PublishedComposeStatus": "portworld_cli.runtime.published",
    "build_compose_command": "portworld_cli.runtime.published",
    "build_health_summary": "portworld_cli.runtime.reporting",
    "build_status_message": "portworld_cli.runtime.reporting",
    "coerce_backend_cli_payload": "portworld_cli.runtime.published",
    "collect_live_service_status": "portworld_cli.runtime.reporting",
    "inspect_published_compose_status": "portworld_cli.runtime.published",
    "parse_backend_cli_json": "portworld_cli.runtime.published",
    "probe_external_command": "portworld_cli.runtime.reporting",
    "run_backend_compose_cli": "portworld_cli.runtime.published",
    "run_bootstrap_storage_source": "portworld_cli.runtime.source",
    "run_export_memory_source": "portworld_cli.runtime.source",
    "run_local_doctor_source": "portworld_cli.runtime.source",
    "run_migrate_storage_layout_source": "portworld_cli.runtime.source",
    "run_ops_check_config_source": "portworld_cli.runtime.source",
}

__all__ = tuple(_EXPORTS.keys())


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name)
    return getattr(module, name)
