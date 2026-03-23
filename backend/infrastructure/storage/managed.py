from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping

from backend.core.storage import BackendStorage
from backend.infrastructure.storage.common.memory_markdown import (
    parse_csv_list,
    parse_managed_memory_markdown_payload,
    read_section_text,
    split_semicolon_list,
)
from backend.infrastructure.storage.common.session_artifacts import session_artifact_descriptors
from backend.infrastructure.storage.common.storage_ids import storage_component_for_id
from backend.infrastructure.storage.common.vision_updates import (
    UNSET,
    resolve_error_details_json,
    resolve_next_retry_at_ms,
)
from backend.infrastructure.storage.errors import SessionNotFoundError
from backend.infrastructure.storage.managed_ops import profile as managed_profile_ops
from backend.infrastructure.storage.managed_ops import exports as managed_export_ops
from backend.infrastructure.storage.managed_ops import vision as managed_vision_ops
from backend.infrastructure.storage.object_store import ObjectStore, normalize_object_store_relative_path
from backend.infrastructure.storage.providers.metadata.postgres import PostgresMetadataStore
from backend.infrastructure.storage.types import (
    ArtifactRecord,
    MemoryExportArtifact,
    SessionMemoryResetResult,
    SessionStorageResult,
    StorageBootstrapResult,
    StorageInfo,
    VisionFrameIndexRecord,
    VisionFrameIngestResult,
    now_ms,
)
from backend.memory.events import AcceptedVisionEvent, coerce_accepted_vision_event
from backend.memory.lifecycle import (
    CROSS_SESSION_MEMORY_FILE_NAME,
    CROSS_SESSION_MEMORY_TEMPLATE,
    PROFILE_ARTIFACT_FILE_NAMES,
    SESSION_MEMORY_TEMPLATE,
    SESSION_MEMORY_MARKDOWN_FILE_NAME,
    SHORT_TERM_MEMORY_TEMPLATE,
    SHORT_TERM_MEMORY_MARKDOWN_FILE_NAME,
    USER_MEMORY_FILE_NAME,
    VISION_EVENTS_LOG_FILE_NAME,
    VISION_ROUTING_EVENTS_LOG_FILE_NAME,
    SessionMemoryResetEligibility,
    SessionMemoryRetentionEligibility,
)
logger = logging.getLogger(__name__)

_CANONICAL_USER_MEMORY_RELATIVE_PATH = f"memory/{USER_MEMORY_FILE_NAME}"
_CANONICAL_CROSS_SESSION_MEMORY_RELATIVE_PATH = f"memory/{CROSS_SESSION_MEMORY_FILE_NAME}"
_LEGACY_PROFILE_MARKDOWN_RELATIVE_PATH = f"user/{PROFILE_ARTIFACT_FILE_NAMES[0]}"
_LEGACY_PROFILE_JSON_RELATIVE_PATH = f"user/{PROFILE_ARTIFACT_FILE_NAMES[1]}"


