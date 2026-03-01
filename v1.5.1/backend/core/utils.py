from __future__ import annotations

import base64
import json
import mimetypes
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, UploadFile
from starlette.routing import Mount


def join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def auth_headers(api_key: str, *, base_url: str = "") -> dict[str, str]:
    token = (api_key or "").strip()
    if not token or token.upper() == "EMPTY":
        return {}
    if token.startswith("${") and token.endswith("}"):
        return {}
    if "bedrock-mantle." in base_url:
        return {"Authorization": f"Bearer {token}"}
    return {"Authorization": f"Bearer {token}"}


def guess_content_type(filename: str | None, current: str | None) -> str:
    if current:
        return current
    guessed, _ = mimetypes.guess_type(filename or "")
    return guessed or "application/octet-stream"


async def read_upload_bytes(upload: UploadFile, *, max_bytes: int, label: str) -> tuple[bytes, str]:
    data = await upload.read(max_bytes + 1)
    if not data:
        raise HTTPException(status_code=400, detail=f"{label} upload is empty.")
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"{label} upload too large ({len(data)} bytes). Limit: {max_bytes} bytes.")
    return data, guess_content_type(upload.filename, upload.content_type)


def to_data_url(raw: bytes, content_type: str) -> str:
    return f"data:{content_type};base64,{base64.b64encode(raw).decode('ascii')}"


def extract_chat_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return " ".join(parts).strip()


def extract_choice_text(choice: dict[str, Any]) -> str:
    message = choice.get("message")
    if isinstance(message, dict):
        text = extract_chat_text(message.get("content"))
        if text:
            return text
    delta = choice.get("delta")
    if isinstance(delta, dict):
        text = extract_chat_text(delta.get("content"))
        if text:
            return text
    fallback = choice.get("text")
    if isinstance(fallback, str):
        return fallback.strip()
    return ""


def parse_history(raw: str) -> list[dict[str, Any]]:
    if not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"history_json must be valid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise HTTPException(status_code=400, detail="history_json must be a JSON array.")
    return [item for item in parsed if isinstance(item, dict)]


def parse_history_payload(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return parse_history(raw)
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    raise HTTPException(status_code=400, detail="history must be a JSON array or JSON string array.")


def parse_required_int64_field(payload: dict[str, Any], field_name: str) -> int:
    raw = payload.get(field_name)
    if isinstance(raw, bool):
        raise HTTPException(status_code=400, detail=f"{field_name} must be an int64.")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return int(raw.strip())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{field_name} must be an int64.") from exc
    raise HTTPException(status_code=400, detail=f"metadata missing required field: {field_name}.")


def parse_optional_int64_field(payload: dict[str, Any], field_name: str) -> int | None:
    raw = payload.get(field_name)
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise HTTPException(status_code=400, detail=f"{field_name} must be an int64.")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return int(raw.strip())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{field_name} must be an int64.") from exc
    raise HTTPException(status_code=400, detail=f"{field_name} must be an int64.")


def validate_query_contract_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("session_id") or "").strip()
    query_id = str(payload.get("query_id") or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="metadata.session_id is required.")
    if not query_id:
        raise HTTPException(status_code=400, detail="metadata.query_id is required.")

    wake_ts_ms = parse_required_int64_field(payload, "wake_ts_ms")
    query_start_ts_ms = parse_required_int64_field(payload, "query_start_ts_ms")
    query_end_ts_ms = parse_required_int64_field(payload, "query_end_ts_ms")
    video_start_ts_ms = parse_required_int64_field(payload, "video_start_ts_ms")
    video_end_ts_ms = parse_required_int64_field(payload, "video_end_ts_ms")

    if query_start_ts_ms < wake_ts_ms:
        raise HTTPException(status_code=400, detail="query_start_ts_ms must be >= wake_ts_ms.")
    if query_end_ts_ms < query_start_ts_ms:
        raise HTTPException(status_code=400, detail="query_end_ts_ms must be >= query_start_ts_ms.")
    expected_video_start = wake_ts_ms - 5000
    if video_start_ts_ms != expected_video_start:
        raise HTTPException(status_code=400, detail=f"video_start_ts_ms must equal wake_ts_ms - 5000 (expected {expected_video_start}).")
    if video_end_ts_ms != query_end_ts_ms:
        raise HTTPException(status_code=400, detail="video_end_ts_ms must equal query_end_ts_ms.")

    normalized = dict(payload)
    normalized.update(
        {
            "session_id": session_id,
            "query_id": query_id,
            "wake_ts_ms": wake_ts_ms,
            "query_start_ts_ms": query_start_ts_ms,
            "query_end_ts_ms": query_end_ts_ms,
            "video_start_ts_ms": video_start_ts_ms,
            "video_end_ts_ms": video_end_ts_ms,
        }
    )
    return normalized


