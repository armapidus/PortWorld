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


async def summarize_video(
    *,
    profile: RuntimeProfile,
    tracer: TraceManager,
    video_data_url: str,
    prompt_hint: str,
    debug_capture: dict[str, Any] | None = None,
) -> str:
    provider = profile.nemotron
    url = join_url(provider.base_url, provider.path)
    headers = {
        **auth_headers(provider.api_key, base_url=provider.base_url),
        "Content-Type": "application/json",
    }

    default_prompt = str(profile.prompts.get("nemotron_video_prompt") or SETTINGS.default_nemotron_prompt)
    prompt = prompt_hint.strip() or default_prompt

    payload: dict[str, Any] = {
        "model": provider.model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "video_url", "video_url": {"url": video_data_url}},
                ],
            }
        ],
        "temperature": profile.temperatures["nemotron"],
        "max_tokens": profile.max_tokens["nemotron"],
        "stream": False,
    }

    if debug_capture is not None:
        debug_capture["request"] = {
            "url": url,
            "headers": sanitize_headers_for_debug(headers),
            "json": sanitize_debug_value(payload),
        }

    await tracer.event("nemotron.request", data={"url": url, "model": provider.model})

    timeout = httpx.Timeout(SETTINGS.request_timeout_s)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        if debug_capture is not None:
            debug_capture["error"] = str(exc)
        await tracer.event("nemotron.error", status="error", data={"message": str(exc)})
        raise HTTPException(status_code=502, detail=f"Nemotron request failed: {exc}") from exc

    if resp.status_code >= 400:
        if debug_capture is not None:
            debug_capture["response"] = {
                "status_code": resp.status_code,
                "text_preview": truncate_debug_text(resp.text, max_chars=700),
            }
        await tracer.event(
            "nemotron.upstream_error",
            status="error",
            data={"status_code": resp.status_code, "text": truncate_debug_text(resp.text, max_chars=700)},
        )
        raise HTTPException(
            status_code=502,
            detail=f"Nemotron upstream error {resp.status_code}: {resp.text[:500]}",
        )

    try:
        response_payload = resp.json()
    except json.JSONDecodeError as exc:
        await tracer.event("nemotron.invalid_json", status="error")
        raise HTTPException(status_code=502, detail="Nemotron response was not JSON.") from exc

    if debug_capture is not None:
        debug_capture["response"] = {
            "status_code": resp.status_code,
            "json": sanitize_debug_value(response_payload),
        }

    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        await tracer.event("nemotron.missing_choices", status="error")
        raise HTTPException(status_code=502, detail="Nemotron response missing choices.")
    first = choices[0]
    if not isinstance(first, dict):
        await tracer.event("nemotron.bad_choice_format", status="error")
        raise HTTPException(status_code=502, detail="Nemotron choice format invalid.")

    video_text = extract_choice_text(first)
    if not video_text:
        await tracer.event("nemotron.empty_text", status="error")
        raise HTTPException(status_code=502, detail="Nemotron response did not contain text.")

    if debug_capture is not None:
        debug_capture["video_summary"] = video_text

    await tracer.event("nemotron.response", data={"summary_chars": len(video_text)})
    return video_text
