from __future__ import annotations

from backend.infrastructure.storage.types import MemoryExportArtifact


def list_memory_export_artifacts(storage: object) -> list[MemoryExportArtifact]:
    artifacts: list[MemoryExportArtifact] = []
    artifacts.extend(
        storage._build_export_artifacts_for_paths(
            artifact_kind="user_memory_markdown",
            session_id=None,
            paths=(storage._CANONICAL_USER_MEMORY_RELATIVE_PATH,),
        )
    )
    artifacts.extend(
        storage._build_export_artifacts_for_paths(
            artifact_kind="cross_session_memory_markdown",
            session_id=None,
            paths=(storage._CANONICAL_CROSS_SESSION_MEMORY_RELATIVE_PATH,),
        )
    )

    for row in storage.metadata_store.list_session_rows_for_retention():
        session_id = str(row.get("session_id") or "").strip()
        if not session_id:
            continue
        session_storage = storage.get_session_storage_paths(session_id=session_id)
        artifacts.extend(
            storage._build_export_artifacts_for_paths(
                artifact_kind="short_term_memory_markdown",
                session_id=session_id,
                paths=(storage._relative_path(session_storage.short_term_memory_markdown_path),),
            )
        )
        artifacts.extend(
            storage._build_export_artifacts_for_paths(
                artifact_kind="session_memory_markdown",
                session_id=session_id,
                paths=(storage._relative_path(session_storage.session_memory_markdown_path),),
            )
        )
        artifacts.extend(
            storage._build_export_artifacts_for_paths(
                artifact_kind="vision_event_log",
                session_id=session_id,
                paths=(storage._relative_path(session_storage.vision_events_log_path),),
            )
        )
        artifacts.extend(
            storage._build_export_artifacts_for_paths(
                artifact_kind="vision_routing_event_log",
                session_id=session_id,
                paths=(storage._relative_path(session_storage.vision_routing_events_log_path),),
            )
        )
    return artifacts
