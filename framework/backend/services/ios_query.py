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
from backend.tools.registry import ToolRunResult, run_requested_tools
from backend.tracing.manager import TraceManager, build_trace_manager

logger = logging.getLogger(__name__)


def _build_tools_prompt_suffix(tool_runs: list[ToolRunResult]) -> str:
    """Build prompt suffix from tool outputs."""
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
    
    Args:
        session_id: The iOS session to send audio to
        query_id: Unique ID for this query
        audio_bytes: WAV audio data
        video_bytes: MP4 video data
        metadata: Query metadata from iOS
        profile: Runtime profile with API keys and settings
        tracer: Trace manager for logging
    """
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
        # 1. Transcribe audio (STT)
        transcript: str | None = None
        if audio_bytes:
            transcript = await transcribe_audio(
                profile=profile,
                tracer=tracer,
                audio=audio_bytes,
                content_type="audio/wav",
                filename="query.wav",
            )
            logger.info(f"Query {query_id}: transcript = {transcript[:100] if transcript else 'None'}...")
        
        # 2. Summarize video
        video_summary: str | None = None
        if video_bytes:
            video_data_url = to_data_url(video_bytes, "video/mp4")
            video_summary = await summarize_video(
                profile=profile,
                tracer=tracer,
                video_data_url=video_data_url,
                prompt_hint=transcript or "",
            )
            logger.info(f"Query {query_id}: video_summary = {video_summary[:100] if video_summary else 'None'}...")
        
        # 3. Run tools/skills
        tool_context = {
            "prompt": transcript or "",
            "transcript": transcript,
            "video_summary": video_summary,
            "history": [],
            "mcp_servers": profile.mcp_servers,
        }
        tool_runs = await run_requested_tools(
            profile=profile,
            tracer=tracer,
            context=tool_context,
        )
        
        # 4. Build LLM messages
        effective_prompt = (transcript or "") + _build_tools_prompt_suffix(tool_runs)
        messages = build_messages_for_main_llm(
            history=[],
            user_prompt=effective_prompt,
            audio_transcript=transcript,
            video_summary=video_summary,
            image_data_urls=[],
            system_prompt=profile.prompts["main_system_prompt"],
        )
        
        model = profile.main_llm.model
        
        await tracer.event(
            "ios_query.llm_start",
            data={"model": model, "messages_count": len(messages)},
        )
        
        # 5. Stream LLM tokens through TTS
        llm_token_stream = iter_main_llm_tokens(
            profile=profile,
            model=model,
            messages=messages,
            tracer=tracer,
            debug_capture=None,
        )
        
        # 6. Pipe through ElevenLabs with pcm_16000 format for iOS
        audio_stream, used_format = await prepare_elevenlabs_live_stream(
            profile=profile,
            tracer=tracer,
            text_iterator=llm_token_stream,
            voice_id=None,  # Use profile default
            model_id=None,
            speed=None,
            output_format="pcm_16000",  # Critical: iOS expects pcm_s16le @ 16kHz
        )
        
        logger.info(f"Query {query_id}: streaming audio to session {session_id} (format={used_format})")
        
        # 7. Stream audio back over WebSocket
        success = await stream_audio_bytes_to_session(
            session_id=session_id,
            response_id=query_id,
            audio_stream=audio_stream,
            chunk_size=6400,  # ~200ms at 16kHz mono 16-bit
        )
        
        if success:
            await tracer.event("ios_query.complete", data={"query_id": query_id})
            logger.info(f"Query {query_id}: audio delivery complete")
        else:
            await tracer.event(
                "ios_query.no_ws",
                status="error",
                data={"query_id": query_id, "session_id": session_id},
            )
            logger.warning(f"Query {query_id}: no WebSocket connection for session {session_id}")
    
    except Exception as exc:
        await tracer.event(
            "ios_query.error",
            status="error",
            data={"query_id": query_id, "error": str(exc)},
        )
        logger.exception(f"Query {query_id} failed: {exc}")
        raise


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
