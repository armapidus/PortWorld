from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, UploadFile

from backend.config.settings import SETTINGS
from backend.core.debug import sanitize_debug_value
from backend.core.profile import RuntimeProfile
from backend.core.utils import (
    build_main_llm_content,
    build_messages_for_main_llm,
    extract_json_from_text,
    is_mp4_upload,
    is_wav_upload,
    parse_history_payload,
    parse_optional_int64_field,
    read_upload_bytes,
    to_data_url,
    utc_now_ts_ms,
    validate_query_contract_metadata,
)
from backend.providers.elevenlabs import capture_elevenlabs_stream_debug, prepare_elevenlabs_stream
from backend.providers.mistral import call_vision_llm_non_stream, iter_main_llm_tokens
from backend.providers.nvidia import summarize_video
from backend.providers.voxtral import transcribe_audio
from backend.tools.registry import ToolRunResult, run_requested_tools
from backend.tracing.manager import TraceManager


def _build_tools_context(tool_runs: list[ToolRunResult]) -> str | None:
    """Build a structured context string from tool outputs (or None if empty)."""
    if not tool_runs:
        return None

    payload = [
        {
            "tool": item.name,
            "status": item.status,
            "output": item.output,
        }
        for item in tool_runs
    ]
    return json.dumps(payload, ensure_ascii=False)


