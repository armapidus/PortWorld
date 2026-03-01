from __future__ import annotations

from dataclasses import dataclass, field
import importlib
from typing import Any


@dataclass(slots=True)
class AgentPreset:
    id: str
    name: str
    description: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    mcp_servers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
        }


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _normalize_agent_payload(raw: dict[str, Any]) -> AgentPreset | None:
    agent_id = str(raw.get("id") or "").strip()
    if not agent_id:
        return None

    return AgentPreset(
        id=agent_id,
        name=str(raw.get("name") or agent_id).strip(),
        description=str(raw.get("description") or "").strip(),
        system_prompt=str(raw.get("system_prompt") or "").strip(),
        tools=_as_str_list(raw.get("tools")),
        skills=_as_str_list(raw.get("skills")),
        mcp_servers=_as_str_list(raw.get("mcp_servers")),
        metadata=dict(raw.get("metadata") or {}),
    )


_BUILTIN_AGENTS: dict[str, AgentPreset] = {
    "porto.default": AgentPreset(
        id="porto.default",
        name="Port Default",
        description="General assistant for voice + vision in real-world scenarios.",
        system_prompt=(
            "You are Port, a smart-glasses voice assistant. You receive structured context:"
            " the user's spoken question, a description of what the glasses camera sees,"
            " and optional tool data. Answer the user directly and conversationally in"
            " 1-3 short sentences. Never use markdown, bullet points, numbered lists, or"
            " asterisks — your response will be spoken aloud. Be practical and specific"
            " to what is visible. Always respond in English, regardless of the language of any input."
        ),
        tools=["echo_context", "detect_intent"],
        skills=["intent_skill"],
    ),
    "porto.tour-guide": AgentPreset(
        id="porto.tour-guide",
        name="Tour Guide",
        description="Guided visits and contextual storytelling for places and landmarks.",
        system_prompt=(
            "You are a cultural tour guide."
            " Give clear, engaging explanations grounded in what the user sees."
            " Always respond in English, regardless of the language of any input."
        ),
        tools=["detect_intent"],
    ),
    "porto.accessibility": AgentPreset(
        id="porto.accessibility",
        name="Accessibility",
        description="Accessibility-first assistant for navigation and daily support.",
        system_prompt=(
            "You are an accessibility assistant."
            " Prioritize safety, orientation, and simple step-by-step instructions."
            " Always respond in English, regardless of the language of any input."
        ),
        tools=["detect_intent"],
    ),
    "porto.field-tech": AgentPreset(
        id="porto.field-tech",
        name="Field Technician",
        description="Industrial and on-site support (plumber, maintenance, inspection).",
        system_prompt=(
            "You are an industrial field assistant."
            " Diagnose issues quickly, ask targeted follow-up questions, and suggest actionable checks."
            " Always respond in English, regardless of the language of any input."
        ),
        tools=["echo_context", "detect_intent"],
    ),
    "porto.sales-agent": AgentPreset(
        id="porto.sales-agent",
        name="Commercial Agent",
        description="Customer-facing assistant for product explanation and qualification.",
        system_prompt=(
            "You are a commercial agent."
            " Be concise, useful, and oriented toward qualification and next business steps."
            " Always respond in English, regardless of the language of any input."
        ),
        tools=["detect_intent"],
    ),
}


def _extract_agents_from_module(module: Any) -> dict[str, AgentPreset]:
    extracted: dict[str, AgentPreset] = {}

    exported = getattr(module, "AGENTS", None)
    if isinstance(exported, dict):
        for _, raw in exported.items():
            if isinstance(raw, AgentPreset):
                extracted[raw.id] = raw
                continue
            if isinstance(raw, dict):
                normalized = _normalize_agent_payload(raw)
                if normalized is not None:
                    extracted[normalized.id] = normalized
    elif isinstance(exported, list):
        for raw in exported:
            if isinstance(raw, AgentPreset):
                extracted[raw.id] = raw
                continue
            if isinstance(raw, dict):
                normalized = _normalize_agent_payload(raw)
                if normalized is not None:
                    extracted[normalized.id] = normalized

    register = getattr(module, "register_agents", None)
    if callable(register):
        try:
            dynamic = register()
        except Exception:
            dynamic = None

        if isinstance(dynamic, dict):
            for _, raw in dynamic.items():
                if isinstance(raw, AgentPreset):
                    extracted[raw.id] = raw
                    continue
                if isinstance(raw, dict):
                    normalized = _normalize_agent_payload(raw)
                    if normalized is not None:
                        extracted[normalized.id] = normalized
        elif isinstance(dynamic, list):
            for raw in dynamic:
                if isinstance(raw, AgentPreset):
                    extracted[raw.id] = raw
                    continue
                if isinstance(raw, dict):
                    normalized = _normalize_agent_payload(raw)
                    if normalized is not None:
                        extracted[normalized.id] = normalized

    return extracted


def _load_external_agents(module_names: list[str]) -> dict[str, AgentPreset]:
    resolved: dict[str, AgentPreset] = {}
    for module_name in module_names:
        candidate = module_name.strip()
        if not candidate:
            continue
        try:
            module = importlib.import_module(candidate)
        except Exception:
            continue
        resolved.update(_extract_agents_from_module(module))
    return resolved


def _resolve_catalog(module_names: list[str] | None = None) -> dict[str, AgentPreset]:
    merged = dict(_BUILTIN_AGENTS)
    if module_names:
        merged.update(_load_external_agents(module_names))
    return merged


def default_agent_id() -> str:
    return "porto.default"


def list_agent_presets(module_names: list[str] | None = None) -> list[dict[str, str]]:
    catalog = _resolve_catalog(module_names=module_names)
    ordered_ids = list(_BUILTIN_AGENTS.keys())
    ordered_ids.extend(
        sorted(
            agent_id for agent_id in catalog.keys() if agent_id not in _BUILTIN_AGENTS
        )
    )

    payload: list[dict[str, str]] = []
    for agent_id in ordered_ids:
        preset = catalog.get(agent_id)
        if preset is None:
            continue
        payload.append(preset.summary())
    return payload


def resolve_agent_preset(
    *,
    agent_id: str | None,
    module_names: list[str] | None = None,
) -> AgentPreset:
    catalog = _resolve_catalog(module_names=module_names)
    selected = (agent_id or "").strip() or default_agent_id()
    if selected in catalog:
        return catalog[selected]
    return catalog[default_agent_id()]


def runtime_agent_template(agent_id: str | None = None) -> dict[str, Any]:
    preset = resolve_agent_preset(agent_id=agent_id, module_names=None)
    return {
        "agent": {
            "id": preset.id,
            "instructions": "",
            "tools": list(preset.tools),
            "skills": list(preset.skills),
            "mcp_servers": list(preset.mcp_servers),
            "metadata": {},
        },
        "generation": {
            "model": "",
            "temperature": None,
            "max_tokens": None,
        },
        "api_keys": {
            "main_llm": "",
            "voxtral": "",
            "nemotron": "",
            "elevenlabs": "",
        },
        "trace": {
            "enabled": True,
            "backends": ["console"],
            "project": "port-open-framework",
            "run_name": "quickstart",
        },
    }
