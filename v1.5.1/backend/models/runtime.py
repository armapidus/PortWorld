from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field


class TraceConfig(BaseModel):
    enabled: bool = True
    backends: list[str] = Field(default_factory=list)
    project: str = "meta-glasses-template"
    run_name: str = "runtime"


class AgentRuntimeConfig(BaseModel):
    id: str = "porto.default"
    instructions: str = ""
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerationRuntimeConfig(BaseModel):
    model: str = ""
    temperature: float | None = None
    max_tokens: int | None = None


class RuntimeConfig(BaseModel):
    api_keys: dict[str, str] = Field(default_factory=dict)
    models: dict[str, str] = Field(default_factory=dict)
    prompts: dict[str, str] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    trace: TraceConfig = Field(default_factory=TraceConfig)
    agent: AgentRuntimeConfig = Field(default_factory=AgentRuntimeConfig)
    generation: GenerationRuntimeConfig = Field(default_factory=GenerationRuntimeConfig)


def parse_runtime_config(raw: str | None) -> RuntimeConfig:
    if raw is None:
        return RuntimeConfig()
    stripped = raw.strip()
    if not stripped:
        return RuntimeConfig()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"runtime_config must be valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="runtime_config must be a JSON object.")
    return RuntimeConfig.model_validate(payload)


def parse_runtime_config_object(payload: dict[str, Any] | None) -> RuntimeConfig:
    if payload is None:
        return RuntimeConfig()
    return RuntimeConfig.model_validate(payload)
