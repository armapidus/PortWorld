from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.infrastructure.storage.types import SessionStorageResult


@dataclass(frozen=True, slots=True)
class SessionArtifactDescriptor:
    artifact_id: str
    artifact_kind: str
    artifact_path: Path
    content_type: str


def session_artifact_descriptors(
    *,
    session_id: str,
    session_storage: SessionStorageResult,
) -> tuple[SessionArtifactDescriptor, ...]:
    return (
        SessionArtifactDescriptor(
            artifact_id=f"{session_id}:short_term_memory_markdown",
            artifact_kind="short_term_memory_markdown",
            artifact_path=session_storage.short_term_memory_markdown_path,
            content_type="text/markdown",
        ),
        SessionArtifactDescriptor(
            artifact_id=f"{session_id}:session_memory_markdown",
            artifact_kind="session_memory_markdown",
            artifact_path=session_storage.session_memory_markdown_path,
            content_type="text/markdown",
        ),
        SessionArtifactDescriptor(
            artifact_id=f"{session_id}:vision_event_log",
            artifact_kind="vision_event_log",
            artifact_path=session_storage.vision_events_log_path,
            content_type="application/x-ndjson",
        ),
        SessionArtifactDescriptor(
            artifact_id=f"{session_id}:vision_routing_event_log",
            artifact_kind="vision_routing_event_log",
            artifact_path=session_storage.vision_routing_events_log_path,
            content_type="application/x-ndjson",
        ),
    )
