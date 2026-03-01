"""iOS query processing service.

This module handles the processing of iOS query bundles through the pipeline
and streams the resulting audio back over WebSocket.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
from typing import Any

from backend.config.settings import SETTINGS
from backend.core.profile import RuntimeProfile, resolve_runtime_profile
from backend.core.utils import build_messages_for_main_llm, to_data_url
from backend.models.runtime import RuntimeConfig, parse_runtime_config
from backend.providers.elevenlabs import prepare_elevenlabs_live_stream
from backend.providers.mistral import iter_main_llm_tokens
from backend.providers.nvidia import summarize_video
from backend.providers.voxtral import transcribe_audio
from backend.routers.ws import stream_audio_bytes_to_session
from backend.services.run_log import RUN_LOG, RunLogEntry, _utc_now
from backend.tools.registry import ToolRunResult, run_requested_tools
from backend.tracing.manager import TraceManager, build_trace_manager

logger = logging.getLogger(__name__)


def _build_tools_context(tool_runs: list[ToolRunResult]) -> str | None:
    """Build a structured context string from tool outputs (or None if empty)."""
    if not tool_runs:
        return None

    serializable = [
        {
            "tool": item.name,
            "status": item.status,
            "output": item.output,
        }
        for item in tool_runs
    ]
    return json.dumps(serializable, ensure_ascii=False)


async def process_ios_query(
    session_id: str,
    query_id: str,
    audio_bytes: bytes,
    video_bytes: bytes,
    metadata: dict[str, Any],
    profile: RuntimeProfile,
    tracer: TraceManager,
) -> None:
    """Process an iOS query bundle through the pipeline and stream audio back.
    
    This function:
    1. Transcribes the audio (STT via Voxtral)
    2. Summarizes the video (via Nemotron)
    3. Runs configured tools/skills
    4. Builds LLM messages and streams tokens
    5. Pipes tokens through ElevenLabs TTS
    6. Streams audio chunks back over WebSocket
    
    Every run is recorded to the persistent run log for offline review.
    """
    run = RunLogEntry(
        query_id=query_id,
        session_id=session_id,
        source="ios_query",
        started_at=_utc_now(),
    )

    await tracer.event(
        "ios_query.start",
        data={
            "session_id": session_id,
            "query_id": query_id,
            "audio_bytes": len(audio_bytes),
            "video_bytes": len(video_bytes),
        },
    )
    
    try:
        # 1. Transcribe audio (STT) — tolerate empty transcripts gracefully
        transcript: str | None = None
        run.stt_model = profile.voxtral.model
        run.stt_audio_bytes = len(audio_bytes)
        if audio_bytes:
            try:
                transcript = await transcribe_audio(
                    profile=profile,
                    tracer=tracer,
                    audio=audio_bytes,
                    content_type="audio/wav",
                    filename="query.wav",
                )
                run.stt_transcript = transcript
            except Exception as stt_exc:
                run.stt_error = str(stt_exc)
                await tracer.event(
                    "ios_query.stt_skipped",
                    status="warning",
                    data={"query_id": query_id, "reason": str(stt_exc)},
                )
                logger.warning(f"Query {query_id}: STT failed, continuing without transcript: {stt_exc}")
            logger.info(f"Query {query_id}: transcript = {transcript[:100] if transcript else 'None'}...")
        
        # 2. Summarize video
        video_summary: str | None = None
        run.video_model = profile.nemotron.model
        if video_bytes:
            video_data_url = to_data_url(video_bytes, "video/mp4")
            try:
                video_summary = await summarize_video(
                    profile=profile,
                    tracer=tracer,
                    video_data_url=video_data_url,
                    prompt_hint=transcript or "",
                )
                run.video_summary = video_summary
            except Exception as vid_exc:
                run.video_error = str(vid_exc)
                logger.warning(f"Query {query_id}: video summarization failed: {vid_exc}")
            run.video_prompt_sent = str(profile.prompts.get("nemotron_video_prompt", ""))
            logger.info(f"Query {query_id}: video_summary = {video_summary[:100] if video_summary else 'None'}...")
        
        # 3. Run tools/skills
        tool_input = {
            "prompt": transcript or "",
            "transcript": transcript,
            "video_summary": video_summary,
            "history": [],
            "mcp_servers": profile.mcp_servers,
        }
        tool_runs = await run_requested_tools(
            profile=profile,
            tracer=tracer,
            context=tool_input,
        )
        run.tool_runs = [
            {"tool": item.name, "status": item.status, "output": item.output}
            for item in tool_runs
        ]
        
        # 4. Build LLM messages — each source is labelled for the main LLM
        tool_context = _build_tools_context(tool_runs)
        messages = build_messages_for_main_llm(
            history=[],
            user_prompt=transcript or "",
            audio_transcript=transcript,
            video_summary=video_summary,
            image_data_urls=[],
            system_prompt=profile.prompts["main_system_prompt"],
            tool_context=tool_context,
        )
        
        model = profile.main_llm.model
        run.main_llm_model = model
        run.main_llm_system_prompt = profile.prompts["main_system_prompt"]
        run.main_llm_messages_count = len(messages)

        # Record the user content that was actually sent
        user_msgs = [m for m in messages if m.get("role") == "user"]
        if user_msgs:
            content = user_msgs[-1].get("content", "")
            run.main_llm_user_content = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)[:2000]
        
        await tracer.event(
            "ios_query.llm_start",
            data={"model": model, "messages_count": len(messages)},
        )
        
        # 5. Stream LLM tokens through TTS — collect tokens for the run log
        collected_tokens: list[str] = []

        async def _logged_token_stream():
            async for token in iter_main_llm_tokens(
                profile=profile,
                model=model,
                messages=messages,
                tracer=tracer,
                debug_capture=None,
            ):
                collected_tokens.append(token)
                yield token

        # 6. Pipe through ElevenLabs with pcm_16000 format for iOS
        run.tts_model = profile.elevenlabs.model
        run.tts_voice_id = str(profile.options.get("elevenlabs_voice_id", ""))
        audio_stream, used_format = await prepare_elevenlabs_live_stream(
            profile=profile,
            tracer=tracer,
            text_iterator=_logged_token_stream(),
            voice_id=None,
            model_id=None,
            speed=None,
            output_format="pcm_16000",
        )
        
        logger.info(f"Query {query_id}: streaming audio to session {session_id} (format={used_format})")
        
        # 7. Stream audio back over WebSocket
        total_audio_bytes = 0
        
        async def _counting_audio_stream():
            nonlocal total_audio_bytes
            async for chunk in audio_stream:
                total_audio_bytes += len(chunk)
                yield chunk

        success = await stream_audio_bytes_to_session(
            session_id=session_id,
            response_id=query_id,
            audio_stream=_counting_audio_stream(),
            chunk_size=6400,
        )

        # Capture final LLM response text
        run.main_llm_response = "".join(collected_tokens).strip()
        run.main_llm_tokens = len(collected_tokens)
        run.tts_audio_bytes = total_audio_bytes

        if success:
            run.status = "ok"
            await tracer.event("ios_query.complete", data={"query_id": query_id})
            logger.info(f"Query {query_id}: audio delivery complete")
        else:
            run.status = "partial"
            run.tts_error = "No WebSocket connection"
            await tracer.event(
                "ios_query.no_ws",
                status="error",
                data={"query_id": query_id, "session_id": session_id},
            )
            logger.warning(f"Query {query_id}: no WebSocket connection for session {session_id}")
    
    except Exception as exc:
        run.status = "error"
        run.error = str(exc)
        await tracer.event(
            "ios_query.error",
            status="error",
            data={"query_id": query_id, "error": str(exc)},
        )
        logger.exception(f"Query {query_id} failed: {exc}")
        raise
    finally:
        # Always persist the run log, even on failure
        run.finished_at = _utc_now()
        run.metadata = {
            "agent_id": str(profile.metadata.get("agent_id", "")),
            "agent_name": str(profile.metadata.get("agent_name", "")),
        }
        RUN_LOG.record(run)
        logger.info(f"Query {query_id}: run log recorded (status={run.status})")


def create_mock_request():
    """Create a mock Request object for profile resolution.
    
    This is needed because resolve_runtime_profile expects a FastAPI Request
    to read optional API key headers, but for background processing we don't
    have a request context.
    """
    class MockRequest:
        def __init__(self):
            self.headers = {}
    return MockRequest()


async def process_ios_query_background(
    session_id: str,
    query_id: str,
    audio_bytes: bytes,
    video_bytes: bytes,
    metadata: dict[str, Any],
    runtime_config_json: str | None = None,
) -> None:
    """Background task wrapper for iOS query processing.
    
    This function handles profile resolution and tracer setup, then delegates
    to process_ios_query.
    """
    try:
        # Parse runtime config if provided
        runtime = parse_runtime_config(runtime_config_json)
        
        # Create mock request for profile resolution
        mock_request = create_mock_request()
        profile = resolve_runtime_profile(mock_request, runtime)
        
        # Build tracer
        tracer = build_trace_manager(profile.trace)
        
        # Process the query
        await process_ios_query(
            session_id=session_id,
            query_id=query_id,
            audio_bytes=audio_bytes,
            video_bytes=video_bytes,
            metadata=metadata,
            profile=profile,
            tracer=tracer,
        )
    
    except Exception as exc:
        logger.exception(f"Background processing failed for query {query_id}: {exc}")
