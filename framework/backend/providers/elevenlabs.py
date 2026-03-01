from __future__ import annotations

import asyncio
import base64
import binascii
import json
from typing import Any, AsyncIterator
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from backend.config.settings import SETTINGS
from backend.core.debug import (
    DEBUG_AUDIO_CHUNK_PREVIEW_B64_CHARS,
    DEBUG_MAX_CAPTURED_AUDIO_CHUNKS,
    sanitize_debug_value,
    sanitize_headers_for_debug,
    truncate_debug_text,
)
from backend.core.profile import RuntimeProfile
from backend.tracing.manager import TraceManager


def media_type_from_output_format(output_format: str) -> str:
    fmt = (output_format or "").lower()
    if fmt.startswith("mp3"):
        return "audio/mpeg"
    if fmt.startswith("pcm"):
        return "audio/wav"
    if fmt.startswith("ulaw"):
        return "audio/basic"
    return "application/octet-stream"


def _resolve_elevenlabs_options(
    *,
    profile: RuntimeProfile,
    voice_id: str | None,
    model_id: str | None,
    speed: float | None,
    output_format: str | None,
) -> tuple[str, str, str, str, float]:
    api_key = (profile.elevenlabs.api_key or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=500, detail="ELEVENLABS_API_KEY is not configured."
        )

    default_voice = str(
        profile.options.get("elevenlabs_voice_id")
        or SETTINGS.default_elevenlabs_voice_id
    )
    default_format = str(
        profile.options.get("elevenlabs_output_format")
        or SETTINGS.default_elevenlabs_output_format
    )
    default_speed = float(
        profile.options.get("elevenlabs_speed") or SETTINGS.default_elevenlabs_speed
    )

    used_voice_id = (voice_id or default_voice).strip()
    used_model_id = (model_id or profile.elevenlabs.model).strip()
    used_output_format = (output_format or default_format).strip()
    used_speed = speed if speed is not None else default_speed

    if not used_voice_id:
        raise HTTPException(
            status_code=400, detail="ElevenLabs voice_id cannot be empty."
        )
    if not used_model_id:
        raise HTTPException(
            status_code=400, detail="ElevenLabs model_id cannot be empty."
        )
    if not used_output_format:
        raise HTTPException(
            status_code=400, detail="ElevenLabs output_format cannot be empty."
        )

    return api_key, used_voice_id, used_model_id, used_output_format, float(used_speed)


def _chunk_tts_buffer(buffer: str, *, target_chars: int = 80) -> tuple[list[str], str]:
    if target_chars < 20:
        target_chars = 20

    chunks: list[str] = []
    working = buffer
    while len(working) >= target_chars:
        pivot = working.rfind(" ", 0, target_chars)
        if pivot < 20:
            pivot = target_chars
        piece = working[:pivot].strip()
        working = working[pivot:].lstrip()
        if piece:
            chunks.append(piece)
    return chunks, working


async def prepare_elevenlabs_stream(
    *,
    profile: RuntimeProfile,
    tracer: TraceManager,
    text: str,
    voice_id: str | None,
    model_id: str | None,
    speed: float | None,
    output_format: str | None,
    debug_capture: dict[str, Any] | None = None,
) -> tuple[httpx.AsyncClient, httpx.Response, str]:
    api_key, used_voice_id, used_model_id, used_output_format, used_speed = (
        _resolve_elevenlabs_options(
            profile=profile,
            voice_id=voice_id,
            model_id=model_id,
            speed=speed,
            output_format=output_format,
        )
    )

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{used_voice_id}/stream"
    params = {"output_format": used_output_format}
    payload = {
        "text": text,
        "model_id": used_model_id,
        "voice_settings": {"speed": used_speed},
    }
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    if debug_capture is not None:
        debug_capture["request"] = {
            "url": url,
            "headers": sanitize_headers_for_debug(headers),
            "params": sanitize_debug_value(params),
            "json": sanitize_debug_value(payload),
        }

    await tracer.event(
        "elevenlabs.request",
        data={
            "url": url,
            "model": used_model_id,
            "voice_id": used_voice_id,
            "output_format": used_output_format,
        },
    )

    client = httpx.AsyncClient(timeout=None)
    request = client.build_request(
        method="POST",
        url=url,
        params=params,
        json=payload,
        headers=headers,
    )
    try:
        response = await client.send(request, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        if debug_capture is not None:
            debug_capture["error"] = str(exc)
        await tracer.event(
            "elevenlabs.error", status="error", data={"message": str(exc)}
        )
        raise HTTPException(
            status_code=502, detail=f"ElevenLabs request failed: {exc}"
        ) from exc

    if response.status_code >= 400:
        body = (await response.aread())[:400].decode("utf-8", errors="replace")
        if debug_capture is not None:
            debug_capture["response"] = {
                "status_code": response.status_code,
                "text_preview": truncate_debug_text(body, max_chars=600),
            }
        await tracer.event(
            "elevenlabs.upstream_error",
            status="error",
            data={
                "status_code": response.status_code,
                "text": truncate_debug_text(body, max_chars=600),
            },
        )
        await response.aclose()
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail=f"ElevenLabs upstream error {response.status_code}: {body}",
        )

    if debug_capture is not None:
        debug_capture["response"] = {"status_code": response.status_code}
        debug_capture["output_format"] = used_output_format

    return client, response, used_output_format


