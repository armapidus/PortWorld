from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.config.settings import SETTINGS
from backend.core.auth import require_edge_api_key
from backend.core.utils import list_routes_recursive

router = APIRouter()


@router.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {
        "status": "ok",
        "service": f"{SETTINGS.app_name}-v1.5.1",
        "time_utc": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/v1/debug/endpoints")
async def debug_endpoints(request: Request) -> JSONResponse:
    require_edge_api_key(request)
    routes = list_routes_recursive(request.app)
    return JSONResponse(
        {
            "status": "ok",
            "count": len(routes),
            "routes": routes,
            "time_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
