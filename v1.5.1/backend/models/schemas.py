from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ElevenLabsStreamRequest(BaseModel):
    text: str = Field(min_length=1)
    voice_id: str | None = None
    tts_model_id: str | None = Field(default=None, alias="model_id")
    speed: float | None = Field(default=None, gt=0.0)
    output_format: str | None = None
    runtime_config: dict[str, Any] | None = None

    model_config = ConfigDict(populate_by_name=True)


class AgentPresetSummary(BaseModel):
    id: str
    name: str
    description: str


class RuntimeTemplateResponse(BaseModel):
    status: str
    runtime_config_template: dict[str, Any]
    quickstart_runtime_config: dict[str, Any]
    available_tools: list[str]
    available_skills: list[str]
    agent_presets: list[AgentPresetSummary]
    trace_backends: list[str]
