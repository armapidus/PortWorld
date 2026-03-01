from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import HTTPException

from backend.config.settings import SETTINGS
from backend.core.debug import sanitize_debug_value, sanitize_headers_for_debug, truncate_debug_text
from backend.core.profile import RuntimeProfile
from backend.core.utils import auth_headers, extract_choice_text, join_url
from backend.tracing.manager import TraceManager


async def transcribe_audio(
    *,
    profile: RuntimeProfile,
    tracer: TraceManager,
    audio: bytes,
    content_type: str,
    filename: str | None,
    debug_capture: dict[str, Any] | None = None,
) -> str:
    provider = profile.voxtral
    url = join_url(provider.base_url, provider.path)

    data: dict[str, str] = {"model": provider.model}
    language = str(profile.options.get("voxtral_language") or SETTINGS.default_voxtral_language).strip()
    if language:
        data["language"] = language

    files = {
        "file": (
            filename or "audio.wav",
            audio,
            content_type,
        )
    }
    headers = auth_headers(provider.api_key, base_url=provider.base_url)
    timeout = httpx.Timeout(SETTINGS.request_timeout_s)

    if debug_capture is not None:
        debug_capture["request"] = {
            "url": url,
            "headers": sanitize_headers_for_debug(headers),
            "form": sanitize_debug_value(data),
            "file": {
                "filename": filename or "audio.wav",
                "content_type": content_type,
                "bytes": len(audio),
            },
        }

    await tracer.event("voxtral.request", data={"url": url, "model": provider.model, "audio_bytes": len(audio)})

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, data=data, files=files, headers=headers)
    except httpx.HTTPError as exc:
        if debug_capture is not None:
            debug_capture["error"] = str(exc)
        await tracer.event("voxtral.error", status="error", data={"message": str(exc)})
        raise HTTPException(status_code=502, detail=f"Voxtral request failed: {exc}") from exc

    if resp.status_code >= 400:
        if debug_capture is not None:
            debug_capture["response"] = {
                "status_code": resp.status_code,
                "text_preview": truncate_debug_text(resp.text, max_chars=600),
            }
        await tracer.event(
            "voxtral.upstream_error",
            status="error",
            data={"status_code": resp.status_code, "text": truncate_debug_text(resp.text, max_chars=600)},
        )
        raise HTTPException(
            status_code=502,
            detail=f"Voxtral upstream error {resp.status_code}: {resp.text[:400]}",
        )

    try:
        payload = resp.json()
    except json.JSONDecodeError as exc:
        await tracer.event("voxtral.invalid_json", status="error")
        raise HTTPException(status_code=502, detail="Voxtral response was not JSON.") from exc

    if debug_capture is not None:
        debug_capture["response"] = {
            "status_code": resp.status_code,
            "json": sanitize_debug_value(payload),
        }

    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        transcript = text.strip()
        if debug_capture is not None:
            debug_capture["transcript"] = transcript
        await tracer.event("voxtral.response", data={"transcript_chars": len(transcript)})
        return transcript

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            text2 = extract_choice_text(first)
            if text2:
                if debug_capture is not None:
                    debug_capture["transcript"] = text2
                await tracer.event("voxtral.response", data={"transcript_chars": len(text2)})
                return text2

    await tracer.event("voxtral.empty_text", status="error")
    raise HTTPException(status_code=502, detail="Voxtral response did not contain text.")
