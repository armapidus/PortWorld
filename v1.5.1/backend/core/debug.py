from __future__ import annotations

from typing import Any

DEBUG_TEXT_MAX_CHARS = 1800
DEBUG_MAX_LIST_ITEMS = 30
DEBUG_MAX_DICT_ITEMS = 40
DEBUG_MAX_CAPTURED_TOKENS = 600
DEBUG_MAX_CAPTURED_AUDIO_CHUNKS = 120
DEBUG_AUDIO_CHUNK_PREVIEW_B64_CHARS = 120


def truncate_debug_text(value: str, *, max_chars: int = DEBUG_TEXT_MAX_CHARS) -> str:
    if len(value) <= max_chars:
        return value
    omitted = len(value) - max_chars
    return f"{value[:max_chars]}...<truncated {omitted} chars>"


def summarize_data_url(data_url: str) -> dict[str, Any]:
    header, _, body = data_url.partition(",")
    mime_type = "application/octet-stream"
    if header.startswith("data:"):
        mime_candidate = header[5:].split(";")[0].strip()
        if mime_candidate:
            mime_type = mime_candidate
    is_base64 = ";base64" in header.lower()
    approx_bytes = (len(body) * 3) // 4 if is_base64 else len(body)
    return {
        "kind": "data_url",
        "mime_type": mime_type,
        "is_base64": is_base64,
        "payload_chars": len(body),
        "approx_bytes": approx_bytes,
    }


def sanitize_headers_for_debug(headers: dict[str, str]) -> dict[str, str]:
    hidden = {
        "authorization",
        "x-api-key",
        "xi-api-key",
        "cf-access-client-id",
        "cf-access-client-secret",
    }
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in hidden:
            sanitized[key] = "<redacted>"
        else:
            sanitized[key] = truncate_debug_text(str(value), max_chars=120)
    return sanitized


def sanitize_debug_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "<max-depth-reached>"

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, bytes):
        return {"kind": "bytes", "size": len(value)}

    if isinstance(value, str):
        if value.startswith("data:") and "," in value:
            return summarize_data_url(value)
        return truncate_debug_text(value)

    if isinstance(value, list):
        items = value[:DEBUG_MAX_LIST_ITEMS]
        sanitized_items = [sanitize_debug_value(item, depth=depth + 1) for item in items]
        if len(value) > DEBUG_MAX_LIST_ITEMS:
            sanitized_items.append(f"<{len(value) - DEBUG_MAX_LIST_ITEMS} more items>")
        return sanitized_items

    if isinstance(value, tuple):
        return sanitize_debug_value(list(value), depth=depth + 1)

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        items = list(value.items())[:DEBUG_MAX_DICT_ITEMS]
        for key, raw in items:
            key_str = str(key)
            if key_str.lower() in {"authorization", "x-api-key", "xi-api-key"}:
                sanitized[key_str] = "<redacted>"
                continue
            sanitized[key_str] = sanitize_debug_value(raw, depth=depth + 1)
        if len(value) > DEBUG_MAX_DICT_ITEMS:
            sanitized["_truncated_keys"] = len(value) - DEBUG_MAX_DICT_ITEMS
        return sanitized

    return truncate_debug_text(str(value))
