"""Endpoints for browsing stored run logs."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from backend.core.auth import require_edge_api_key
from backend.services.run_log import RUN_LOG

router = APIRouter()


@router.get("/v1/runs")
async def list_runs(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
) -> JSONResponse:
    """Return the most recent run log entries (newest last)."""
    require_edge_api_key(request)
    entries = RUN_LOG.recent(limit=limit)
    return JSONResponse(
        {
            "status": "ok",
            "count": len(entries),
            "total_in_memory": RUN_LOG.count,
            "log_file": str(RUN_LOG.file_path) if RUN_LOG.file_path else None,
            "runs": entries,
            "time_utc": datetime.now(timezone.utc).isoformat(),
        }
    )


@router.get("/v1/runs/{query_id}")
async def get_run(request: Request, query_id: str) -> JSONResponse:
    """Fetch a single run log entry by query_id."""
    require_edge_api_key(request)
    entry = RUN_LOG.get(query_id)
    if entry is None:
        return JSONResponse(
            {"status": "not_found", "query_id": query_id},
            status_code=404,
        )
    return JSONResponse({"status": "ok", "run": entry})
