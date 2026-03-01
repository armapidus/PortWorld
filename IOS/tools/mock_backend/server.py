from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
import os
import random
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
load_dotenv()  # Load .env file before reading env vars

from elevenlabs import ElevenLabs
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

# ElevenLabs configuration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")  # George voice
GREETING_TEXT = os.getenv("GREETING_TEXT", "Hey Pierre, how can I help you today?")

app = FastAPI(title="MetaCollectLuigi Mock Backend", version="0.1.0")

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("mock-backend")

RUN_ID = os.getenv("RUN_ID", f"run-{int(time.time())}")
DEFAULT_FAULT_PROFILE = os.getenv("FAULT_PROFILE", "")

# Capture directory for storing received data
_SERVER_DIR = Path(__file__).parent
CAPTURE_DIR = Path(os.getenv("CAPTURE_DIR", str(_SERVER_DIR / "captures" / RUN_ID)))
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
logger.info(f"Capture directory: {CAPTURE_DIR}")


@dataclass
class FaultConfig:
    latency_ms: int = 0
    vision_5xx_every: int = 0
    query_5xx_every: int = 0
    ws_drop_after: int = 0
    malformed_ws_once: bool = False
    no_audio: bool = False


class RuntimeState:
    def __init__(self) -> None:
        self.vision_count = 0
        self.query_count = 0
        self.ws_message_count = 0
        self.malformed_sent = False
        self.ws_clients: dict[str, set[WebSocket]] = {}
        self.ws_seq_by_session: dict[str, int] = {}


state = RuntimeState()


def parse_fault_profile(raw: str | None) -> FaultConfig:
    if not raw:
        return FaultConfig()

    profile = FaultConfig()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue

        if "=" in token:
            key, value = token.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key == "latency_ms":
                profile.latency_ms = max(0, int(value))
            elif key == "vision_5xx_every":
                profile.vision_5xx_every = max(0, int(value))
            elif key == "query_5xx_every":
                profile.query_5xx_every = max(0, int(value))
            elif key == "ws_drop_after":
                profile.ws_drop_after = max(0, int(value))
            elif key == "malformed_ws_once":
                profile.malformed_ws_once = value.lower() in {"1", "true", "yes", "on"}
            elif key == "no_audio":
                profile.no_audio = value.lower() in {"1", "true", "yes", "on"}
            continue

        if token == "latency":
            profile.latency_ms = 500
        elif token == "flaky_vision":
            profile.vision_5xx_every = 3
        elif token == "flaky_query":
            profile.query_5xx_every = 2
        elif token == "drop_ws":
            profile.ws_drop_after = 5
        elif token == "malformed":
            profile.malformed_ws_once = True
        elif token == "no_audio":
            profile.no_audio = True

    return profile


def resolve_fault_profile(header_value: str | None, query_value: str | None) -> FaultConfig:
    raw = query_value or header_value or DEFAULT_FAULT_PROFILE
    return parse_fault_profile(raw)


def now_ms() -> int:
    return int(time.time() * 1000)


def log_event(event: str, **fields: Any) -> None:
    payload = {"run_id": RUN_ID, "ts_ms": now_ms(), "event": event, **fields}
    logger.info(json.dumps(payload, sort_keys=True))


# --- Data Capture Helpers ---

def capture_vision_frame(session_id: str, frame_id: str, frame_b64: str, ts_ms: int) -> None:
    """Save a vision frame and its metadata to disk."""
    vision_dir = CAPTURE_DIR / "vision" / session_id
    vision_dir.mkdir(parents=True, exist_ok=True)

    # Decode and write the frame image
    try:
        frame_bytes = base64.b64decode(frame_b64)
        (vision_dir / f"{frame_id}.jpg").write_bytes(frame_bytes)
    except Exception as exc:
        log_event("capture.vision.error", session_id=session_id, frame_id=frame_id, reason=str(exc))
        return

    # Write metadata sidecar
    metadata = {"session_id": session_id, "frame_id": frame_id, "ts_ms": ts_ms, "captured_at": now_ms()}
    (vision_dir / f"{frame_id}.json").write_text(json.dumps(metadata, indent=2))


