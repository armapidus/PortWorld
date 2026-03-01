from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request

from backend.agents.catalog import resolve_agent_preset
from backend.config.settings import SETTINGS
from backend.models.runtime import RuntimeConfig


@dataclass(slots=True)
class ProviderConfig:
    base_url: str
    api_key: str
    path: str
    model: str


@dataclass(slots=True)
class RuntimeProfile:
    voxtral: ProviderConfig
    nemotron: ProviderConfig
    main_llm: ProviderConfig
    vision: ProviderConfig
    elevenlabs: ProviderConfig
    temperatures: dict[str, float]
    max_tokens: dict[str, int]
    prompts: dict[str, str]
    tools: list[str]
    skills: list[str]
    mcp_servers: list[str]
    trace: dict[str, Any]
    options: dict[str, Any]
    metadata: dict[str, Any]


def _header_key(request: Request, name: str) -> str:
    return request.headers.get(name, "").strip()


def _pick(*values: str) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _normalize_vision_model(model: str) -> str:
    candidate = model.strip()
    if not candidate:
        return SETTINGS.default_vision_model
    if candidate == "mistral.ministral-3b-instruct":
        return "mistral.ministral-3-3b-instruct"
    return candidate


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


def _as_list_of_str(value: Any) -> list[str]:
    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def resolve_runtime_profile(request: Request, runtime: RuntimeConfig) -> RuntimeProfile:
    api_keys = runtime.api_keys
    models = runtime.models
    prompts = runtime.prompts
    agent_metadata = dict(runtime.agent.metadata)
    module_names = _dedupe(
        _as_list_of_str(runtime.metadata.get("agent_modules"))
        + _as_list_of_str(agent_metadata.get("agent_modules"))
    )
    agent = resolve_agent_preset(agent_id=runtime.agent.id, module_names=module_names)

    merged_metadata = dict(agent.metadata)
    merged_metadata.update(agent_metadata)
    merged_metadata.update(runtime.metadata)

    voxtral_key = _pick(
        api_keys.get("voxtral", ""),
        _header_key(request, "x-voxtral-api-key"),
        SETTINGS.default_voxtral_api_key,
    )
    nemotron_key = _pick(
        api_keys.get("nemotron", ""),
        _header_key(request, "x-nemotron-api-key"),
        SETTINGS.default_nemotron_api_key,
    )
    main_key = _pick(
        api_keys.get("main_llm", ""),
        _header_key(request, "x-main-llm-api-key"),
        SETTINGS.default_main_llm_api_key,
    )
    vision_key = _pick(
        api_keys.get("vision", ""),
        _header_key(request, "x-vision-api-key"),
        SETTINGS.default_vision_api_key,
    )
    elevenlabs_key = _pick(
        api_keys.get("elevenlabs", ""),
        _header_key(request, "x-elevenlabs-api-key"),
        SETTINGS.default_elevenlabs_api_key,
    )

    voice_model = (models.get("elevenlabs", "") or SETTINGS.default_elevenlabs_model_id).strip()
    voxtral_model = (models.get("voxtral", "") or SETTINGS.default_voxtral_model).strip()
    nemotron_model = (models.get("nemotron", "") or SETTINGS.default_nemotron_model).strip()
    main_model = _pick(runtime.generation.model, models.get("main_llm", ""), SETTINGS.default_main_llm_model)
    vision_model = _normalize_vision_model(models.get("vision", "") or SETTINGS.default_vision_model)

    main_temperature = runtime.generation.temperature
    if main_temperature is None:
        main_temperature = float(merged_metadata.get("main_llm_temperature", SETTINGS.default_main_llm_temperature))

    main_max_tokens = runtime.generation.max_tokens
    if main_max_tokens is None:
        main_max_tokens = int(merged_metadata.get("main_llm_max_tokens", SETTINGS.default_main_llm_max_tokens))

    selected_tools = _dedupe(agent.tools + runtime.agent.tools + runtime.tools)
    selected_skills = _dedupe(agent.skills + runtime.agent.skills + runtime.skills)
    selected_mcp_servers = _dedupe(agent.mcp_servers + runtime.agent.mcp_servers + runtime.mcp_servers)

    main_system_prompt = _pick(
        runtime.agent.instructions,
        prompts.get("main_system_prompt", ""),
        agent.system_prompt,
        SETTINGS.default_main_llm_system_prompt,
    )

    profile_metadata = dict(merged_metadata)
    profile_metadata["agent_id"] = agent.id
    profile_metadata["agent_name"] = agent.name

    return RuntimeProfile(
        voxtral=ProviderConfig(
            base_url=models.get("voxtral_base_url", "") or SETTINGS.default_voxtral_base_url,
            api_key=voxtral_key,
            path=models.get("voxtral_path", "") or SETTINGS.default_voxtral_stt_path,
            model=voxtral_model,
        ),
        nemotron=ProviderConfig(
            base_url=models.get("nemotron_base_url", "") or SETTINGS.default_nemotron_base_url,
            api_key=nemotron_key,
            path=models.get("nemotron_path", "") or SETTINGS.default_nemotron_chat_path,
            model=nemotron_model,
        ),
        main_llm=ProviderConfig(
            base_url=models.get("main_llm_base_url", "") or SETTINGS.default_main_llm_base_url,
            api_key=main_key,
            path=models.get("main_llm_path", "") or SETTINGS.default_main_llm_chat_path,
            model=main_model,
        ),
        vision=ProviderConfig(
            base_url=models.get("vision_base_url", "") or SETTINGS.default_vision_base_url,
            api_key=vision_key,
            path=models.get("vision_path", "") or SETTINGS.default_vision_chat_path,
            model=vision_model,
        ),
        elevenlabs=ProviderConfig(
            base_url="https://api.elevenlabs.io",
            api_key=elevenlabs_key,
            path="/v1/text-to-speech",
            model=voice_model,
        ),
        temperatures={
            "main_llm": float(main_temperature),
            "nemotron": float(merged_metadata.get("nemotron_temperature", SETTINGS.default_nemotron_temperature)),
            "vision": float(merged_metadata.get("vision_temperature", SETTINGS.default_vision_temperature)),
            "elevenlabs_speed": float(merged_metadata.get("elevenlabs_speed", SETTINGS.default_elevenlabs_speed)),
        },
        max_tokens={
            "main_llm": int(main_max_tokens),
            "nemotron": int(merged_metadata.get("nemotron_max_tokens", SETTINGS.default_nemotron_max_tokens)),
            "vision": int(merged_metadata.get("vision_max_tokens", SETTINGS.default_vision_max_tokens)),
        },
        prompts={
            "main_system_prompt": main_system_prompt,
            "nemotron_video_prompt": prompts.get("nemotron_video_prompt", SETTINGS.default_nemotron_prompt),
            "vision_system_prompt": prompts.get("vision_system_prompt", SETTINGS.default_vision_system_prompt),
            "vision_prompt": prompts.get("vision_prompt", SETTINGS.default_vision_prompt),
        },
        tools=selected_tools,
        skills=selected_skills,
        mcp_servers=selected_mcp_servers,
        trace={
            "enabled": runtime.trace.enabled,
            "backends": runtime.trace.backends or SETTINGS.default_trace_backends,
            "project": runtime.trace.project,
            "run_name": runtime.trace.run_name,
        },
        options={
            "voxtral_language": str(merged_metadata.get("voxtral_language", SETTINGS.default_voxtral_language)).strip(),
            "elevenlabs_voice_id": str(
                merged_metadata.get("elevenlabs_voice_id", SETTINGS.default_elevenlabs_voice_id)
            ).strip(),
            "elevenlabs_output_format": str(
                merged_metadata.get("elevenlabs_output_format", SETTINGS.default_elevenlabs_output_format)
            ).strip(),
            "elevenlabs_speed": float(merged_metadata.get("elevenlabs_speed", SETTINGS.default_elevenlabs_speed)),
            "main_llm_driver": str(merged_metadata.get("main_llm_driver", SETTINGS.default_main_llm_driver)).strip()
            or SETTINGS.default_main_llm_driver,
            "agent_id": agent.id,
        },
        metadata=profile_metadata,
    )