async def prepare_elevenlabs_live_stream(
    *,
    profile: RuntimeProfile,
    tracer: TraceManager,
    text_iterator: AsyncIterator[str],
    voice_id: str | None,
    model_id: str | None,
    speed: float | None,
    output_format: str | None,
    debug_capture: dict[str, Any] | None = None,
) -> tuple[AsyncIterator[bytes], str]:
    api_key, used_voice_id, used_model_id, used_output_format, used_speed = (
        _resolve_elevenlabs_options(
            profile=profile,
            voice_id=voice_id,
            model_id=model_id,
            speed=speed,
            output_format=output_format,
        )
    )

    query = urlencode(
        {
            "model_id": used_model_id,
            "output_format": used_output_format,
        }
    )
    ws_url = f"wss://api.elevenlabs.io/v1/text-to-speech/{used_voice_id}/stream-input?{query}"
    headers = {
        "xi-api-key": api_key,
    }

    if debug_capture is not None:
        debug_capture["request"] = {
            "url": ws_url,
            "headers": sanitize_headers_for_debug(headers),
            "voice_settings": {"speed": used_speed},
        }

    await tracer.event(
        "elevenlabs.live.request",
        data={
            "url": ws_url,
            "model": used_model_id,
            "voice_id": used_voice_id,
            "output_format": used_output_format,
        },
    )

    async def audio_chunks() -> AsyncIterator[bytes]:
        try:
            import websockets
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail="websockets package is required for live TTS streaming.",
            ) from exc

        queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=48)
        sender_error: Exception | None = None
        receiver_error: Exception | None = None
        audio_chunks_sent = 0
        audio_bytes_sent = 0
        tokens_sent = 0

        async with websockets.connect(
            ws_url,
            additional_headers=headers,
            max_size=None,
            open_timeout=20,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=10,
        ) as ws:
            init_payload = {
                "text": " ",
                "xi_api_key": api_key,
                "voice_settings": {"speed": used_speed},
                "generation_config": {"chunk_length_schedule": [50, 120, 160, 250]},
            }
            await ws.send(json.dumps(init_payload))
            await tracer.event("elevenlabs.live.open", data={"voice_id": used_voice_id})

            async def send_loop() -> None:
                nonlocal sender_error, tokens_sent
                buffer = ""
                try:
                    async for token in text_iterator:
                        if not token:
                            continue
                        tokens_sent += 1
                        buffer += token
                        ready, buffer = _chunk_tts_buffer(buffer, target_chars=40)
                        for piece in ready:
                            await ws.send(
                                json.dumps(
                                    {
                                        "text": piece + " ",
                                        "try_trigger_generation": True,
                                    }
                                )
                            )
                    trailing = buffer.strip()
                    if trailing:
                        await ws.send(
                            json.dumps(
                                {"text": trailing + " ", "try_trigger_generation": True}
                            )
                        )
                    await ws.send(json.dumps({"text": ""}))
                except websockets.exceptions.ConnectionClosedOK:
                    return
                except Exception as exc:
                    sender_error = exc
                    try:
                        await ws.close()
                    except Exception:
                        pass

            async def receive_loop() -> None:
                nonlocal receiver_error, audio_chunks_sent, audio_bytes_sent
                try:
                    while True:
                        message = await ws.recv()
                        if isinstance(message, bytes):
                            if message:
                                audio_chunks_sent += 1
                                audio_bytes_sent += len(message)
                                await queue.put(message)
                            continue

                        payload: dict[str, Any]
                        try:
                            payload = json.loads(message)
                        except json.JSONDecodeError:
                            continue

                        maybe_audio = payload.get("audio")
                        if isinstance(maybe_audio, str) and maybe_audio:
                            try:
                                decoded = base64.b64decode(maybe_audio)
                            except (binascii.Error, ValueError):
                                decoded = b""
                            if decoded:
                                audio_chunks_sent += 1
                                audio_bytes_sent += len(decoded)
                                await queue.put(decoded)

                        is_final = payload.get("isFinal")
                        if isinstance(is_final, bool) and is_final:
                            break
                except websockets.exceptions.ConnectionClosedOK:
                    return
                except Exception as exc:
                    receiver_error = exc
                finally:
                    await queue.put(None)

            sender_task = asyncio.create_task(send_loop())
            receiver_task = asyncio.create_task(receive_loop())
            try:
                while True:
                    item = await queue.get()
                    if item is None:
                        break
                    yield item
            finally:
                if not sender_task.done():
                    sender_task.cancel()
                if not receiver_task.done():
                    receiver_task.cancel()
                await asyncio.gather(sender_task, receiver_task, return_exceptions=True)

        if debug_capture is not None:
            debug_capture["response"] = {
                "tokens_forwarded": tokens_sent,
                "audio_chunks": audio_chunks_sent,
                "audio_bytes": audio_bytes_sent,
                "output_format": used_output_format,
            }
            if sender_error is not None:
                debug_capture["sender_error"] = str(sender_error)
            if receiver_error is not None:
                debug_capture["receiver_error"] = str(receiver_error)

        if sender_error is not None:
            await tracer.event(
                "elevenlabs.live.sender_error",
                status="error",
                data={"message": str(sender_error)},
            )
            raise HTTPException(
                status_code=502, detail=f"Live relay sender failed: {sender_error}"
            ) from sender_error

        if receiver_error is not None:
            await tracer.event(
                "elevenlabs.live.receiver_error",
                status="error",
                data={"message": str(receiver_error)},
            )
            raise HTTPException(
                status_code=502, detail=f"Live relay receiver failed: {receiver_error}"
            ) from receiver_error

        await tracer.event(
            "elevenlabs.live.done",
            data={
                "tokens_forwarded": tokens_sent,
                "audio_chunks": audio_chunks_sent,
                "audio_bytes": audio_bytes_sent,
            },
        )

    return audio_chunks(), used_output_format