def capture_query_bundle(
    session_id: str, query_id: str, metadata_obj: dict[str, Any], audio_bytes: bytes, video_bytes: bytes,
    audio_filename: str | None, video_filename: str | None
) -> None:
    """Save a query bundle (metadata, audio, video) to disk."""
    query_dir = CAPTURE_DIR / "query" / session_id / query_id
    query_dir.mkdir(parents=True, exist_ok=True)

    # Write metadata
    (query_dir / "metadata.json").write_text(json.dumps(metadata_obj, indent=2))

    # Determine file extensions
    audio_ext = Path(audio_filename).suffix if audio_filename else ".bin"
    video_ext = Path(video_filename).suffix if video_filename else ".bin"
    if not audio_ext:
        audio_ext = ".bin"
    if not video_ext:
        video_ext = ".bin"

    # Write audio and video
    (query_dir / f"audio{audio_ext}").write_bytes(audio_bytes)
    (query_dir / f"video{video_ext}").write_bytes(video_bytes)


def capture_ws_message(session_id: str, envelope: dict[str, Any]) -> None:
    """Append a WebSocket message to the session's message log."""
    ws_dir = CAPTURE_DIR / "ws" / session_id
    ws_dir.mkdir(parents=True, exist_ok=True)

    # Add capture timestamp
    record = {"captured_at": now_ms(), **envelope}
    with (ws_dir / "messages.jsonl").open("a") as f:
        f.write(json.dumps(record) + "\n")


def next_ws_seq(session_id: str) -> int:
    current = state.ws_seq_by_session.get(session_id, 0) + 1
    state.ws_seq_by_session[session_id] = current
    return current


def build_envelope(message_type: str, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": message_type,
        "session_id": session_id,
        "seq": next_ws_seq(session_id),
        "ts_ms": now_ms(),
        "payload": payload,
    }


# μ-law decoding table for converting telephony audio to PCM
# μ-law is an 8-bit companding algorithm used in telephony (ITU-T G.711)
ULAW_DECODE_TABLE = [
    -32124, -31100, -30076, -29052, -28028, -27004, -25980, -24956,
    -23932, -22908, -21884, -20860, -19836, -18812, -17788, -16764,
    -15996, -15484, -14972, -14460, -13948, -13436, -12924, -12412,
    -11900, -11388, -10876, -10364, -9852, -9340, -8828, -8316,
    -7932, -7676, -7420, -7164, -6908, -6652, -6396, -6140,
    -5884, -5628, -5372, -5116, -4860, -4604, -4348, -4092,
    -3900, -3772, -3644, -3516, -3388, -3260, -3132, -3004,
    -2876, -2748, -2620, -2492, -2364, -2236, -2108, -1980,
    -1884, -1820, -1756, -1692, -1628, -1564, -1500, -1436,
    -1372, -1308, -1244, -1180, -1116, -1052, -988, -924,
    -876, -844, -812, -780, -748, -716, -684, -652,
    -620, -588, -556, -524, -492, -460, -428, -396,
    -372, -356, -340, -324, -308, -292, -276, -260,
    -244, -228, -212, -196, -180, -164, -148, -132,
    -120, -112, -104, -96, -88, -80, -72, -64,
    -56, -48, -40, -32, -24, -16, -8, 0,
    32124, 31100, 30076, 29052, 28028, 27004, 25980, 24956,
    23932, 22908, 21884, 20860, 19836, 18812, 17788, 16764,
    15996, 15484, 14972, 14460, 13948, 13436, 12924, 12412,
    11900, 11388, 10876, 10364, 9852, 9340, 8828, 8316,
    7932, 7676, 7420, 7164, 6908, 6652, 6396, 6140,
    5884, 5628, 5372, 5116, 4860, 4604, 4348, 4092,
    3900, 3772, 3644, 3516, 3388, 3260, 3132, 3004,
    2876, 2748, 2620, 2492, 2364, 2236, 2108, 1980,
    1884, 1820, 1756, 1692, 1628, 1564, 1500, 1436,
    1372, 1308, 1244, 1180, 1116, 1052, 988, 924,
    876, 844, 812, 780, 748, 716, 684, 652,
    620, 588, 556, 524, 492, 460, 428, 396,
    372, 356, 340, 324, 308, 292, 276, 260,
    244, 228, 212, 196, 180, 164, 148, 132,
    120, 112, 104, 96, 88, 80, 72, 64,
    56, 48, 40, 32, 24, 16, 8, 0,
]


def ulaw_to_pcm(ulaw_byte: int) -> int:
    """Convert a single μ-law byte to 16-bit PCM sample."""
    return ULAW_DECODE_TABLE[ulaw_byte]


