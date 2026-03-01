from __future__ import annotations

from dataclasses import dataclass
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, UploadFile

from backend.config.settings import SETTINGS
from backend.core.profile import RuntimeProfile
from backend.core.utils import build_messages_for_main_llm, parse_history, read_upload_bytes, to_data_url
from backend.providers.mistral import call_main_llm_non_stream
from backend.providers.nvidia import summarize_video
from backend.providers.voxtral import transcribe_audio
from backend.tools.registry import ToolRunResult, run_requested_tools
from backend.tracing.manager import TraceManager


@dataclass(slots=True)
class PreparedPipelineRun:
    model: str
    transcript: str | None
    video_summary: str | None
    image_data_urls: list[str]
    tool_runs: list[ToolRunResult]
    messages: list[dict[str, Any]]


def _build_tools_prompt_suffix(tool_runs: list[ToolRunResult]) -> str:
    if not tool_runs:
        return ""

    serializable = [
        {
            "tool": item.name,
            "status": item.status,
            "output": item.output,
        }
        for item in tool_runs
    ]
    serialized = json.dumps(serializable, ensure_ascii=False)
    return f"\n\nContext from tools/skills:\n{serialized}"


async def prepare_pipeline_run(
    *,
    profile: RuntimeProfile,
    tracer: TraceManager,
    prompt: str,
    history_json: str,
    audio: UploadFile | None,
    images: list[UploadFile],
    video: UploadFile | None,
    llm_model: str | None = None,
) -> PreparedPipelineRun:
    if not prompt.strip() and audio is None and not images and video is None:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one input: prompt, audio, image(s), or video.",
        )

    await tracer.event("pipeline.start", data={"has_audio": audio is not None, "images": len(images), "has_video": video is not None})

    history = parse_history(history_json)
    model = (llm_model or profile.main_llm.model).strip()

    transcript: str | None = None
    if audio is not None:
        audio_bytes, audio_type = await read_upload_bytes(
            audio,
            max_bytes=SETTINGS.max_audio_bytes,
            label="Audio",
        )
        transcript = await transcribe_audio(
            profile=profile,
            tracer=tracer,
            audio=audio_bytes,
            content_type=audio_type,
            filename=audio.filename,
        )

    image_data_urls: list[str] = []
    for image in images:
        image_bytes, image_type = await read_upload_bytes(
            image,
            max_bytes=SETTINGS.max_image_bytes,
            label="Image",
        )
        image_data_urls.append(to_data_url(image_bytes, image_type))

    video_summary: str | None = None
    if video is not None:
        video_bytes, video_type = await read_upload_bytes(
            video,
            max_bytes=SETTINGS.max_video_bytes,
            label="Video",
        )
        video_summary = await summarize_video(
            profile=profile,
            tracer=tracer,
            video_data_url=to_data_url(video_bytes, video_type),
            prompt_hint=prompt,
        )

    tool_context = {
        "prompt": prompt,
        "transcript": transcript,
        "video_summary": video_summary,
        "history": history,
        "mcp_servers": profile.mcp_servers,
    }
    tool_runs = await run_requested_tools(profile=profile, tracer=tracer, context=tool_context)
    effective_prompt = prompt + _build_tools_prompt_suffix(tool_runs)

    messages = build_messages_for_main_llm(
        history=history,
        user_prompt=effective_prompt,
        audio_transcript=transcript,
        video_summary=video_summary,
        image_data_urls=image_data_urls,
        system_prompt=profile.prompts["main_system_prompt"],
    )

    return PreparedPipelineRun(
        model=model,
        transcript=transcript,
        video_summary=video_summary,
        image_data_urls=image_data_urls,
        tool_runs=tool_runs,
        messages=messages,
    )


async def run_pipeline(
    *,
    profile: RuntimeProfile,
    tracer: TraceManager,
    prompt: str,
    history_json: str,
    audio: UploadFile | None,
    images: list[UploadFile],
    video: UploadFile | None,
    llm_model: str | None = None,
) -> dict[str, Any]:
    prepared = await prepare_pipeline_run(
        profile=profile,
        tracer=tracer,
        prompt=prompt,
        history_json=history_json,
        audio=audio,
        images=images,
        video=video,
        llm_model=llm_model,
    )

    assistant_text = await call_main_llm_non_stream(
        profile=profile,
        tracer=tracer,
        model=prepared.model,
        messages=prepared.messages,
    )

    await tracer.event("pipeline.done", data={"assistant_chars": len(assistant_text)})

    return {
        "assistant_text": assistant_text,
        "transcript": prepared.transcript,
        "video_summary": prepared.video_summary,
        "images_count": len(prepared.image_data_urls),
        "video_attached": video is not None,
        "models": {
            "voxtral": profile.voxtral.model,
            "nemotron": profile.nemotron.model,
            "main_llm": prepared.model,
        },
        "agent": {
            "id": str(profile.metadata.get("agent_id") or "porto.default"),
            "name": str(profile.metadata.get("agent_name") or "Port Default"),
        },
        "tools": [
            {
                "name": run.name,
                "status": run.status,
                "output": run.output,
            }
            for run in prepared.tool_runs
        ],
        "mcp_servers": profile.mcp_servers,
        "trace": tracer.export(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
