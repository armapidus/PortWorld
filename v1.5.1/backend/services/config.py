from __future__ import annotations

from typing import Any

from backend.agents.catalog import list_agent_presets, runtime_agent_template
from backend.config.settings import SETTINGS
from backend.models.schemas import RuntimeTemplateResponse
from backend.tools.registry import list_available_skills, list_available_tools


def quickstart_template_payload(agent_id: str | None = None) -> dict[str, Any]:
    template = runtime_agent_template(agent_id=agent_id)
    template["generation"] = {
        "model": SETTINGS.default_main_llm_model,
        "temperature": SETTINGS.default_main_llm_temperature,
        "max_tokens": SETTINGS.default_main_llm_max_tokens,
    }
    return {
        "status": "ok",
        "runtime_config_template": template,
        "note": "Lean setup: pick an agent preset, add API keys, optionally tune generation.",
    }


def agents_payload() -> dict[str, Any]:
    return {
        "status": "ok",
        "agents": list_agent_presets(),
    }


def runtime_template_payload() -> RuntimeTemplateResponse:
    quickstart_template = quickstart_template_payload()["runtime_config_template"]

    template: dict[str, Any] = {
        "api_keys": {
            "voxtral": "",
            "nemotron": "",
            "main_llm": "",
            "vision": "",
            "elevenlabs": "",
        },
        "models": {
            "voxtral": SETTINGS.default_voxtral_model,
            "nemotron": SETTINGS.default_nemotron_model,
            "main_llm": SETTINGS.default_main_llm_model,
            "vision": SETTINGS.default_vision_model,
            "elevenlabs": SETTINGS.default_elevenlabs_model_id,
            "voxtral_base_url": SETTINGS.default_voxtral_base_url,
            "nemotron_base_url": SETTINGS.default_nemotron_base_url,
            "main_llm_base_url": SETTINGS.default_main_llm_base_url,
            "vision_base_url": SETTINGS.default_vision_base_url,
        },
        "prompts": {
            "main_system_prompt": SETTINGS.default_main_llm_system_prompt,
            "nemotron_video_prompt": SETTINGS.default_nemotron_prompt,
            "vision_system_prompt": SETTINGS.default_vision_system_prompt,
            "vision_prompt": SETTINGS.default_vision_prompt,
        },
        "tools": ["echo_context"],
        "skills": ["intent_skill"],
        "mcp_servers": [
            "stdio://local-memory",
            "http://localhost:8080/mcp",
        ],
        "agent": {
            "id": "porto.default",
            "instructions": "",
            "tools": [],
            "skills": [],
            "mcp_servers": [],
            "metadata": {},
        },
        "generation": {
            "model": SETTINGS.default_main_llm_model,
            "temperature": SETTINGS.default_main_llm_temperature,
            "max_tokens": SETTINGS.default_main_llm_max_tokens,
        },
        "metadata": {
            "main_llm_temperature": SETTINGS.default_main_llm_temperature,
            "main_llm_max_tokens": SETTINGS.default_main_llm_max_tokens,
            "nemotron_temperature": SETTINGS.default_nemotron_temperature,
            "nemotron_max_tokens": SETTINGS.default_nemotron_max_tokens,
            "vision_temperature": SETTINGS.default_vision_temperature,
            "vision_max_tokens": SETTINGS.default_vision_max_tokens,
            "voxtral_language": SETTINGS.default_voxtral_language,
            "elevenlabs_voice_id": SETTINGS.default_elevenlabs_voice_id,
            "elevenlabs_speed": SETTINGS.default_elevenlabs_speed,
            "elevenlabs_output_format": SETTINGS.default_elevenlabs_output_format,
            "main_llm_driver": SETTINGS.default_main_llm_driver,
            "tool_modules": [
                "custom_tools.my_tools",
            ],
            "agent_modules": [
                "examples.custom_agents",
            ],
        },
        "trace": {
            "enabled": True,
            "backends": SETTINGS.default_trace_backends,
            "project": "meta-glasses-template",
            "run_name": "runtime",
        },
    }

    return RuntimeTemplateResponse(
        status="ok",
        runtime_config_template=template,
        quickstart_runtime_config=quickstart_template,
        available_tools=list_available_tools(),
        available_skills=list_available_skills(),
        agent_presets=list_agent_presets(),
        trace_backends=["console", "weave", "strands"],
    )