def generate_pcm_s16le_tone_b64(sample_rate: int = 16000, duration_ms: int = 220) -> str:
    total_samples = int(sample_rate * (duration_ms / 1000.0))
    freq_hz = random.choice([440.0, 523.25, 659.25])
    amp = 0.22
    raw = bytearray()

    for i in range(total_samples):
        t = i / sample_rate
        sample = int(max(-1.0, min(1.0, amp * math.sin(2 * math.pi * freq_hz * t))) * 32767)
        raw.extend(struct.pack("<h", sample))

    return base64.b64encode(bytes(raw)).decode("ascii")


async def maybe_sleep(profile: FaultConfig) -> None:
    if profile.latency_ms > 0:
        await asyncio.sleep(profile.latency_ms / 1000.0)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "run_id": RUN_ID,
        "vision_count": state.vision_count,
        "query_count": state.query_count,
        "ws_message_count": state.ws_message_count,
    }


@app.post("/vision/frame")
async def post_vision_frame(
    payload: dict[str, Any],
    x_fault_profile: str | None = Header(default=None),
    fault: str | None = Query(default=None),
) -> JSONResponse:
    profile = resolve_fault_profile(x_fault_profile, fault)
    await maybe_sleep(profile)

    session_id = payload.get("session_id")
    frame_id = payload.get("frame_id")
    frame_b64 = payload.get("frame_b64")
    ts_ms = payload.get("ts_ms")

    if not session_id or not frame_id or not frame_b64 or ts_ms is None:
        raise HTTPException(status_code=400, detail="Missing required fields")

    state.vision_count += 1

    # Capture the frame data before any fault injection
    capture_vision_frame(session_id, frame_id, frame_b64, ts_ms)

    if profile.vision_5xx_every > 0 and state.vision_count % profile.vision_5xx_every == 0:
        log_event("vision.frame.failed", reason="injected_5xx", session_id=session_id, frame_id=frame_id)
        return JSONResponse(status_code=503, content={"status": "error", "reason": "injected_vision_failure"})

    log_event("vision.frame.received", session_id=session_id, frame_id=frame_id, bytes=len(frame_b64))
    return JSONResponse(content={"status": "ok", "frame_id": frame_id})


@app.post("/query")
async def post_query_bundle(
    metadata: str = Form(...),
    audio: UploadFile = File(...),
    video: UploadFile = File(...),
    x_fault_profile: str | None = Header(default=None),
    fault: str | None = Query(default=None),
) -> JSONResponse:
    profile = resolve_fault_profile(x_fault_profile, fault)
    await maybe_sleep(profile)

    try:
        metadata_obj = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid metadata JSON: {exc}")

    query_id = metadata_obj.get("query_id")
    session_id = metadata_obj.get("session_id")
    if not query_id or not session_id:
        raise HTTPException(status_code=400, detail="metadata.session_id and metadata.query_id are required")

    audio_bytes = await audio.read()
    video_bytes = await video.read()

    state.query_count += 1

    # Capture the query bundle data before any fault injection
    capture_query_bundle(
        session_id=session_id,
        query_id=query_id,
        metadata_obj=metadata_obj,
        audio_bytes=audio_bytes,
        video_bytes=video_bytes,
        audio_filename=audio.filename,
        video_filename=video.filename,
    )

    if profile.query_5xx_every > 0 and state.query_count % profile.query_5xx_every == 0:
        log_event("query.bundle.failed", reason="injected_5xx", session_id=session_id, query_id=query_id)
        return JSONResponse(status_code=503, content={"status": "error", "reason": "injected_query_failure"})

    log_event(
        "query.bundle.received",
        session_id=session_id,
        query_id=query_id,
        audio_bytes=len(audio_bytes),
        video_bytes=len(video_bytes),
    )

    if not profile.no_audio:
        asyncio.create_task(stream_mock_assistant_audio(session_id=session_id, query_id=query_id))

    return JSONResponse(content={"status": "ok", "query_id": query_id, "processing": True})


@app.get("/ws/session")
async def ws_info() -> dict[str, Any]:
    return {"status": "ok", "path": "/ws/session", "run_id": RUN_ID}


