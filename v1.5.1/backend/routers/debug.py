from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from backend.core.auth import require_edge_api_key
from backend.core.profile import resolve_runtime_profile
from backend.models.runtime import parse_runtime_config
from backend.services.debug import run_ios_debug_simulation, run_vision_frame_debug
from backend.tracing.manager import build_trace_manager

router = APIRouter()


@router.post("/v1/debug/ios/simulate")
async def debug_ios_simulate(
    request: Request,
    metadata: str = Form(...),
    audio: UploadFile = File(...),
    video: UploadFile = File(...),
    frame: UploadFile | None = File(default=None),
    llm_model: str = Form(default=""),
    voice_id: str = Form(default=""),
    tts_model_id: str = Form(default="", alias="model_id"),
    speed: float | None = Form(default=None),
    output_format: str = Form(default=""),
    include_audio_base64: bool = Form(default=False),
    runtime_config: str | None = Form(default=None),
) -> JSONResponse:
    require_edge_api_key(request)
    runtime = parse_runtime_config(runtime_config)
    profile = resolve_runtime_profile(request, runtime)
    tracer = build_trace_manager(profile.trace)

    result = await run_ios_debug_simulation(
        profile=profile,
        tracer=tracer,
        metadata_raw=metadata,
        audio=audio,
        video=video,
        frame=frame,
        llm_model=llm_model,
        voice_id=voice_id,
        tts_model_id=tts_model_id,
        speed=speed,
        output_format=output_format,
        include_audio_base64=include_audio_base64,
    )
    return JSONResponse(result)


@router.post("/v1/debug/vision/frame")
async def debug_vision_frame(
    request: Request,
    metadata: str = Form(...),
    frame: UploadFile = File(...),
    runtime_config: str | None = Form(default=None),
) -> JSONResponse:
    require_edge_api_key(request)
    runtime = parse_runtime_config(runtime_config)
    profile = resolve_runtime_profile(request, runtime)
    tracer = build_trace_manager(profile.trace)

    result = await run_vision_frame_debug(
        profile=profile,
        tracer=tracer,
        metadata_raw=metadata,
        frame=frame,
    )
    return JSONResponse(result)
