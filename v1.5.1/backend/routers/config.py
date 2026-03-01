from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.services.config import agents_payload, quickstart_template_payload, runtime_template_payload

router = APIRouter()


@router.get("/v1/config/runtime-template")
async def runtime_template() -> JSONResponse:
    payload = runtime_template_payload()
    return JSONResponse(payload.model_dump())


@router.get("/v1/config/quickstart-template")
async def quickstart_template(agent_id: str = Query(default="porto.default")) -> JSONResponse:
    payload = quickstart_template_payload(agent_id=agent_id)
    return JSONResponse(payload)


@router.get("/v1/agents")
async def agents_catalog() -> JSONResponse:
    payload = agents_payload()
    return JSONResponse(payload)