def is_wav_upload(content_type: str, filename: str | None) -> bool:
    mime = (content_type or "").lower()
    name = (filename or "").lower()
    return "wav" in mime or name.endswith(".wav") or name.endswith(".wave")


def is_mp4_upload(content_type: str, filename: str | None) -> bool:
    mime = (content_type or "").lower()
    name = (filename or "").lower()
    return "mp4" in mime or name.endswith(".mp4")


def build_main_llm_content(*, prompt: str, audio_transcript: str | None, video_summary: str | None, image_data_urls: list[str]) -> str | list[dict[str, Any]]:
    sections: list[str] = []
    if prompt.strip():
        sections.append(prompt.strip())
    if audio_transcript and audio_transcript.strip():
        sections.append(f"Transcription audio (Voxtral):\n{audio_transcript.strip()}")
    if video_summary and video_summary.strip():
        sections.append(f"Analyse video (Nemotron):\n{video_summary.strip()}")
    if not sections:
        sections.append("Reponds en francais de facon concise et utile.")

    text_payload = "\n\n".join(sections)
    if not image_data_urls:
        return text_payload

    content: list[dict[str, Any]] = [{"type": "text", "text": text_payload}]
    for image_url in image_data_urls:
        content.append({"type": "image_url", "image_url": {"url": image_url}})
    return content


def build_messages_for_main_llm(*, history: list[dict[str, Any]], user_prompt: str, audio_transcript: str | None, video_summary: str | None, image_data_urls: list[str], system_prompt: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history)
    messages.append(
        {
            "role": "user",
            "content": build_main_llm_content(
                prompt=user_prompt,
                audio_transcript=audio_transcript,
                video_summary=video_summary,
                image_data_urls=image_data_urls,
            ),
        }
    )
    return messages


def extract_json_from_text(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(raw[start : end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def split_complete_sentences(buffer: str) -> tuple[list[str], str]:
    pattern = re.compile(r"[.!?]\s+|\n+")
    complete: list[str] = []
    start = 0
    for match in pattern.finditer(buffer):
        end = match.end()
        sentence = buffer[start:end].strip()
        if sentence:
            complete.append(sentence)
        start = end
    return complete, buffer[start:]


def utc_now_ts_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def media_type_from_output_format(output_format: str) -> str:
    fmt = (output_format or "").lower()
    if fmt.startswith("mp3"):
        return "audio/mpeg"
    if fmt.startswith("pcm"):
        return "audio/wav"
    if fmt.startswith("ulaw"):
        return "audio/basic"
    return "application/octet-stream"


def _join_paths(prefix: str, path: str) -> str:
    prefix = prefix[:-1] if prefix.endswith("/") else prefix
    path = path if path.startswith("/") else f"/{path}"
    return f"{prefix}{path}" or "/"


def list_routes_recursive(app: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    def collect(current_app: Any, prefix: str = "") -> None:
        for route in getattr(current_app, "routes", []):
            if isinstance(route, Mount):
                mounted = getattr(route, "app", None)
                if mounted is not None:
                    collect(mounted, _join_paths(prefix, route.path))
                continue

            path = getattr(route, "path", None)
            if not isinstance(path, str) or not path:
                continue

            methods = getattr(route, "methods", None)
            normalized_methods: list[str] = []
            if isinstance(methods, set):
                normalized_methods = sorted(method for method in methods if method != "HEAD")

            entries.append(
                {
                    "name": str(getattr(route, "name", "") or ""),
                    "path": _join_paths(prefix, path),
                    "methods": normalized_methods,
                    "route_type": "websocket" if "websocket" in route.__class__.__name__.lower() else "http",
                }
            )

    collect(app)
    entries.sort(key=lambda item: (item["path"], ",".join(item["methods"]), item["name"]))
    return entries
