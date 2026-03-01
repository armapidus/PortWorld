from __future__ import annotations

from fastapi import HTTPException, Request

from backend.config.settings import SETTINGS


def require_edge_api_key(request: Request) -> None:
    required = SETTINGS.edge_api_key
    if not required:
        return
    provided = request.headers.get("x-api-key", "").strip()
    if provided != required:
        raise HTTPException(status_code=401, detail="Unauthorized.")
