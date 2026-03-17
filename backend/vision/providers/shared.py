from __future__ import annotations

import base64
import datetime as dt
import email.utils
import json
from typing import Any, Mapping

import httpx

from backend.vision.contracts import (
    ProviderObservationPayload,
    VisionFrameContext,
    VisionObservation,
    VisionProviderError,
    VisionRateLimitError,
)

DEFAULT_VISION_TEMPERATURE = 0.0
DEFAULT_VISION_TOP_P = 0.1
DEFAULT_VISION_MAX_TOKENS = 280

VISION_SYSTEM_PROMPT = (
    "You are a vision observation service for a realtime wearable assistant. "
    "Return exactly one compact JSON object with keys: "
    "scene_summary, user_activity_guess, entities, actions, visible_text, documents_seen, salient_change, confidence. "
    "Do not include markdown, code fences, or extra commentary. "
    "Keep scene_summary short and factual. "
    "Use arrays of short strings for entities, actions, visible_text, and documents_seen. "
    "Set salient_change to the JSON boolean true or false. "
    "Set confidence as a JSON number between 0.0 and 1.0."
)


def build_data_url(*, image_bytes: bytes, image_media_type: str) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{image_media_type};base64,{encoded}"


def build_base64_data(*, image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("ascii")


def build_user_prompt(*, frame_context: VisionFrameContext) -> str:
    dimensions = []
    if frame_context.width is not None:
        dimensions.append(f"width={frame_context.width}")
    if frame_context.height is not None:
        dimensions.append(f"height={frame_context.height}")
    dimension_text = ", ".join(dimensions) if dimensions else "unknown dimensions"
    return (
        "Analyze this single still image for short-term wearable context. "
        f"Frame context: session_id={frame_context.session_id}, frame_id={frame_context.frame_id}, "
        f"capture_ts_ms={frame_context.capture_ts_ms}, {dimension_text}. "
        "Focus on what the user appears to be doing, prominent entities, readable text, "
        "and whether this frame likely represents a salient change from nearby context."
    )


def normalize_observation(
    *,
    payload: ProviderObservationPayload,
    frame_context: VisionFrameContext,
) -> VisionObservation:
    return VisionObservation.model_validate(
        {
            "frame_id": frame_context.frame_id,
            "session_id": frame_context.session_id,
            "capture_ts_ms": frame_context.capture_ts_ms,
            **payload.model_dump(),
        }
    )


def coalesce_text_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        raise ValueError("Provider response content had an unsupported shape")

    text_parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            text_parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        item_type = (item.get("type") or "").strip().lower()
        if item_type in {"text", "output_text"}:
            text_value = item.get("text")
            if isinstance(text_value, str):
                text_parts.append(text_value)
                continue
        if item_type == "text_delta":
            text_value = item.get("delta")
            if isinstance(text_value, str):
                text_parts.append(text_value)
                continue
    if not text_parts:
        raise ValueError("Provider response content list did not contain text")
    return "\n".join(text_parts)


def extract_provider_content_excerpt_from_chat_choices(response_json: Mapping[str, Any]) -> str | None:
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        return str(response_json)[:400]

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return str(first_choice)[:400]

    message = first_choice.get("message")
    if not isinstance(message, dict):
        return str(first_choice)[:400]

    content = message.get("content")
    if content is None:
        return None
    return str(content)[:400]


def parse_retry_after_seconds(response: httpx.Response) -> float | None:
    retry_after_raw = response.headers.get("Retry-After")
    if not retry_after_raw:
        return None
    candidate = retry_after_raw.strip()
    if not candidate:
        return None
    try:
        value = float(candidate)
        return value if value > 0 else None
    except ValueError:
        pass
    try:
        parsed_dt = email.utils.parsedate_to_datetime(candidate)
    except (TypeError, ValueError):
        return None
    if parsed_dt is None:
        return None
    if parsed_dt.tzinfo is None:
        parsed_dt = parsed_dt.replace(tzinfo=dt.timezone.utc)
    now = dt.datetime.now(tz=dt.timezone.utc)
    delta_seconds = (parsed_dt - now).total_seconds()
    return delta_seconds if delta_seconds > 0 else None


def extract_http_error_details(response: httpx.Response) -> dict[str, str | None]:
    payload_excerpt: str | None = None
    provider_error_code: str | None = None
    provider_message: str | None = None

    raw_text = response.text.strip()
    if raw_text:
        payload_excerpt = raw_text[:400]

    try:
        payload = response.json()
    except ValueError:
        return {
            "provider_error_code": provider_error_code,
            "provider_message": provider_message,
            "payload_excerpt": payload_excerpt,
        }

    if isinstance(payload, dict):
        error_payload = payload.get("error")
        if isinstance(error_payload, dict):
            error_code = error_payload.get("code")
            if isinstance(error_code, str) and error_code.strip():
                provider_error_code = error_code.strip()
            message = error_payload.get("message")
            if isinstance(message, str) and message.strip():
                provider_message = message.strip()
        elif isinstance(error_payload, str) and error_payload.strip():
            provider_message = error_payload.strip()
        elif payload_excerpt is None:
            payload_excerpt = str(payload)[:400]

    return {
        "provider_error_code": provider_error_code,
        "provider_message": provider_message,
        "payload_excerpt": payload_excerpt,
    }


async def post_json_with_vision_errors(
    *,
    client: httpx.AsyncClient,
    url: str,
    request_body: Mapping[str, Any],
) -> httpx.Response:
    try:
        response = await client.post(url, json=request_body)
    except httpx.ReadTimeout as exc:
        raise VisionProviderError(
            provider_error_code="provider_read_timeout",
            provider_message="Vision provider request timed out while waiting for a response",
        ) from exc
    except httpx.RequestError as exc:
        raise VisionProviderError(
            provider_error_code="provider_transport_error",
            provider_message=f"{type(exc).__name__}: {exc}",
        ) from exc

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        error_details = extract_http_error_details(exc.response)
        if exc.response.status_code == 429:
            raise VisionRateLimitError(
                retry_after_seconds=parse_retry_after_seconds(exc.response),
                status_code=429,
                provider_error_code=error_details["provider_error_code"],
                provider_message=error_details["provider_message"],
                payload_excerpt=error_details["payload_excerpt"],
            ) from exc
        raise VisionProviderError(
            status_code=exc.response.status_code,
            provider_error_code=error_details["provider_error_code"],
            provider_message=error_details["provider_message"],
            payload_excerpt=error_details["payload_excerpt"],
        ) from exc
    return response


def is_response_format_compatibility_error(error: VisionProviderError) -> bool:
    if error.status_code != 400:
        return False
    code = (error.provider_error_code or "").strip().lower()
    message = (error.provider_message or "").strip().lower()
    if "response_format" in message:
        if not code:
            return True
        return "unknown_parameter" in code or "invalid_parameter" in code

    structured_output_markers = (
        "structured output backend",
        "structured outputs",
        "guidance",
        "xgrammar",
        "outlines",
        "tokenizer_mode='hf'",
        'tokenizer_mode="hf"',
        "mistral tokenizer is not supported",
    )
    return any(marker in message for marker in structured_output_markers)


def provider_error_from_exception(
    *,
    message: str,
    error_code: str,
    payload_excerpt: str | None = None,
) -> VisionProviderError:
    return VisionProviderError(
        provider_error_code=error_code,
        provider_message=message,
        payload_excerpt=payload_excerpt,
    )


def safe_json_excerpt(payload: object) -> str | None:
    try:
        return json.dumps(payload)[:400]
    except Exception:
        return str(payload)[:400]
