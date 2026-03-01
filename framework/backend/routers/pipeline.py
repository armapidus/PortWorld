from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from backend.core.profile import resolve_runtime_profile
from backend.models.runtime import parse_runtime_config, parse_runtime_config_object
from backend.models.schemas import ElevenLabsStreamRequest
from backend.providers.elevenlabs import media_type_from_output_format, prepare_elevenlabs_live_stream, prepare_elevenlabs_stream
from backend.providers.mistral import iter_main_llm_tokens
from backend.services.pipeline import prepare_pipeline_run, run_pipeline
from backend.tracing.manager import build_trace_manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/vision/frame")
async def vision_frame(payload: dict[str, Any]) -> JSONResponse:
    """iOS vision frame endpoint.
    
    Accepts the iOS JSON format with inline base64 image data.
    For now, just acknowledges receipt - frame analysis can be added later.
    
    Expected payload:
    {
        "session_id": "sess_<UUID>",
        "ts_ms": 1740777601000,
        "frame_id": "frame_<nowMs>",
        "capture_ts_ms": 1740777600990,
        "width": 1280,
        "height": 720,
        "frame_b64": "<base64 encoded JPEG>"
    }
    """
    session_id = payload.get("session_id")
    frame_id = payload.get("frame_id")
    ts_ms = payload.get("ts_ms")
    frame_b64 = payload.get("frame_b64")
    
    if not session_id or not frame_id or not frame_b64 or ts_ms is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    # Log receipt (analysis can be added later)
    logger.debug(f"Vision frame received: session={session_id} frame={frame_id} bytes={len(frame_b64)}")
    
    return JSONResponse(content={"status": "ok", "frame_id": frame_id})


@router.post("/v1/pipeline")
async def pipeline(
    request: Request,
    prompt: str = Form(default=""),
    history_json: str = Form(default="[]"),
    audio: UploadFile | None = File(default=None),
    images: list[UploadFile] | None = File(default=None),
    video: UploadFile | None = File(default=None),
    llm_model: str = Form(default=""),
    runtime_config: str | None = Form(default=None),
) -> JSONResponse:
    runtime = parse_runtime_config(runtime_config)
    profile = resolve_runtime_profile(request, runtime)
    tracer = build_trace_manager(profile.trace)

    result = await run_pipeline(
        profile=profile,
        tracer=tracer,
        prompt=prompt,
        history_json=history_json,
        audio=audio,
        images=images or [],
        video=video,
        llm_model=llm_model or None,
    )
    return JSONResponse(result)


@router.post("/v1/elevenlabs/stream")
async def elevenlabs_stream(request: Request, body: ElevenLabsStreamRequest) -> StreamingResponse:
    runtime = parse_runtime_config_object(body.runtime_config)
    profile = resolve_runtime_profile(request, runtime)
    tracer = build_trace_manager(profile.trace)

    client, response, used_output_format = await prepare_elevenlabs_stream(
        profile=profile,
        tracer=tracer,
        text=body.text,
        voice_id=body.voice_id,
        model_id=body.tts_model_id,
        speed=body.speed,
        output_format=body.output_format,
    )

    async def chunked_audio():
        try:
            async for chunk in response.aiter_bytes():
                if chunk:
                    yield chunk
        finally:
            await response.aclose()
            await client.aclose()

    return StreamingResponse(
        chunked_audio(),
        media_type=media_type_from_output_format(used_output_format),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/v1/pipeline/tts-stream")
async def pipeline_tts_stream(
    request: Request,
    prompt: str = Form(default=""),
    history_json: str = Form(default="[]"),
    audio: UploadFile | None = File(default=None),
    images: list[UploadFile] | None = File(default=None),
    video: UploadFile | None = File(default=None),
    llm_model: str = Form(default=""),
    voice_id: str = Form(default=""),
    tts_model_id: str = Form(default="", alias="model_id"),
    speed: float | None = Form(default=None),
    output_format: str = Form(default=""),
    runtime_config: str | None = Form(default=None),
) -> StreamingResponse:
    runtime = parse_runtime_config(runtime_config)
    profile = resolve_runtime_profile(request, runtime)
    tracer = build_trace_manager(profile.trace)

    prepared = await prepare_pipeline_run(
        profile=profile,
        tracer=tracer,
        prompt=prompt,
        history_json=history_json,
        audio=audio,
        images=images or [],
        video=video,
        llm_model=llm_model or None,
    )

    llm_token_stream = iter_main_llm_tokens(
        profile=profile,
        model=prepared.model,
        messages=prepared.messages,
        tracer=tracer,
        debug_capture=None,
    )

    audio_stream, used_output_format = await prepare_elevenlabs_live_stream(
        profile=profile,
        tracer=tracer,
        text_iterator=llm_token_stream,
        voice_id=voice_id or None,
        model_id=tts_model_id or None,
        speed=speed,
        output_format=output_format or None,
    )

    return StreamingResponse(
        audio_stream,
        media_type=media_type_from_output_format(used_output_format),
        headers={
            "Cache-Control": "no-store",
            "X-Transcript-Available": "1" if prepared.transcript else "0",
            "X-Video-Summary-Available": "1" if prepared.video_summary else "0",
            "X-TTS-Relay-Mode": "llm-token-live",
        },
    )


@router.post("/v1/query")
async def ios_query(
    request: Request,
    metadata: str = Form(...),
    audio: UploadFile = File(...),
    video: UploadFile = File(...),
    runtime_config: str | None = Form(default=None),
) -> JSONResponse:
    """iOS query bundle endpoint.
    
    Accepts the iOS multipart format (metadata + audio + video), processes
    the query through the pipeline, and streams audio back over WebSocket.
    
    The HTTP response returns immediately with {"status": "ok", "query_id": "...", "processing": true}.
    Actual audio delivery happens asynchronously over the WebSocket connection.
    """
    import asyncio
    import json
    
    from backend.services.ios_query import process_ios_query_background
    
    # Parse metadata JSON
    try:
        metadata_obj = json.loads(metadata)
    except json.JSONDecodeError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Invalid metadata JSON: {exc}")
    
    # Extract required fields
    session_id = metadata_obj.get("session_id")
    query_id = metadata_obj.get("query_id")
    
    if not session_id or not query_id:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail="metadata.session_id and metadata.query_id are required",
        )
    
    # Read file data
    audio_bytes = await audio.read()
    video_bytes = await video.read()
    
    # Spawn background task for pipeline processing
    asyncio.create_task(
        process_ios_query_background(
            session_id=session_id,
            query_id=query_id,
            audio_bytes=audio_bytes,
            video_bytes=video_bytes,
            metadata=metadata_obj,
            runtime_config_json=runtime_config,
        )
    )
    
    # Return immediately
    return JSONResponse(
        content={
            "status": "ok",
            "query_id": query_id,
            "processing": True,
        }
    )
