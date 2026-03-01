from __future__ import annotations

from dataclasses import dataclass
import importlib
from typing import Any, Callable

from backend.core.debug import sanitize_debug_value
from backend.core.profile import RuntimeProfile
from backend.tools.builtin import detect_intent, echo_context
from backend.tracing.manager import TraceManager

ToolFn = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(slots=True)
class ToolRunResult:
    name: str
    status: str
    output: dict[str, Any]


_TOOL_REGISTRY: dict[str, ToolFn] = {
    "echo_context": echo_context,
    "detect_intent": detect_intent,
}

_SKILL_ALIASES: dict[str, str] = {
    "intent_skill": "detect_intent",
    "echo_skill": "echo_context",
}


def list_available_tools() -> list[str]:
    return sorted(_TOOL_REGISTRY.keys())


def list_available_skills() -> list[str]:
    return sorted(_SKILL_ALIASES.keys())


def _resolve_tool_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        return ""
    return _SKILL_ALIASES.get(normalized, normalized)


def _load_external_tools(module_names: list[str]) -> dict[str, ToolFn]:
    resolved = dict(_TOOL_REGISTRY)
    for module_name in module_names:
        candidate = module_name.strip()
        if not candidate:
            continue
        try:
            module = importlib.import_module(candidate)
        except Exception:
            continue

        exported = getattr(module, "TOOLS", None)
        if isinstance(exported, dict):
            for key, value in exported.items():
                if isinstance(key, str) and callable(value):
                    resolved[key] = value
            continue

        register = getattr(module, "register_tools", None)
        if callable(register):
            try:
                dynamic = register()
            except Exception:
                continue
            if isinstance(dynamic, dict):
                for key, value in dynamic.items():
                    if isinstance(key, str) and callable(value):
                        resolved[key] = value
    return resolved


async def run_requested_tools(
    *,
    profile: RuntimeProfile,
    tracer: TraceManager,
    context: dict[str, Any],
) -> list[ToolRunResult]:
    module_names = profile.metadata.get("tool_modules", [])
    if isinstance(module_names, str):
        module_names = [module_names]
    if not isinstance(module_names, list):
        module_names = []

    available_tools = _load_external_tools([str(item) for item in module_names])

    requested = []
    requested.extend(profile.tools)
    requested.extend(profile.skills)

    deduped: list[str] = []
    seen: set[str] = set()
    for name in requested:
        resolved = _resolve_tool_name(name)
        if not resolved or resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)

    results: list[ToolRunResult] = []
    if not deduped:
        return results

    for tool_name in deduped:
        tool_fn = available_tools.get(tool_name)
        if tool_fn is None:
            output = {"error": f"Unknown tool: {tool_name}"}
            results.append(ToolRunResult(name=tool_name, status="skipped", output=output))
            await tracer.event("tools.skipped", data={"tool": tool_name, "reason": "unknown_tool"})
            continue

        try:
            output = sanitize_debug_value(tool_fn(context))
            results.append(ToolRunResult(name=tool_name, status="ok", output=output))
            await tracer.event("tools.executed", data={"tool": tool_name})
        except Exception as exc:
            output = {"error": str(exc)}
            results.append(ToolRunResult(name=tool_name, status="error", output=output))
            await tracer.event("tools.error", status="error", data={"tool": tool_name, "message": str(exc)})

    return results
