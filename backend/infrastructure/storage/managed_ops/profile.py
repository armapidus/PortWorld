from __future__ import annotations

from typing import Mapping

from backend.memory.user_memory import (
    build_user_memory_payload,
    build_user_memory_record,
    empty_user_memory_markdown,
    parse_user_memory_markdown,
    parse_user_memory_record,
    render_user_memory_markdown,
)


def read_user_memory_payload(storage: object) -> dict[str, object]:
    markdown_text = storage.read_user_memory_markdown()
    record = parse_user_memory_markdown(markdown_text)
    return build_user_memory_payload(record, include_metadata=False)


def read_user_memory_markdown(storage: object) -> str:
    return storage._read_or_initialize_markdown_artifact(
        relative_path=storage._CANONICAL_USER_MEMORY_RELATIVE_PATH,
        default_text=empty_user_memory_markdown(),
    )


def read_cross_session_memory(storage: object) -> str:
    return storage._read_or_initialize_markdown_artifact(
        relative_path=storage._CANONICAL_CROSS_SESSION_MEMORY_RELATIVE_PATH,
        default_text=storage._CROSS_SESSION_MEMORY_TEMPLATE,
    )


def write_user_memory_payload(
    storage: object,
    *,
    payload: Mapping[str, object],
    source: str | None = None,
    updated_at_ms: int | None = None,
) -> dict[str, object]:
    timestamp_ms = updated_at_ms if updated_at_ms is not None else storage.now_ms()
    record = build_user_memory_record(
        payload,
        updated_at_ms=timestamp_ms,
        source=source,
    )
    normalized_payload = build_user_memory_payload(record)
    if not normalized_payload:
        return storage.reset_user_memory_payload()

    markdown_text = render_user_memory_markdown(parse_user_memory_record(normalized_payload))
    storage.object_store.put_text(
        relative_path=storage._CANONICAL_USER_MEMORY_RELATIVE_PATH,
        content=markdown_text,
        content_type="text/markdown",
    )
    return normalized_payload


def reset_user_memory_payload(storage: object) -> dict[str, object]:
    markdown_text = empty_user_memory_markdown()
    storage.object_store.put_text(
        relative_path=storage._CANONICAL_USER_MEMORY_RELATIVE_PATH,
        content=markdown_text,
        content_type="text/markdown",
    )
    return {}


def write_user_memory(storage: object, *, markdown: str) -> None:
    storage.object_store.put_text(
        relative_path=storage._CANONICAL_USER_MEMORY_RELATIVE_PATH,
        content=markdown,
        content_type="text/markdown",
    )


def write_cross_session_memory(storage: object, *, markdown: str) -> None:
    storage.object_store.put_text(
        relative_path=storage._CANONICAL_CROSS_SESSION_MEMORY_RELATIVE_PATH,
        content=markdown,
        content_type="text/markdown",
    )


def ensure_user_memory_artifacts(storage: object) -> None:
    storage.read_user_memory_markdown()
    storage.read_cross_session_memory()