async def run_ios_debug_simulation(
    *,
    profile: RuntimeProfile,
    tracer: TraceManager,
    metadata_raw: str,
    audio: UploadFile,
    video: UploadFile,
    frame: UploadFile | None,
    llm_model: str,
    voice_id: str,
    tts_model_id: str,
    speed: float | None,
    output_format: str,
    include_audio_base64: bool,
) -> dict[str, Any]:
    try:
        payload = json.loads(metadata_raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="metadata must be valid JSON.") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="metadata must be a JSON object.")

    contract_metadata = validate_query_contract_metadata(payload)

    audio_bytes, audio_type = await read_upload_bytes(
        audio,
        max_bytes=SETTINGS.max_audio_bytes,
        label="Audio",
    )
    if not is_wav_upload(audio_type, audio.filename):
        raise HTTPException(status_code=400, detail="For /v1/debug/ios/simulate, audio must be WAV (.wav/.wave).")

    video_bytes, video_type = await read_upload_bytes(
        video,
        max_bytes=SETTINGS.max_video_bytes,
        label="Video",
    )
    if not is_mp4_upload(video_type, video.filename):
        raise HTTPException(status_code=400, detail="For /v1/debug/ios/simulate, video must be MP4 (.mp4).")

    voxtral_debug: dict[str, Any] = {}
    transcript = await transcribe_audio(
        profile=profile,
        tracer=tracer,
        audio=audio_bytes,
        content_type=audio_type,
        filename=audio.filename,
        debug_capture=voxtral_debug,
    )

    nemotron_debug: dict[str, Any] = {}
    video_summary = await summarize_video(
        profile=profile,
        tracer=tracer,
        video_data_url=to_data_url(video_bytes, video_type),
        prompt_hint=str(contract_metadata.get("video_prompt") or contract_metadata.get("prompt") or "").strip(),
        debug_capture=nemotron_debug,
    )

    history = parse_history_payload(contract_metadata.get("history"))
    user_prompt = str(contract_metadata.get("prompt") or "").strip()
    model = str(contract_metadata.get("llm_model") or llm_model or profile.main_llm.model).strip()
    if not model:
        model = profile.main_llm.model

    tool_context = {
        "prompt": user_prompt,
        "transcript": transcript,
        "video_summary": video_summary,
        "history": history,
        "mcp_servers": profile.mcp_servers,
    }
    tool_runs = await run_requested_tools(profile=profile, tracer=tracer, context=tool_context)
    tools_ctx = _build_tools_context(tool_runs)

    messages = build_messages_for_main_llm(
        history=history,
        user_prompt=user_prompt,
        audio_transcript=transcript,
        video_summary=video_summary,
        image_data_urls=[],
        system_prompt=profile.prompts["main_system_prompt"],
        tool_context=tools_ctx,
    )

    main_llm_stream_debug: dict[str, Any] = {}
    collected_tokens: list[str] = []
    async for token in iter_main_llm_tokens(
        profile=profile,
        tracer=tracer,
        model=model,
        messages=messages,
        debug_capture=main_llm_stream_debug,
    ):
        collected_tokens.append(token)
    assistant_text = "".join(collected_tokens).strip()
    main_llm_stream_debug["assistant_text"] = assistant_text

    if not assistant_text:
        raise HTTPException(status_code=502, detail="Main LLM stream returned no assistant text.")

    elevenlabs_debug: dict[str, Any] = {}
    client, response, used_output_format = await prepare_elevenlabs_stream(
        profile=profile,
        tracer=tracer,
        text=assistant_text,
        voice_id=voice_id or None,
        model_id=tts_model_id or None,
        speed=speed,
        output_format=output_format or None,
        debug_capture=elevenlabs_debug,
    )

    try:
        captured_chunks, total_chunks, total_bytes, full_audio_b64 = await capture_elevenlabs_stream_debug(
            response=response,
            include_audio_base64=include_audio_base64,
        )
    finally:
        await response.aclose()
        await client.aclose()

    elevenlabs_debug["stream"] = {
        "output_format": used_output_format,
        "chunks_captured": captured_chunks,
        "chunks_total": total_chunks,
        "total_bytes": total_bytes,
        "audio_base64": full_audio_b64,
    }

    vision_frame_debug: dict[str, Any] | None = None
    if frame is not None:
        frame_bytes, frame_type = await read_upload_bytes(
            frame,
            max_bytes=SETTINGS.max_image_bytes,
            label="Frame",
        )
        if not frame_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="For /v1/debug/ios/simulate, frame must be an image MIME type.")

        vision_messages: list[dict[str, Any]] = []
        if profile.prompts["vision_system_prompt"]:
            vision_messages.append({"role": "system", "content": profile.prompts["vision_system_prompt"]})
        vision_messages.append(
            {
                "role": "user",
                "content": build_main_llm_content(
                    prompt=profile.prompts["vision_prompt"],
                    audio_transcript=None,
                    video_summary=None,
                    image_data_urls=[to_data_url(frame_bytes, frame_type)],
                ),
            }
        )

        vision_model_debug: dict[str, Any] = {}
        vision_assistant_text = await call_vision_llm_non_stream(
            profile=profile,
            tracer=tracer,
            messages=vision_messages,
            debug_capture=vision_model_debug,
        )
        parsed_vision = extract_json_from_text(vision_assistant_text)
        vision_frame_debug = {
            "assistant_text": vision_assistant_text,
            "parsed_json": sanitize_debug_value(parsed_vision),
            "description": str(parsed_vision.get("description") or parsed_vision.get("summary") or vision_assistant_text).strip(),
            "trace": sanitize_debug_value(vision_model_debug),
        }

    return {
        "status": "ok",
        "mode": "ios_simulation_debug",
        "session_id": contract_metadata["session_id"],
        "query_id": contract_metadata["query_id"],
        "models": {
            "voxtral": profile.voxtral.model,
            "nemotron": profile.nemotron.model,
            "main_llm": model,
            "vision_llm": profile.vision.model if vision_frame_debug is not None else None,
            "elevenlabs_model": (tts_model_id or profile.elevenlabs.model).strip(),
        },
        "agent": {
            "id": str(profile.metadata.get("agent_id") or "porto.default"),
            "name": str(profile.metadata.get("agent_name") or "Port Default"),
        },
        "transcript": transcript,
        "video_summary": video_summary,
        "assistant_text": assistant_text,
        "tools": [
            {
                "name": run.name,
                "status": run.status,
                "output": run.output,
            }
            for run in tool_runs
        ],
        "mcp_servers": profile.mcp_servers,
        "trace": {
            "voxtral": sanitize_debug_value(voxtral_debug),
            "nemotron": sanitize_debug_value(nemotron_debug),
            "main_llm_stream": sanitize_debug_value(main_llm_stream_debug),
            "elevenlabs_stream": sanitize_debug_value(elevenlabs_debug),
            "vision_frame": vision_frame_debug,
            "runtime": tracer.export(),
        },
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


async def run_vision_frame_debug(
    *,
    profile: RuntimeProfile,
    tracer: TraceManager,
    metadata_raw: str,
    frame: UploadFile,
) -> dict[str, Any]:
    try:
        payload = json.loads(metadata_raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="metadata must be valid JSON.") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="metadata must be a JSON object.")

    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="metadata.session_id is required.")

    frame_ts_ms = parse_optional_int64_field(payload, "frame_ts_ms")

    frame_bytes, frame_type = await read_upload_bytes(
        frame,
        max_bytes=SETTINGS.max_image_bytes,
        label="Frame",
    )
    if not frame_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="For /v1/debug/vision/frame, frame must be an image MIME type.")

    image_data_url = to_data_url(frame_bytes, frame_type)
    vision_messages: list[dict[str, Any]] = []
    if profile.prompts["vision_system_prompt"]:
        vision_messages.append({"role": "system", "content": profile.prompts["vision_system_prompt"]})
    vision_messages.append(
        {
            "role": "user",
            "content": build_main_llm_content(
                prompt=profile.prompts["vision_prompt"],
                audio_transcript=None,
                video_summary=None,
                image_data_urls=[image_data_url],
            ),
        }
    )

    vision_debug: dict[str, Any] = {}
    assistant_text = await call_vision_llm_non_stream(
        profile=profile,
        tracer=tracer,
        messages=vision_messages,
        debug_capture=vision_debug,
    )
    parsed = extract_json_from_text(assistant_text)
    description = str(parsed.get("description") or parsed.get("summary") or assistant_text).strip()

    return {
        "status": "ok",
        "session_id": session_id,
        "ts_ms": frame_ts_ms or utc_now_ts_ms(),
        "description": description,
        "raw_assistant_text": assistant_text,
        "parsed_json": sanitize_debug_value(parsed),
        "trace": {
            "vision_llm": sanitize_debug_value(vision_debug),
            "runtime": tracer.export(),
        },
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