class ManagedBackendStorage(BackendStorage):
    """Managed storage backed by Postgres metadata and object-store artifacts."""
    _CANONICAL_USER_MEMORY_RELATIVE_PATH = _CANONICAL_USER_MEMORY_RELATIVE_PATH
    _CANONICAL_CROSS_SESSION_MEMORY_RELATIVE_PATH = _CANONICAL_CROSS_SESSION_MEMORY_RELATIVE_PATH
    _LEGACY_PROFILE_MARKDOWN_RELATIVE_PATH = _LEGACY_PROFILE_MARKDOWN_RELATIVE_PATH
    _LEGACY_PROFILE_JSON_RELATIVE_PATH = _LEGACY_PROFILE_JSON_RELATIVE_PATH
    _CROSS_SESSION_MEMORY_TEMPLATE = CROSS_SESSION_MEMORY_TEMPLATE
    logger = logger
    now_ms = staticmethod(now_ms)

    @staticmethod
    def _resolve_next_retry_at_ms(
        value: int | object | None,
        existing_value: int | None,
    ) -> int | None:
        return resolve_next_retry_at_ms(value, existing_value)

    @staticmethod
    def _resolve_error_details_json(
        error_details: dict[str, Any] | object | None,
        error_code: str | None,
        existing_json: str | None,
    ) -> str | None:
        return resolve_error_details_json(error_details, error_code, existing_json)

    def __init__(
        self,
        *,
        database_url: str,
        object_store: ObjectStore,
    ) -> None:
        self.object_store = object_store
        self.metadata_store = PostgresMetadataStore(database_url=database_url)
        super().__init__(
            storage_info=StorageInfo(
                backend="managed",
                details={
                    "database_url_configured": bool(database_url),
                    "object_store_provider": object_store.provider_name,
                    "object_store_name": object_store.store_name,
                    "object_store_prefix": object_store.key_prefix,
                    "object_store_endpoint": object_store.endpoint or "",
                },
            )
        )

    def bootstrap(self) -> StorageBootstrapResult:
        self.metadata_store.initialize_schema()
        self._ensure_profile_artifacts()
        return StorageBootstrapResult(
            storage_backend=self.backend_name,
            sqlite_path=None,
            user_profile_markdown_path=None,
            bootstrapped_at_ms=now_ms(),
            storage_details=dict(self.storage_info.details),
        )

    def bootstrap_session_storage(self, *, session_id: str) -> SessionStorageResult:
        session_storage = self.get_session_storage_paths(session_id=session_id)
        self._register_session_artifacts(
            session_id=session_id,
            session_storage=session_storage,
        )
        self._ensure_session_artifacts(
            session_id=session_id,
            session_storage=session_storage,
        )
        return session_storage

    def ensure_session_storage(self, *, session_id: str) -> SessionStorageResult:
        return self.bootstrap_session_storage(session_id=session_id)

    def get_session_storage_paths(self, *, session_id: str) -> SessionStorageResult:
        session_dir = Path("memory") / "sessions" / self._storage_component_for_id(session_id)
        return SessionStorageResult(
            session_dir=session_dir,
            short_term_memory_markdown_path=session_dir / SHORT_TERM_MEMORY_MARKDOWN_FILE_NAME,
            session_memory_markdown_path=session_dir / SESSION_MEMORY_MARKDOWN_FILE_NAME,
            vision_events_log_path=session_dir / VISION_EVENTS_LOG_FILE_NAME,
            vision_routing_events_log_path=session_dir / VISION_ROUTING_EVENTS_LOG_FILE_NAME,
        )

    def register_artifact(
        self,
        *,
        artifact_id: str,
        session_id: str | None,
        artifact_kind: str,
        artifact_path: Any,
        content_type: str,
        metadata: dict[str, Any],
    ) -> ArtifactRecord:
        relative_path = self._resolve_relative_path(artifact_path)
        created_at_ms = now_ms()
        return self.metadata_store.register_artifact_record(
            artifact_id=artifact_id,
            session_id=session_id,
            artifact_kind=artifact_kind,
            relative_path=relative_path,
            content_type=content_type,
            metadata_json=json.dumps(metadata, ensure_ascii=True, sort_keys=True),
            created_at_ms=created_at_ms,
            updated_at_ms=created_at_ms,
        )

    def read_user_profile(self) -> dict[str, object]:
        return managed_profile_ops.read_user_profile(self)

    def read_user_profile_markdown(self) -> str:
        return managed_profile_ops.read_user_profile_markdown(self)

    def read_cross_session_memory(self) -> str:
        return managed_profile_ops.read_cross_session_memory(self)

    def write_user_profile(
        self,
        *,
        payload: Mapping[str, object],
        source: str | None = None,
        updated_at_ms: int | None = None,
    ) -> dict[str, object]:
        return managed_profile_ops.write_user_profile(
            self,
            payload=payload,
            source=source,
            updated_at_ms=updated_at_ms,
        )

    def reset_user_profile(self) -> dict[str, object]:
        return managed_profile_ops.reset_user_profile(self)

    def write_cross_session_memory(self, *, markdown: str) -> None:
        managed_profile_ops.write_cross_session_memory(self, markdown=markdown)

    def upsert_session_status(self, *, session_id: str, status: str) -> None:
        self.metadata_store.upsert_session_status(session_id=session_id, status=status)

    def append_vision_event(self, *, session_id: str, event: dict[str, Any]) -> None:
        self.ensure_session_storage(session_id=session_id)
        self._append_event_to_log_artifact(
            session_id=session_id,
            log_kind="vision_events",
            event=event,
        )

    def append_vision_routing_event(self, *, session_id: str, event: dict[str, Any]) -> None:
        self.ensure_session_storage(session_id=session_id)
        self._append_event_to_log_artifact(
            session_id=session_id,
            log_kind="vision_routing_events",
            event=event,
        )

    def read_vision_events(self, *, session_id: str) -> list[AcceptedVisionEvent]:
        self._require_session_persisted(session_id=session_id)
        raw_events = self._read_session_event_payloads(
            session_id=session_id,
            log_kind="vision_events",
        )
        valid_events: list[AcceptedVisionEvent] = []
        for payload in raw_events:
            event, _ = coerce_accepted_vision_event(payload)
            if event is not None:
                valid_events.append(event)
        return valid_events

    def read_session_memory(self, *, session_id: str) -> dict[str, Any]:
        self._require_session_persisted(session_id=session_id)
        session_storage = self.get_session_storage_paths(session_id=session_id)
        markdown_text = self._read_memory_markdown_with_fallbacks(
            canonical_relative_path=self._relative_path(session_storage.session_memory_markdown_path),
            legacy_relative_paths=(
                self._legacy_session_relative_path(
                    session_id=session_id,
                    file_name="session_memory.md",
                ),
            ),
            fallback_document=self._coerce_text(
                (self.metadata_store.read_session_memory_document(
                    session_id=session_id,
                    memory_scope="session",
                ) or {}).get("markdown_text")
            ),
            fallback_template=SESSION_MEMORY_TEMPLATE,
            content_type="text/markdown",
            context=f"managed session memory artifact session_id={session_id}",
        )
        return self._read_memory_markdown_payload(markdown_text)

    def read_short_term_memory(self, *, session_id: str) -> dict[str, Any]:
        self._require_session_persisted(session_id=session_id)
        session_storage = self.get_session_storage_paths(session_id=session_id)
        markdown_text = self._read_memory_markdown_with_fallbacks(
            canonical_relative_path=self._relative_path(session_storage.short_term_memory_markdown_path),
            legacy_relative_paths=(
                self._legacy_session_relative_path(
                    session_id=session_id,
                    file_name="short_term_memory.md",
                ),
            ),
            fallback_document=self._coerce_text(
                (self.metadata_store.read_session_memory_document(
                    session_id=session_id,
                    memory_scope="short_term",
                ) or {}).get("markdown_text")
            ),
            fallback_template=SHORT_TERM_MEMORY_TEMPLATE,
            content_type="text/markdown",
            context=f"managed short-term memory artifact session_id={session_id}",
        )
        return self._read_memory_markdown_payload(markdown_text)

    def write_short_term_memory(
        self,
        *,
        session_id: str,
        payload: dict[str, Any],
        markdown_text: str,
    ) -> None:
        session_storage = self.ensure_session_storage(session_id=session_id)
        self.object_store.put_text(
            relative_path=self._relative_path(session_storage.short_term_memory_markdown_path),
            content=markdown_text,
            content_type="text/markdown",
        )

    def write_session_memory(
        self,
        *,
        session_id: str,
        payload: dict[str, Any],
        markdown_text: str,
    ) -> None:
        session_storage = self.ensure_session_storage(session_id=session_id)
        self.object_store.put_text(
            relative_path=self._relative_path(session_storage.session_memory_markdown_path),
            content=markdown_text,
            content_type="text/markdown",
        )

    def get_session_memory_reset_eligibility(
        self,
        *,
        session_id: str,
    ) -> SessionMemoryResetEligibility:
        counts = self.metadata_store.get_session_metadata_counts(session_id=session_id)
        session_row = self.metadata_store.get_session_row(session_id=session_id)
        has_persisted_memory = any(
            [
                bool(counts["session_row_present"]),
                int(counts["artifact_count"]) > 0,
                int(counts["vision_frame_count"]) > 0,
                self.object_store.exists(
                    relative_path=self._relative_path(
                        self.get_session_storage_paths(session_id=session_id).short_term_memory_markdown_path
                    )
                ),
                self.object_store.exists(
                    relative_path=self._relative_path(
                        self.get_session_storage_paths(session_id=session_id).session_memory_markdown_path
                    )
                ),
                self.object_store.exists(
                    relative_path=self._relative_path(
                        self.get_session_storage_paths(session_id=session_id).vision_events_log_path
                    )
                ),
            ]
        )
        is_active = bool(session_row is not None and str(session_row["status"]) == "active")
        if is_active:
            return SessionMemoryResetEligibility(
                session_id=session_id,
                is_active=True,
                has_persisted_memory=True,
                eligible=False,
                reason="session_is_active",
            )
        if not has_persisted_memory:
            return SessionMemoryResetEligibility(
                session_id=session_id,
                is_active=False,
                has_persisted_memory=False,
                eligible=False,
                reason="session_memory_not_found",
            )
        return SessionMemoryResetEligibility(
            session_id=session_id,
            is_active=False,
            has_persisted_memory=True,
            eligible=True,
            reason="eligible",
        )

    def reset_session_memory(self, *, session_id: str) -> SessionMemoryResetResult:
        eligibility = self.get_session_memory_reset_eligibility(session_id=session_id)
        if eligibility.is_active:
            raise RuntimeError(f"Cannot reset memory for active session {session_id!r}")
        if not eligibility.has_persisted_memory:
            raise KeyError(f"No persisted memory found for session {session_id!r}")

        relative_paths = {
            self._relative_path(self.get_session_storage_paths(session_id=session_id).short_term_memory_markdown_path),
            self._relative_path(self.get_session_storage_paths(session_id=session_id).session_memory_markdown_path),
            self._relative_path(self.get_session_storage_paths(session_id=session_id).vision_events_log_path),
            self._relative_path(self.get_session_storage_paths(session_id=session_id).vision_routing_events_log_path),
            self._legacy_session_relative_path(session_id=session_id, file_name="short_term_memory.md"),
            self._legacy_session_relative_path(session_id=session_id, file_name="session_memory.md"),
            self._legacy_session_relative_path(session_id=session_id, file_name="vision_events.jsonl"),
        }
        for artifact in self.metadata_store.list_artifact_records_for_session(session_id=session_id):
            relative_paths.add(artifact.relative_path)
        for relative_path in sorted(relative_paths):
            self.object_store.delete(relative_path=relative_path)

        deleted = self.metadata_store.delete_session_metadata(session_id=session_id)
        return SessionMemoryResetResult(
            session_id=session_id,
            deleted_artifact_rows=int(deleted["deleted_artifact_rows"]),
            deleted_vision_frame_rows=int(deleted["deleted_vision_frame_rows"]),
            deleted_session_rows=int(deleted["deleted_session_rows"]),
            removed_session_dir=False,
            removed_vision_frames_dir=False,
        )

    def list_session_memory_retention_eligibility(
        self,
        *,
        retention_days: int,
        reference_time_ms: int | None = None,
    ) -> list[SessionMemoryRetentionEligibility]:
        if retention_days < 1:
            raise ValueError("retention_days must be >= 1")
        reference_ms = reference_time_ms if reference_time_ms is not None else now_ms()
        cutoff_at_ms = max(0, reference_ms - retention_days * 24 * 60 * 60 * 1000)
        results: list[SessionMemoryRetentionEligibility] = []
        for row in self.metadata_store.list_session_rows_for_retention():
            session_id = str(row["session_id"])
            status = str(row["status"])
            updated_at_ms = int(row["updated_at_ms"])
            if status == "active":
                reason = "session_is_active"
                eligible = False
            elif status != "ended":
                reason = "session_not_ended"
                eligible = False
            elif updated_at_ms > cutoff_at_ms:
                reason = "within_retention_window"
                eligible = False
            else:
                reason = "expired_ended_session"
                eligible = True
            results.append(
                SessionMemoryRetentionEligibility(
                    session_id=session_id,
                    status=status,
                    updated_at_ms=updated_at_ms,
                    cutoff_at_ms=cutoff_at_ms,
                    eligible=eligible,
                    reason=reason,
                )
            )
        return results

    def sweep_expired_session_memory(
        self,
        *,
        retention_days: int,
        reference_time_ms: int | None = None,
    ) -> list[SessionMemoryResetResult]:
        results: list[SessionMemoryResetResult] = []
        for eligibility in self.list_session_memory_retention_eligibility(
            retention_days=retention_days,
            reference_time_ms=reference_time_ms,
        ):
            if eligibility.eligible:
                results.append(self.reset_session_memory(session_id=eligibility.session_id))
        return results

    def read_session_memory_status(
        self,
        *,
        session_id: str,
        recent_limit: int = 10,
    ) -> dict[str, object]:
        self._require_session_persisted(session_id=session_id)
        session_row = self.metadata_store.get_session_row(session_id=session_id)
        short_term_memory = self.read_short_term_memory(session_id=session_id)
        session_memory = self.read_session_memory(session_id=session_id)
        accepted_events = self.read_vision_events(session_id=session_id)
        recent_records = self.metadata_store.list_recent_vision_frame_records(
            session_id=session_id,
            limit=max(1, recent_limit),
        )
        counts = self.metadata_store.get_session_metadata_counts(session_id=session_id)

        status = (
            str(session_memory.get("status") or short_term_memory.get("status") or "")
            or ("ready" if accepted_events else "unbootstrapped")
        )
        return {
            "session_id": session_id,
            "status": status,
            "session_state": str(session_row["status"]) if session_row is not None else None,
            "session_created_at_ms": (
                int(session_row["created_at_ms"]) if session_row is not None else None
            ),
            "session_updated_at_ms": (
                int(session_row["updated_at_ms"]) if session_row is not None else None
            ),
            "accepted_event_count": len(accepted_events),
            "total_frames": int(counts["vision_frame_count"]),
            "short_term_memory": short_term_memory,
            "session_memory": session_memory,
            "recent_frames": [self._recent_frame_payload(record) for record in recent_records],
            "session_dir_exists": False,
        }

    def update_vision_frame_processing(
        self,
        *,
        session_id: str,
        frame_id: str,
        processing_status: str,
        gate_status: str | None = None,
        gate_reason: str | None = None,
        phash: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        analyzed_at_ms: int | None = None,
        next_retry_at_ms: int | object = UNSET,
        attempt_count: int | object = UNSET,
        error_code: str | None = None,
        error_details: dict[str, Any] | None | object = UNSET,
        summary_snippet: str | None = None,
        routing_status: str | None = None,
        routing_reason: str | None = None,
        routing_score: float | None = None,
        routing_metadata: dict[str, Any] | None = None,
    ) -> None:
        managed_vision_ops.update_vision_frame_processing(
            self,
            session_id=session_id,
            frame_id=frame_id,
            processing_status=processing_status,
            gate_status=gate_status,
            gate_reason=gate_reason,
            phash=phash,
            provider=provider,
            model=model,
            analyzed_at_ms=analyzed_at_ms,
            next_retry_at_ms=next_retry_at_ms,
            attempt_count=attempt_count,
            error_code=error_code,
            error_details=error_details,
            summary_snippet=summary_snippet,
            routing_status=routing_status,
            routing_reason=routing_reason,
            routing_score=routing_score,
            routing_metadata=routing_metadata,
        )

    def get_vision_frame_record(
        self,
        *,
        session_id: str,
        frame_id: str,
    ) -> VisionFrameIndexRecord | None:
        return managed_vision_ops.get_vision_frame_record(
            self,
            session_id=session_id,
            frame_id=frame_id,
        )

    def store_vision_frame_ingest(
        self,
        *,
        session_id: str,
        frame_id: str,
        ts_ms: int,
        capture_ts_ms: int,
        width: int,
        height: int,
        frame_bytes: bytes,
    ) -> VisionFrameIngestResult:
        return managed_vision_ops.store_vision_frame_ingest(
            self,
            session_id=session_id,
            frame_id=frame_id,
            ts_ms=ts_ms,
            capture_ts_ms=capture_ts_ms,
            width=width,
            height=height,
            frame_bytes=frame_bytes,
        )

    def delete_vision_ingest_artifacts(self, *, session_id: str, frame_id: str) -> None:
        managed_vision_ops.delete_vision_ingest_artifacts(
            self,
            session_id=session_id,
            frame_id=frame_id,
        )

    def list_memory_export_artifacts(self) -> list[MemoryExportArtifact]:
        return managed_export_ops.list_memory_export_artifacts(self)

    def migrate_legacy_storage_layout(self) -> dict[str, Any]:
        raise RuntimeError(
            "Storage layout migration is only supported when "
            "BACKEND_STORAGE_BACKEND=local."
        )

    def _register_session_artifacts(
        self,
        *,
        session_id: str,
        session_storage: SessionStorageResult,
    ) -> None:
        artifact_metadata = {"session_id": session_id, "artifact_role": "derived_memory"}
        for descriptor in session_artifact_descriptors(
            session_id=session_id,
            session_storage=session_storage,
        ):
            self.register_artifact(
                artifact_id=descriptor.artifact_id,
                session_id=session_id,
                artifact_kind=descriptor.artifact_kind,
                artifact_path=descriptor.artifact_path,
                content_type=descriptor.content_type,
                metadata=artifact_metadata,
            )

    def _ensure_profile_artifacts(self) -> None:
        managed_profile_ops.ensure_profile_artifacts(self)

    def _ensure_session_artifacts(
        self,
        *,
        session_id: str,
        session_storage: SessionStorageResult,
    ) -> None:
        self._read_memory_markdown_with_fallbacks(
            canonical_relative_path=self._relative_path(session_storage.short_term_memory_markdown_path),
            legacy_relative_paths=(
                self._legacy_session_relative_path(
                    session_id=session_id,
                    file_name="short_term_memory.md",
                ),
            ),
            fallback_document=self._coerce_text(
                (self.metadata_store.read_session_memory_document(
                    session_id=session_id,
                    memory_scope="short_term",
                ) or {}).get("markdown_text")
            ),
            fallback_template=SHORT_TERM_MEMORY_TEMPLATE,
            content_type="text/markdown",
            context=f"managed short-term memory artifact session_id={session_id}",
        )
        self._read_memory_markdown_with_fallbacks(
            canonical_relative_path=self._relative_path(session_storage.session_memory_markdown_path),
            legacy_relative_paths=(
                self._legacy_session_relative_path(
                    session_id=session_id,
                    file_name="session_memory.md",
                ),
            ),
            fallback_document=self._coerce_text(
                (self.metadata_store.read_session_memory_document(
                    session_id=session_id,
                    memory_scope="session",
                ) or {}).get("markdown_text")
            ),
            fallback_template=SESSION_MEMORY_TEMPLATE,
            content_type="text/markdown",
            context=f"managed session memory artifact session_id={session_id}",
        )
        self._ensure_text_artifact(
            relative_path=self._relative_path(session_storage.vision_events_log_path),
            fallback_text=self._render_ndjson(
                self.metadata_store.list_session_events(
                    session_id=session_id,
                    log_kind="vision_events",
                )
            ),
            content_type="application/x-ndjson",
        )
        self._ensure_text_artifact(
            relative_path=self._relative_path(session_storage.vision_routing_events_log_path),
            fallback_text=self._render_ndjson(
                self.metadata_store.list_session_events(
                    session_id=session_id,
                    log_kind="vision_routing_events",
                )
            ),
            content_type="application/x-ndjson",
        )

    def _ensure_text_artifact(
        self,
        *,
        relative_path: str,
        fallback_text: str,
        content_type: str,
    ) -> None:
        if self.object_store.exists(relative_path=relative_path):
            return
        self.object_store.put_text(
            relative_path=relative_path,
            content=fallback_text,
            content_type=content_type,
        )

    def _append_event_to_log_artifact(
        self,
        *,
        session_id: str,
        log_kind: str,
        event: dict[str, Any],
    ) -> None:
        session_storage = self.get_session_storage_paths(session_id=session_id)
        relative_path = self._relative_path(
            session_storage.vision_events_log_path
            if log_kind == "vision_events"
            else session_storage.vision_routing_events_log_path
        )
        payloads = self._read_ndjson_artifact(
            relative_path=relative_path,
            context=f"managed {log_kind} artifact session_id={session_id}",
        )
        if payloads is None:
            payloads = self.metadata_store.list_session_events(
                session_id=session_id,
                log_kind=log_kind,
            )
        payloads.append(event)
        self.object_store.put_text(
            relative_path=relative_path,
            content=self._render_ndjson(payloads),
            content_type="application/x-ndjson",
        )

    def _read_session_event_payloads(
        self,
        *,
        session_id: str,
        log_kind: str,
    ) -> list[dict[str, Any]]:
        session_storage = self.get_session_storage_paths(session_id=session_id)
        relative_path = self._relative_path(
            session_storage.vision_events_log_path
            if log_kind == "vision_events"
            else session_storage.vision_routing_events_log_path
        )
        from_object = self._read_ndjson_artifact(
            relative_path=relative_path,
            context=f"managed {log_kind} artifact session_id={session_id}",
        )
        if from_object is not None:
            return from_object
        return self.metadata_store.list_session_events(
            session_id=session_id,
            log_kind=log_kind,
        )

    def _read_memory_markdown_with_fallbacks(
        self,
        *,
        canonical_relative_path: str,
        legacy_relative_paths: tuple[str, ...],
        fallback_document: str | None,
        fallback_template: str,
        content_type: str,
        context: str,
    ) -> str:
        canonical_text = self.object_store.get_text(relative_path=canonical_relative_path)
        if canonical_text is not None:
            return canonical_text
        for legacy_path in legacy_relative_paths:
            legacy_text = self.object_store.get_text(relative_path=legacy_path)
            if legacy_text is None:
                continue
            self.object_store.put_text(
                relative_path=canonical_relative_path,
                content=legacy_text,
                content_type=content_type,
            )
            return legacy_text
        if fallback_document is not None:
            self.object_store.put_text(
                relative_path=canonical_relative_path,
                content=fallback_document,
                content_type=content_type,
            )
            return fallback_document
        self.object_store.put_text(
            relative_path=canonical_relative_path,
            content=fallback_template,
            content_type=content_type,
        )
        return fallback_template

    def _read_memory_markdown_payload(self, markdown: str) -> dict[str, Any]:
        return parse_managed_memory_markdown_payload(markdown)

    def _read_json_artifact(
        self,
        *,
        relative_path: str,
        context: str,
    ) -> dict[str, object] | None:
        raw_json = self.object_store.get_text(relative_path=relative_path)
        if raw_json is None:
            return None
        payload = self._parse_json_payload(raw_json, context=context)
        if payload is None:
            logger.warning("Failed decoding %s from object store; falling back", context)
            return None
        return payload

    def _read_ndjson_artifact(
        self,
        *,
        relative_path: str,
        context: str,
    ) -> list[dict[str, Any]] | None:
        raw_text = self.object_store.get_text(relative_path=relative_path)
        if raw_text is None:
            return None
        payloads: list[dict[str, Any]] = []
        for index, line in enumerate(raw_text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Failed decoding %s line=%s; falling back", context, index)
                return None
            if not isinstance(payload, dict):
                logger.warning("Invalid NDJSON root for %s line=%s; falling back", context, index)
                return None
            payloads.append(payload)
        return payloads

    def _parse_json_payload(
        self,
        raw_json: str | None,
        *,
        context: str,
    ) -> dict[str, object] | None:
        if raw_json is None:
            return None
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            logger.warning("Failed decoding %s", context)
            return None
        if not isinstance(payload, dict):
            logger.warning("Invalid JSON root for %s", context)
            return None
        return payload

    def _read_profile_markdown_export_bytes(self) -> bytes:
        markdown_text = self.object_store.get_text(
            relative_path=_CANONICAL_USER_MEMORY_RELATIVE_PATH
        )
        if markdown_text is not None:
            return markdown_text.encode("utf-8")
        return self.read_user_profile_markdown().encode("utf-8")

    def _build_export_artifacts_for_paths(
        self,
        *,
        artifact_kind: str,
        session_id: str | None,
        paths: tuple[str, ...],
    ) -> list[MemoryExportArtifact]:
        artifacts: list[MemoryExportArtifact] = []
        for relative_path in paths:
            payload = self.object_store.get_bytes(relative_path=relative_path)
            if payload is None:
                continue
            content_type = "text/markdown"
            if relative_path.endswith(".ndjson"):
                content_type = "application/x-ndjson"
            artifacts.append(
                MemoryExportArtifact(
                    artifact_id=None,
                    session_id=session_id,
                    artifact_kind=artifact_kind,
                    relative_path=relative_path,
                    content_type=content_type,
                    created_at_ms=None,
                    read_bytes=lambda payload=payload: payload,
                )
            )
        return artifacts

    def _require_session_persisted(self, *, session_id: str) -> None:
        eligibility = self.get_session_memory_reset_eligibility(session_id=session_id)
        if not eligibility.has_persisted_memory:
            raise SessionNotFoundError(f"No persisted memory found for session {session_id!r}")

    def _resolve_relative_path(self, artifact_path: Any) -> str:
        if isinstance(artifact_path, Path):
            if artifact_path.is_absolute():
                raise ValueError(
                    "Managed storage artifact paths must be relative logical paths, not absolute paths."
                )
            return normalize_object_store_relative_path(artifact_path.as_posix())
        if isinstance(artifact_path, str):
            return normalize_object_store_relative_path(artifact_path)
        raise TypeError(f"Unsupported managed artifact path type: {type(artifact_path).__name__}")

    def _coerce_text(self, value: object) -> str | None:
        if isinstance(value, str):
            return value
        return None

    def _render_ndjson(self, payloads: list[dict[str, Any]]) -> str:
        if not payloads:
            return ""
        return "".join(
            json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n"
            for payload in payloads
        )

    def _legacy_session_relative_path(self, *, session_id: str, file_name: str) -> str:
        return normalize_object_store_relative_path(
            str(Path("session") / self._storage_component_for_id(session_id) / file_name)
        )

    def _parse_csv_list(self, raw_value: str) -> list[str]:
        return parse_csv_list(raw_value)

    def _split_semicolon_list(self, raw_value: str) -> list[str]:
        return split_semicolon_list(raw_value)

    def _read_section_text(self, markdown: str, section_name: str) -> str:
        return read_section_text(markdown, section_name)

    def _canonical_memory_key(self, raw_key: str, *, is_short_term_memory: bool = False) -> str:
        from backend.infrastructure.storage.common.memory_markdown import canonical_memory_key

        return canonical_memory_key(raw_key, is_short_term_memory=is_short_term_memory)

    def _relative_path(self, path: Path) -> str:
        return normalize_object_store_relative_path(path.as_posix())

    def _vision_frame_relative_paths(self, *, session_id: str, frame_id: str) -> tuple[str, str]:
        session_component = self._storage_component_for_id(session_id)
        frame_component = self._storage_component_for_id(frame_id)
        root = Path("vision_frames") / session_component
        return (
            self._relative_path(root / f"{frame_component}.jpg"),
            self._relative_path(root / f"{frame_component}.json"),
        )

    def _recent_frame_payload(self, record: VisionFrameIndexRecord) -> dict[str, object]:
        error_details: dict[str, object] | None = None
        if record.error_details_json is not None:
            try:
                loaded = json.loads(record.error_details_json)
            except json.JSONDecodeError:
                loaded = {"raw": record.error_details_json}
            if isinstance(loaded, dict):
                error_details = loaded
        return {
            "frame_id": record.frame_id,
            "capture_ts_ms": record.capture_ts_ms,
            "processing_status": record.processing_status,
            "gate_status": record.gate_status,
            "gate_reason": record.gate_reason,
            "provider": record.provider,
            "model": record.model,
            "analyzed_at_ms": record.analyzed_at_ms,
            "next_retry_at_ms": record.next_retry_at_ms,
            "attempt_count": record.attempt_count,
            "error_code": record.error_code,
            "error_details": error_details,
            "routing_status": record.routing_status,
            "routing_reason": record.routing_reason,
            "routing_score": record.routing_score,
        }

    def _storage_component_for_id(self, raw_id: str) -> str:
        return storage_component_for_id(raw_id)
