"""WebSocket router for iOS client connections.

Implements the exact envelope protocol expected by the iOS app:
- session.activate / session.deactivate
- health.ping / health.pong
- assistant.audio_chunk / assistant.playback.control
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.ws.state import (
    SessionState,
    get_session,
    register_session,
    unregister_session,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def now_ms() -> int:
    """Current timestamp in milliseconds."""
    return int(time.time() * 1000)


def build_envelope(
    message_type: str,
    session_id: str,
    payload: dict[str, Any],
    seq: int,
) -> dict[str, Any]:
    """Build a WebSocket message envelope matching iOS expectations."""
    return {
        "type": message_type,
        "session_id": session_id,
        "seq": seq,
        "ts_ms": now_ms(),
        "payload": payload,
    }


async def send_envelope(
    websocket: WebSocket,
    session_state: SessionState,
    message_type: str,
    payload: dict[str, Any],
) -> None:
    """Send a properly formatted envelope over WebSocket."""
    envelope = build_envelope(
        message_type=message_type,
        session_id=session_state.session_id,
        payload=payload,
        seq=session_state.next_seq(),
    )
    await websocket.send_json(envelope)


async def send_error(
    websocket: WebSocket,
    session_state: SessionState,
    code: str,
    message: str,
    retriable: bool = False,
) -> None:
    """Send an error envelope."""
    await send_envelope(
        websocket=websocket,
        session_state=session_state,
        message_type="error",
        payload={
            "code": code,
            "message": message,
            "retriable": retriable,
        },
    )


@router.websocket("/ws/session")
async def ws_session(websocket: WebSocket) -> None:
    """WebSocket endpoint for iOS session management.

    Protocol:
    - Client connects and sends envelopes with type, session_id, seq, ts_ms, payload
    - On session.activate: register session, respond with session.state
    - On session.deactivate: unregister, respond with session.state
    - On health.ping: respond with health.pong
    - Audio is pushed from /v1/query background tasks via stream_audio_to_session()
    """
    await websocket.accept()

    # Start with unknown session, will be set on first message
    session_state: SessionState | None = None
    active_session_id = "unknown"

    logger.info(f"WebSocket connected, waiting for session.activate")

    try:
        while True:
            # Receive message (text or bytes)
            message = await websocket.receive()
            message_type = message.get("type")

            if message_type == "websocket.disconnect":
                break
            if message_type != "websocket.receive":
                continue

            # Parse raw message
            raw_message = message.get("text")
            if raw_message is None:
                raw_bytes = message.get("bytes")
                if raw_bytes is None:
                    continue
                try:
                    raw_message = raw_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    logger.warning(
                        f"Non-UTF8 WebSocket payload from {active_session_id}"
                    )
                    continue

            # Parse JSON envelope
            try:
                envelope = json.loads(raw_message)
            except json.JSONDecodeError as exc:
                logger.warning(f"Invalid JSON from {active_session_id}: {exc}")
                if session_state:
                    await send_error(
                        websocket=websocket,
                        session_state=session_state,
                        code="WS_PROTOCOL_ERROR",
                        message="Invalid JSON payload",
                        retriable=False,
                    )
                continue

            msg_type = envelope.get("type", "")
            session_id = envelope.get("session_id", "unknown")
            payload = envelope.get("payload", {})

            # Handle session registration / update
            if session_id != active_session_id:
                active_session_id = session_id
                session_state = await register_session(session_id, websocket)

            logger.info(f"WS received: type={msg_type} session={session_id}")

            # Route message to handler
            await handle_client_message(
                websocket=websocket,
                session_state=session_state,
                msg_type=msg_type,
                payload=payload,
            )

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: session={active_session_id}")
    except Exception as exc:
        logger.exception(f"WebSocket error for session={active_session_id}: {exc}")
    finally:
        if active_session_id != "unknown":
            await unregister_session(active_session_id)


async def handle_client_message(
    websocket: WebSocket,
    session_state: SessionState | None,
    msg_type: str,
    payload: dict[str, Any],
) -> None:
    """Handle an inbound client message."""
    if session_state is None:
        logger.warning("Received message before session was established")
        return

    if msg_type == "session.activate":
        await send_envelope(
            websocket=websocket,
            session_state=session_state,
            message_type="session.state",
            payload={"state": "active", "detail": "connected"},
        )
        logger.info(f"Session {session_state.session_id} activated")

        # Optionally send greeting audio (can be enabled later)
        # asyncio.create_task(stream_greeting_audio(websocket, session_state))
        return

    if msg_type == "session.deactivate":
        await send_envelope(
            websocket=websocket,
            session_state=session_state,
            message_type="session.state",
            payload={"state": "ended", "detail": "deactivated"},
        )
        logger.info(f"Session {session_state.session_id} deactivated")
        return

    if msg_type == "health.ping":
        await send_envelope(
            websocket=websocket,
            session_state=session_state,
            message_type="health.pong",
            payload={"ok": True},
        )
        return

    if msg_type == "health.stats":
        # Log stats but don't respond
        logger.info(f"Health stats from {session_state.session_id}: {payload}")
        return

    if msg_type == "query.bundle.uploaded":
        # Log for traceability - the actual audio push happens from /v1/query
        logger.info(
            f"Query bundle uploaded notification from {session_state.session_id}: {payload}"
        )
        return

    if msg_type == "wakeword.detected":
        logger.info(f"Wakeword detected from {session_state.session_id}: {payload}")
        return

    if msg_type == "query.started":
        logger.info(f"Query started from {session_state.session_id}: {payload}")
        return

    if msg_type == "query.ended":
        logger.info(f"Query ended from {session_state.session_id}: {payload}")
        return

    if msg_type == "error":
        logger.warning(f"Client error from {session_state.session_id}: {payload}")
        return

    # Unknown message type - log but don't error
    logger.warning(f"Unknown message type '{msg_type}' from {session_state.session_id}")


async def stream_audio_to_session(
    session_id: str,
    response_id: str,
    audio_chunks: list[tuple[bytes, int]],  # List of (pcm_bytes, duration_ms)
) -> bool:
    """Stream audio chunks to a connected iOS session.

    Called from the /v1/query background task after pipeline processing.

    Args:
        session_id: The session to send audio to
        response_id: Unique ID for this response (usually query_id)
        audio_chunks: List of (pcm_bytes, duration_ms) tuples

    Returns:
        True if audio was delivered, False if session not found
    """
    session_state = get_session(session_id)
    if session_state is None:
        logger.warning(f"Cannot stream audio: no WebSocket for session {session_id}")
        return False

    websocket = session_state.websocket

    try:
        # Send playback start
        await send_envelope(
            websocket=websocket,
            session_state=session_state,
            message_type="assistant.playback.control",
            payload={"command": "start_response", "response_id": response_id},
        )

        # Send audio chunks
        for idx, (pcm_bytes, duration_ms) in enumerate(audio_chunks):
            is_last = idx == len(audio_chunks) - 1
            chunk_id = f"{response_id}_{idx + 1}"

            await send_envelope(
                websocket=websocket,
                session_state=session_state,
                message_type="assistant.audio_chunk",
                payload={
                    "response_id": response_id,
                    "chunk_id": chunk_id,
                    "codec": "pcm_s16le",
                    "sample_rate": 16000,
                    "channels": 1,
                    "duration_ms": duration_ms,
                    "is_last": is_last,
                    "bytes_b64": base64.b64encode(pcm_bytes).decode("ascii"),
                },
            )

        # Send playback stop
        await send_envelope(
            websocket=websocket,
            session_state=session_state,
            message_type="assistant.playback.control",
            payload={"command": "stop_response", "response_id": response_id},
        )

        logger.info(
            f"Streamed {len(audio_chunks)} audio chunks to session {session_id}"
        )
        return True

    except Exception as exc:
        logger.exception(f"Failed to stream audio to session {session_id}: {exc}")
        return False


async def stream_audio_bytes_to_session(
    session_id: str,
    response_id: str,
    audio_stream,  # AsyncIterator[bytes]
    chunk_size: int = 6400,  # ~200ms at 16kHz mono 16-bit
) -> bool:
    """Stream raw PCM bytes to a connected iOS session, chunking as we go.

    This version takes an async iterator of raw PCM bytes (from ElevenLabs)
    and chunks them into ~200ms segments for the iOS playback engine.

    Args:
        session_id: The session to send audio to
        response_id: Unique ID for this response (usually query_id)
        audio_stream: Async iterator yielding raw PCM bytes
        chunk_size: Bytes per chunk (default 6400 = 200ms at 16kHz/16bit/mono)

    Returns:
        True if audio was delivered, False if session not found
    """
    session_state = get_session(session_id)
    if session_state is None:
        logger.warning(f"Cannot stream audio: no WebSocket for session {session_id}")
        return False

    websocket = session_state.websocket

    try:
        # Send playback start
        await send_envelope(
            websocket=websocket,
            session_state=session_state,
            message_type="assistant.playback.control",
            payload={"command": "start_response", "response_id": response_id},
        )

        # Send a short silent preamble before the first real audio chunk.
        # Historically this was needed because the iOS client reset the player
        # node and reconfigured the AVAudioEngine graph on `start_response`,
        # which could cause the first buffer to be partially dropped. The
        # current iOS implementation no longer calls `playerNode.reset()`, so
        # this 150ms of silence mainly adds a small fixed latency/byte overhead
        # but is kept for now as a conservative, backwards-compatible buffer.
        preamble_samples = int(16000 * 0.15)  # 150ms @ 16 kHz
        preamble_bytes = bytes(preamble_samples * 2)  # 16-bit zeros = silence
        await send_envelope(
            websocket=websocket,
            session_state=session_state,
            message_type="assistant.audio_chunk",
            payload={
                "response_id": response_id,
                "chunk_id": f"{response_id}_preamble",
                "codec": "pcm_s16le",
                "sample_rate": 16000,
                "channels": 1,
                "duration_ms": 150,
                "is_last": False,
                "bytes_b64": base64.b64encode(preamble_bytes).decode("ascii"),
            },
        )

        buffer = bytearray()
        chunk_idx = 0

        async for audio_bytes in audio_stream:
            buffer.extend(audio_bytes)

            # Send full chunks as they accumulate
            while len(buffer) >= chunk_size:
                chunk_data = bytes(buffer[:chunk_size])
                buffer = buffer[chunk_size:]
                chunk_idx += 1

                # 16kHz * 2 bytes/sample = 32 bytes/ms => duration_ms = len / 32
                duration_ms = len(chunk_data) // 32

                await send_envelope(
                    websocket=websocket,
                    session_state=session_state,
                    message_type="assistant.audio_chunk",
                    payload={
                        "response_id": response_id,
                        "chunk_id": f"{response_id}_{chunk_idx}",
                        "codec": "pcm_s16le",
                        "sample_rate": 16000,
                        "channels": 1,
                        "duration_ms": duration_ms,
                        "is_last": False,
                        "bytes_b64": base64.b64encode(chunk_data).decode("ascii"),
                    },
                )

        # Flush remaining buffer as final chunk
        if buffer:
            chunk_idx += 1
            duration_ms = len(buffer) // 32

            await send_envelope(
                websocket=websocket,
                session_state=session_state,
                message_type="assistant.audio_chunk",
                payload={
                    "response_id": response_id,
                    "chunk_id": f"{response_id}_{chunk_idx}",
                    "codec": "pcm_s16le",
                    "sample_rate": 16000,
                    "channels": 1,
                    "duration_ms": duration_ms,
                    "is_last": True,
                    "bytes_b64": base64.b64encode(bytes(buffer)).decode("ascii"),
                },
            )
        elif chunk_idx > 0:
            # No remaining buffer but we sent chunks - mark last one
            # This case shouldn't happen often, but handle it gracefully
            pass

        # Send playback stop
        await send_envelope(
            websocket=websocket,
            session_state=session_state,
            message_type="assistant.playback.control",
            payload={"command": "stop_response", "response_id": response_id},
        )

        logger.info(f"Streamed {chunk_idx} audio chunks to session {session_id}")
        return True

    except Exception as exc:
        logger.exception(f"Failed to stream audio to session {session_id}: {exc}")
        return False


async def send_thinking_to_session(session_id: str, query_id: str) -> bool:
    """Send an instant 'assistant.thinking' acknowledgment to a connected iOS session.

    Called at the very start of query processing so the user gets immediate
    feedback (haptic/visual) that their query was received — before any STT,
    video, or LLM work begins.

    Returns True if delivered, False if the session is not connected.
    """
    session_state = get_session(session_id)
    if session_state is None:
        logger.warning(
            f"Cannot send thinking ack: no WebSocket for session {session_id}"
        )
        return False

    try:
        await send_envelope(
            websocket=session_state.websocket,
            session_state=session_state,
            message_type="assistant.thinking",
            payload={"status": "received", "query_id": query_id},
        )
        logger.info(
            f"Sent assistant.thinking to session {session_id} for query {query_id}"
        )
        return True
    except Exception as exc:
        logger.warning(f"Failed to send thinking ack to session {session_id}: {exc}")
        return False