async def capture_elevenlabs_stream_debug(
    *,
    response: httpx.Response,
    include_audio_base64: bool = False,
    max_audio_bytes: int = 8_000_000,
    max_chunks: int = DEBUG_MAX_CAPTURED_AUDIO_CHUNKS,
    preview_b64_chars: int = DEBUG_AUDIO_CHUNK_PREVIEW_B64_CHARS,
) -> tuple[list[dict[str, Any]], int, int, str | None]:
    captured_chunks: list[dict[str, Any]] = []
    total_chunks = 0
    total_bytes = 0
    audio_parts: list[bytes] = []

    async for chunk in response.aiter_bytes():
        if not chunk:
            continue
        total_chunks += 1
        chunk_size = len(chunk)
        total_bytes += chunk_size

        if include_audio_base64 and total_bytes <= max_audio_bytes:
            audio_parts.append(chunk)

        if len(captured_chunks) < max_chunks:
            captured_chunks.append(
                {
                    "chunk_index": total_chunks,
                    "bytes": chunk_size,
                    "audio_base64_preview": base64.b64encode(chunk).decode("ascii")[
                        :preview_b64_chars
                    ],
                }
            )

    full_audio_b64: str | None = None
    if include_audio_base64 and audio_parts and total_bytes <= max_audio_bytes:
        full_audio_b64 = base64.b64encode(b"".join(audio_parts)).decode("ascii")

    return captured_chunks, total_chunks, total_bytes, full_audio_b64
