from __future__ import annotations

from typing import Mapping

from backend.memory.profile import (
    build_profile_payload,
    build_profile_record,
    empty_profile_markdown,
    empty_profile_payload,
    parse_profile_markdown,
    parse_profile_record,
    render_profile_markdown,
)


def read_user_profile(storage: object) -> dict[str, object]:
    markdown_text = storage.read_user_profile_markdown()
    record = parse_profile_markdown(markdown_text)
    return build_profile_payload(record, include_metadata=False)


def read_user_profile_markdown(storage: object) -> str:
    markdown_text = storage.object_store.get_text(
        relative_path=storage._CANONICAL_USER_MEMORY_RELATIVE_PATH
    )
    if markdown_text is not None:
        return markdown_text
    legacy_markdown = storage.object_store.get_text(
        relative_path=storage._LEGACY_PROFILE_MARKDOWN_RELATIVE_PATH
    )
    if legacy_markdown is not None:
        storage.object_store.put_text(
            relative_path=storage._CANONICAL_USER_MEMORY_RELATIVE_PATH,
            content=legacy_markdown,
            content_type="text/markdown",
        )
        return legacy_markdown
    legacy_json_payload = storage._read_json_artifact(
        relative_path=storage._LEGACY_PROFILE_JSON_RELATIVE_PATH,
        context="managed legacy profile json artifact",
    )
    if legacy_json_payload is not None:
        rendered = render_profile_markdown(parse_profile_record(legacy_json_payload))
        storage.object_store.put_text(
            relative_path=storage._CANONICAL_USER_MEMORY_RELATIVE_PATH,
            content=rendered,
            content_type="text/markdown",
        )
        return rendered
    document = storage.metadata_store.read_profile_document()
    fallback = storage._coerce_text(document.get("markdown_text")) or empty_profile_markdown()
    storage.object_store.put_text(
        relative_path=storage._CANONICAL_USER_MEMORY_RELATIVE_PATH,
        content=fallback,
        content_type="text/markdown",
    )
    return fallback


def read_cross_session_memory(storage: object) -> str:
    cross_session_markdown = storage.object_store.get_text(
        relative_path=storage._CANONICAL_CROSS_SESSION_MEMORY_RELATIVE_PATH
    )
    if cross_session_markdown is not None:
        return cross_session_markdown
    storage.object_store.put_text(
        relative_path=storage._CANONICAL_CROSS_SESSION_MEMORY_RELATIVE_PATH,
        content=storage._CROSS_SESSION_MEMORY_TEMPLATE,
        content_type="text/markdown",
    )
    return storage._CROSS_SESSION_MEMORY_TEMPLATE


def write_user_profile(
    storage: object,
    *,
    payload: Mapping[str, object],
    source: str | None = None,
    updated_at_ms: int | None = None,
) -> dict[str, object]:
    timestamp_ms = updated_at_ms if updated_at_ms is not None else storage.now_ms()
    record = build_profile_record(
        payload,
        updated_at_ms=timestamp_ms,
        source=source,
    )
    normalized_payload = build_profile_payload(record)
    if not normalized_payload:
        return storage.reset_user_profile()

    markdown_text = render_profile_markdown(parse_profile_record(normalized_payload))
    storage.object_store.put_text(
        relative_path=storage._CANONICAL_USER_MEMORY_RELATIVE_PATH,
        content=markdown_text,
        content_type="text/markdown",
    )
    return normalized_payload


def reset_user_profile(storage: object) -> dict[str, object]:
    markdown_text = empty_profile_markdown()
    storage.object_store.put_text(
        relative_path=storage._CANONICAL_USER_MEMORY_RELATIVE_PATH,
        content=markdown_text,
        content_type="text/markdown",
    )
    return empty_profile_payload()


def write_cross_session_memory(storage: object, *, markdown: str) -> None:
    storage.object_store.put_text(
        relative_path=storage._CANONICAL_CROSS_SESSION_MEMORY_RELATIVE_PATH,
        content=markdown,
        content_type="text/markdown",
    )


def ensure_profile_artifacts(storage: object) -> None:
    storage.read_user_profile_markdown()
    storage.read_cross_session_memory()
