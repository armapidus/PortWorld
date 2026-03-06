from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class VisionFramePayload(BaseModel):
    frame_id: str | None = None


@router.post("/vision/frame")
async def vision_frame(payload: VisionFramePayload) -> dict[str, str | None]:
    return {"status": "ok", "frame_id": payload.frame_id}
