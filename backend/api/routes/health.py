from __future__ import annotations

from fastapi import APIRouter

from backend.core.settings import settings

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "loopa-mock-backend",
        "model": settings.openai_realtime_model,
        "ws_path": "/ws/session",
        "mock_capture_mode": "enabled"
        if settings.openai_debug_mock_capture_mode
        else "disabled",
    }
