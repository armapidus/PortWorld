from __future__ import annotations

import itertools
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.settings import settings
from backend.ws.binary_dispatch import dispatch_binary_frame
from backend.ws.control_dispatch import dispatch_control_envelope, parse_control_envelope
from backend.ws.contracts import make_envelope
from backend.ws.frame_codec import encode_frame
from backend.ws.session_registry import SessionRecord
from backend.ws.session_runtime import deactivate_and_unregister_session, trace_ws_message
from backend.ws.telemetry import SessionTelemetry

router = APIRouter()
logger = logging.getLogger(__name__)
_connection_ids = itertools.count(1)


@router.websocket("/ws/session")
async def ws_session(websocket: WebSocket) -> None:
    await websocket.accept()
    connection_id = next(_connection_ids)

    active_session: SessionRecord | None = None
    telemetry = SessionTelemetry(
        connection_id=connection_id,
        uplink_ack_every_n_frames=settings.openai_realtime_uplink_ack_every_n_frames,
    )

    async def send_control(
        message_type: str,
        payload: dict[str, Any],
        *,
        target: SessionRecord | None = None,
        fallback_session_id: str = "unknown",
    ) -> None:
        session = target or active_session
        if session is None:
            envelope = make_envelope(
                message_type=message_type,
                session_id=fallback_session_id,
                seq=0,
                payload=payload,
            )
        else:
            envelope = make_envelope(
                message_type=message_type,
                session_id=session.session_id,
                seq=session.next_seq(),
                payload=payload,
            )
        await websocket.send_json(envelope.model_dump())

    async def send_server_audio(frame_type: int, ts_ms: int, payload_bytes: bytes) -> None:
        encoded = encode_frame(frame_type, ts_ms, payload_bytes)
        await websocket.send_bytes(encoded)

    try:
        while True:
            message = await websocket.receive()
            message_type = message.get("type")
            telemetry.log_receive_shape(message)
            trace_ws_message(
                message,
                active_session=active_session,
                connection_id=connection_id,
            )

            if message_type == "websocket.disconnect":
                break
            if message_type != "websocket.receive":
                continue

            raw_bytes = message.get("bytes")
            if raw_bytes is not None:
                handled = await dispatch_binary_frame(
                    raw_bytes=raw_bytes,
                    active_session=active_session,
                    send_control=send_control,
                    telemetry=telemetry,
                    connection_id=connection_id,
                )
                if handled:
                    continue

            raw_text = message.get("text")
            if raw_text is None:
                continue

            envelope = await parse_control_envelope(
                raw_text=raw_text,
                active_session=active_session,
                send_control=send_control,
            )
            if envelope is None:
                continue

            dispatch_result = await dispatch_control_envelope(
                envelope=envelope,
                active_session=active_session,
                websocket=websocket,
                send_control=send_control,
                send_server_audio=send_server_audio,
                telemetry=telemetry,
            )
            active_session = dispatch_result.active_session
            if not dispatch_result.handled:
                logger.info(
                    "Ignoring unsupported control type=%s session=%s",
                    envelope.type,
                    envelope.session_id,
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    finally:
        if active_session is not None:
            await deactivate_and_unregister_session(
                active_session=active_session,
                websocket=websocket,
                send_control=send_control,
                emit_session_state=False,
            )