@app.websocket("/ws/session")
async def ws_session(websocket: WebSocket) -> None:
    await websocket.accept()

    active_session_id = "unknown"
    state.ws_clients.setdefault(active_session_id, set()).add(websocket)
    log_event("ws.connected", session_id=active_session_id)

    try:
        while True:
            message = await websocket.receive()
            message_type = message.get("type")
            if message_type == "websocket.disconnect":
                break
            if message_type != "websocket.receive":
                continue

            raw_message = message.get("text")
            if raw_message is None:
                raw_bytes = message.get("bytes")
                if raw_bytes is None:
                    continue
                try:
                    raw_message = raw_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    log_event("ws.protocol_error", session_id=active_session_id, reason="non_utf8_payload")
                    continue

            state.ws_message_count += 1

            try:
                envelope = json.loads(raw_message)
            except json.JSONDecodeError as exc:
                log_event("ws.protocol_error", session_id=active_session_id, reason="invalid_json", detail=str(exc))
                try:
                    await websocket.send_json(
                        build_envelope(
                            "error",
                            active_session_id,
                            {
                                "code": "WS_PROTOCOL_ERROR",
                                "retriable": False,
                                "message": "Invalid JSON payload",
                            },
                        )
                    )
                except RuntimeError:
                    pass
                continue

            msg_type = envelope.get("type", "")
            session_id = envelope.get("session_id", "unknown")
            payload = envelope.get("payload", {})

            if session_id != active_session_id:
                if websocket in state.ws_clients.get(active_session_id, set()):
                    state.ws_clients[active_session_id].discard(websocket)
                state.ws_clients.setdefault(session_id, set()).add(websocket)
                active_session_id = session_id

            profile = resolve_fault_profile(None, None)
            if profile.malformed_ws_once and not state.malformed_sent:
                state.malformed_sent = True
                await websocket.send_text("{malformed_json")
                log_event("ws.malformed.sent", session_id=session_id)

            if profile.ws_drop_after > 0 and state.ws_message_count >= profile.ws_drop_after:
                log_event("ws.drop.injected", session_id=session_id, after_messages=state.ws_message_count)
                await websocket.close(code=1011, reason="Injected ws_drop_after")
                break

            log_event("ws.received", session_id=session_id, type=msg_type)
            capture_ws_message(session_id, envelope)
            await handle_client_message(websocket, session_id, msg_type, payload)

    except WebSocketDisconnect:
        log_event("ws.disconnected", session_id=active_session_id)
    except Exception as exc:
        log_event("ws.error", session_id=active_session_id, message=str(exc))
    finally:
        if websocket in state.ws_clients.get(active_session_id, set()):
            state.ws_clients[active_session_id].discard(websocket)


async def handle_client_message(websocket: WebSocket, session_id: str, msg_type: str, payload: dict[str, Any]) -> None:
    if msg_type == "session.activate":
        await websocket.send_json(build_envelope("session.state", session_id, {"state": "active", "detail": "mock_active"}))
        # Stream greeting audio to the user
        asyncio.create_task(stream_greeting_audio(websocket, session_id))
        return

    if msg_type == "session.deactivate":
        await websocket.send_json(build_envelope("session.state", session_id, {"state": "ended", "detail": "mock_ended"}))
        return

    if msg_type == "health.ping":
        await websocket.send_json(build_envelope("health.pong", session_id, {"ok": True}))
        return

    if msg_type == "health.stats":
        log_event("health.stats", session_id=session_id, fields=payload)
        return

    if msg_type == "query.bundle.uploaded":
        # `/query` already triggers audio by default; keep this event for logging/traceability only.
        log_event("query.bundle.uploaded", session_id=session_id, payload=payload)
        return


async def stream_mock_assistant_audio(session_id: str, query_id: str) -> None:
    clients = list(state.ws_clients.get(session_id, set()))
    if not clients:
        return

    start_payload = {"command": "start_response", "response_id": query_id}
    chunk_payload = {
        "response_id": query_id,
        "chunk_id": f"{query_id}_1",
        "codec": "pcm_s16le",
        "sample_rate": 16000,
        "channels": 1,
        "duration_ms": 220,
        "is_last": True,
        "bytes_b64": generate_pcm_s16le_tone_b64(sample_rate=16000, duration_ms=220),
    }
    stop_payload = {"command": "stop_response", "response_id": query_id}

    for client in clients:
        try:
            await client.send_json(build_envelope("assistant.playback.control", session_id, start_payload))
            await client.send_json(build_envelope("assistant.audio_chunk", session_id, chunk_payload))
            await client.send_json(build_envelope("assistant.playback.control", session_id, stop_payload))
        except RuntimeError:
            continue

    log_event("assistant.audio.sent", session_id=session_id, query_id=query_id, chunks=1)


