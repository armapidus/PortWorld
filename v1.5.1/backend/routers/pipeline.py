from __future__ import annotations

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
