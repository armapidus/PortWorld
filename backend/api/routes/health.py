from __future__ import annotations

from fastapi import APIRouter
from fastapi import Request

from backend.core.constants import SERVICE_NAME

router = APIRouter()


@router.get("/healthz")
async def healthz(request: Request) -> dict[str, str]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
    }