async def stream_greeting_audio(websocket: WebSocket, session_id: str) -> None:
    """Stream a greeting message to the user via ElevenLabs TTS.
    
    If ELEVENLABS_API_KEY is not set, falls back to a simple mock tone.
    """
    # Wait for the glasses' "Experience started" system announcement to finish
    # before playing our greeting audio. 4s observed to be sufficient in practice:
    # 2s caused overlap with the system announcement; 10s risked WebSocket staleness.
    await asyncio.sleep(4)
    
    response_id = f"greeting_{session_id}_{int(time.time() * 1000)}"
    
    # Send playback start control
    start_payload = {"command": "start_response", "response_id": response_id}
    try:
        await websocket.send_json(build_envelope("assistant.playback.control", session_id, start_payload))
    except RuntimeError:
        log_event("greeting.audio.error", session_id=session_id, reason="websocket_closed")
        return

    if not ELEVENLABS_API_KEY:
        # Fallback to mock tone if no API key (8kHz for HFP compatibility)
        log_event("greeting.audio.fallback", session_id=session_id, reason="no_api_key")
        chunk_payload = {
            "response_id": response_id,
            "chunk_id": f"{response_id}_1",
            "codec": "pcm_s16le",
            "sample_rate": 16000,
            "channels": 1,
            "duration_ms": 500,
            "is_last": True,
            "bytes_b64": generate_pcm_s16le_tone_b64(sample_rate=16000, duration_ms=500),
        }
        try:
            await websocket.send_json(build_envelope("assistant.audio_chunk", session_id, chunk_payload))
        except RuntimeError:
            pass
    else:
        # Use ElevenLabs TTS
        try:
            client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            
            # Get TTS audio with μ-law 8kHz format (HFP uses 8kHz for voice)
            # Then convert to PCM s16le for the playback engine
            audio_stream = client.text_to_speech.convert(
                text=GREETING_TEXT,
                voice_id=ELEVENLABS_VOICE_ID,
                model_id="eleven_flash_v2_5",  # Low latency model
                output_format="pcm_16000",  # 16kHz linear PCM s16le — no companding round-trip
            )
            
            # Accumulate all audio data (already raw PCM s16le little-endian)
            all_pcm = bytearray()
            for audio_chunk in audio_stream:
                all_pcm.extend(audio_chunk)
            
            if all_pcm:
                audio_bytes = bytes(all_pcm)
                # 16-bit samples → frame count = byte_count / 2; duration = frames / 16000
                sample_count = len(audio_bytes) // 2
                duration_ms = int(sample_count / 16000 * 1000)
                
                chunk_payload = {
                    "response_id": response_id,
                    "chunk_id": f"{response_id}_1",
                    "codec": "pcm_s16le",
                    "sample_rate": 16000,
                    "channels": 1,
                    "duration_ms": duration_ms,
                    "is_last": True,
                    "bytes_b64": base64.b64encode(audio_bytes).decode("ascii"),
                }
                await websocket.send_json(build_envelope("assistant.audio_chunk", session_id, chunk_payload))
                log_event("greeting.audio.sent", session_id=session_id, chunks=1, bytes=len(audio_bytes), duration_ms=duration_ms, source="elevenlabs")
            else:
                log_event("greeting.audio.error", session_id=session_id, reason="no_audio_data")
            
        except Exception as exc:
            log_event("greeting.audio.error", session_id=session_id, reason=str(exc))
            # Fallback to mock tone on error
            chunk_payload = {
                "response_id": response_id,
                "chunk_id": f"{response_id}_1",
                "codec": "pcm_s16le",
                "sample_rate": 16000,
                "channels": 1,
                "duration_ms": 500,
                "is_last": True,
                "bytes_b64": generate_pcm_s16le_tone_b64(sample_rate=16000, duration_ms=500),
            }
            try:
                await websocket.send_json(build_envelope("assistant.audio_chunk", session_id, chunk_payload))
            except RuntimeError:
                pass

    # Send playback stop control
    stop_payload = {"command": "stop_response", "response_id": response_id}
    try:
        await websocket.send_json(build_envelope("assistant.playback.control", session_id, stop_payload))
    except RuntimeError:
        pass
