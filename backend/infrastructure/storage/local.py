from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Mapping

from backend.core.storage import (
    ArtifactRecord,
    BackendStorage,
    MemoryExportArtifact,
    SessionMemoryResetEligibility,
    SessionMemoryResetResult,
    SessionMemoryRetentionEligibility,
    SessionStorageResult,
    VisionFrameIndexRecord,
    VisionFrameIngestResult,
)
from backend.infrastructure.storage.artifacts import ArtifactStorageMixin
from backend.infrastructure.storage.memory_v2_layout import (
    global_memory_evidence_relative_path,
    maintenance_state_relative_path,
    memory_item_relative_path,
    retrieval_index_relative_path,
    session_memory_candidate_log_relative_path,
    session_memory_evidence_relative_path,
    session_observation_log_relative_path,
)
from backend.infrastructure.storage.paths import StoragePathMixin
from backend.infrastructure.storage.user_memory import UserMemoryStorageMixin
from backend.infrastructure.storage.sessions import SessionStorageMixin
from backend.infrastructure.storage.sqlite import SQLiteStorageMixin
from backend.infrastructure.storage.types import StorageBootstrapResult, StorageInfo, StoragePaths, now_ms
from backend.infrastructure.storage.vision import VisionFrameStorageMixin
from backend.memory.normalization_v2 import (
    parse_maintenance_state,
    parse_memory_candidate,
    parse_memory_evidence,
    parse_memory_item,
    parse_retrieval_index_state,
    parse_session_observation,
    render_maintenance_state,
    render_memory_candidate,
    render_memory_evidence,
    render_memory_item,
    render_ndjson,
    render_retrieval_index_state,
    render_session_observation,
)
from backend.memory.types_v2 import (
    MaintenanceState,
    MemoryCandidateV2,
    MemoryEvidence,
    MemoryItem,
    RetrievalIndexState,
    SessionObservation,
)

if TYPE_CHECKING:
    from backend.memory.events import AcceptedVisionEvent


class LocalBackendStorage(
    SessionStorageMixin,
    UserMemoryStorageMixin,
    ArtifactStorageMixin,
    VisionFrameStorageMixin,
    SQLiteStorageMixin,
    StoragePathMixin,
    BackendStorage,
):
    """SQLite/filesystem storage implementation used for local mode."""

    # Explicit forwarding methods make the intended MRO resolution visible to
    # static analysis without changing the concrete mixin implementation used.
    def bootstrap_session_storage(self, *, session_id: str) -> SessionStorageResult:
        return super().bootstrap_session_storage(session_id=session_id)

    def ensure_session_storage(self, *, session_id: str) -> SessionStorageResult:
        return super().ensure_session_storage(session_id=session_id)

    def get_session_storage_paths(self, *, session_id: str) -> SessionStorageResult:
        return super().get_session_storage_paths(session_id=session_id)

    def upsert_session_status(self, *, session_id: str, status: str) -> None:
        super().upsert_session_status(session_id=session_id, status=status)

    def append_vision_event(self, *, session_id: str, event: dict[str, Any]) -> None:
        super().append_vision_event(session_id=session_id, event=event)

    def append_vision_routing_event(self, *, session_id: str, event: dict[str, Any]) -> None:
        super().append_vision_routing_event(session_id=session_id, event=event)

    def read_vision_events(self, *, session_id: str) -> list["AcceptedVisionEvent"]:
        return super().read_vision_events(session_id=session_id)

    def read_session_memory(self, *, session_id: str) -> dict[str, Any]:
        return super().read_session_memory(session_id=session_id)

    def read_short_term_memory(self, *, session_id: str) -> dict[str, Any]:
        return super().read_short_term_memory(session_id=session_id)

    def read_session_memory_markdown(self, *, session_id: str) -> str:
        return super().read_session_memory_markdown(session_id=session_id)

    def read_short_term_memory_markdown(self, *, session_id: str) -> str:
        return super().read_short_term_memory_markdown(session_id=session_id)

    def get_session_memory_reset_eligibility(
        self,
        *,
        session_id: str,
    ) -> SessionMemoryResetEligibility:
        return super().get_session_memory_reset_eligibility(session_id=session_id)

    def reset_session_memory(self, *, session_id: str) -> SessionMemoryResetResult:
        return super().reset_session_memory(session_id=session_id)

    def list_session_memory_retention_eligibility(
        self,
        *,
        retention_days: int,
        reference_time_ms: int | None = None,
    ) -> list[SessionMemoryRetentionEligibility]:
        return super().list_session_memory_retention_eligibility(
            retention_days=retention_days,
            reference_time_ms=reference_time_ms,
        )

    def sweep_expired_session_memory(
        self,
        *,
        retention_days: int,
        reference_time_ms: int | None = None,
    ) -> list[SessionMemoryResetResult]:
        return super().sweep_expired_session_memory(
            retention_days=retention_days,
            reference_time_ms=reference_time_ms,
        )

    def write_short_term_memory(
        self,
        *,
        session_id: str,
        payload: dict[str, Any],
        markdown_text: str,
    ) -> None:
        super().write_short_term_memory(
            session_id=session_id,
            payload=payload,
            markdown_text=markdown_text,
        )

    def write_session_memory(
        self,
        *,
        session_id: str,
        payload: dict[str, Any],
        markdown_text: str,
    ) -> None:
        super().write_session_memory(
            session_id=session_id,
            payload=payload,
            markdown_text=markdown_text,
        )

    def read_session_memory_status(self, *, session_id: str) -> dict[str, object]:
        return super().read_session_memory_status(session_id=session_id)

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
        return super().register_artifact(
            artifact_id=artifact_id,
            session_id=session_id,
            artifact_kind=artifact_kind,
            artifact_path=artifact_path,
            content_type=content_type,
            metadata=metadata,
        )

    def list_memory_export_artifacts(self) -> list[MemoryExportArtifact]:
        return super().list_memory_export_artifacts()

    def read_cross_session_memory(self) -> str:
        return super().read_cross_session_memory()

    def read_user_memory_payload(self) -> dict[str, object]:
        return super().read_user_memory_payload()

    def read_user_memory_markdown(self) -> str:
        return super().read_user_memory_markdown()

    def write_user_memory_payload(
        self,
        *,
        payload: Mapping[str, object],
        source: str | None = None,
        updated_at_ms: int | None = None,
    ) -> dict[str, object]:
        return super().write_user_memory_payload(
            payload=payload,
            source=source,
            updated_at_ms=updated_at_ms,
        )

    def reset_user_memory_payload(self) -> dict[str, object]:
        return super().reset_user_memory_payload()

    def write_user_memory(self, *, markdown: str) -> None:
        super().write_user_memory(markdown=markdown)

    def write_cross_session_memory(self, *, markdown: str) -> None:
        super().write_cross_session_memory(markdown=markdown)

    def append_memory_candidate(self, *, session_id: str, candidate: dict[str, Any]) -> None:
        super().append_memory_candidate(session_id=session_id, candidate=candidate)

    def read_memory_candidates(self, *, session_id: str) -> list[dict[str, Any]]:
        return super().read_memory_candidates(session_id=session_id)

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
        return super().store_vision_frame_ingest(
            session_id=session_id,
            frame_id=frame_id,
            ts_ms=ts_ms,
            capture_ts_ms=capture_ts_ms,
            width=width,
            height=height,
            frame_bytes=frame_bytes,
        )

    def delete_vision_ingest_artifacts(self, *, session_id: str, frame_id: str) -> None:
        super().delete_vision_ingest_artifacts(session_id=session_id, frame_id=frame_id)

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
        next_retry_at_ms: int | object = None,
        attempt_count: int | object = None,
        error_code: str | None = None,
        error_details: dict[str, Any] | None | object = None,
        summary_snippet: str | None = None,
        routing_status: str | None = None,
        routing_reason: str | None = None,
        routing_score: float | None = None,
        routing_metadata: dict[str, Any] | None = None,
    ) -> None:
        super().update_vision_frame_processing(
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
        return super().get_vision_frame_record(session_id=session_id, frame_id=frame_id)

    def write_memory_item(self, *, item: MemoryItem) -> MemoryItem:
        rendered = render_memory_item(item)
        path = self._memory_item_path(item_id=str(rendered["item_id"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(rendered, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return parse_memory_item(rendered)

    def read_memory_item(self, *, item_id: str) -> MemoryItem | None:
        path = self._memory_item_path(item_id=item_id)
        payload = self._read_json_file(path)
        if payload is None:
            return None
        return parse_memory_item(payload)

    def list_memory_items(self) -> list[MemoryItem]:
        items_dir = self.memory_v2_items_dir()
        if not items_dir.exists():
            return []
        items: list[MemoryItem] = []
        for path in sorted(items_dir.glob("*.json")):
            payload = self._read_json_file(path)
            if payload is None:
                continue
            items.append(parse_memory_item(payload))
        items.sort(key=lambda item: (item.last_seen_at_ms or 0, item.item_id), reverse=True)
        return items

    def delete_memory_item(self, *, item_id: str) -> bool:
        path = self._memory_item_path(item_id=item_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def write_memory_evidence(self, *, evidence: MemoryEvidence) -> MemoryEvidence:
        rendered = render_memory_evidence(evidence)
        path = self._memory_evidence_path(
            evidence_id=str(rendered["evidence_id"]),
            session_id=str(rendered["session_id"]) if rendered["session_id"] is not None else None,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(rendered, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return parse_memory_evidence(rendered)

    def read_memory_evidence(self, *, evidence_id: str) -> MemoryEvidence | None:
        candidates = [self._memory_evidence_path(evidence_id=evidence_id, session_id=None)]
        session_root = self.memory_v2_root_dir() / "sessions"
        if session_root.exists():
            candidates.extend(sorted(session_root.rglob(f"evidence/{evidence_id}.json")))
        for path in candidates:
            payload = self._read_json_file(path)
            if payload is not None:
                return parse_memory_evidence(payload)
        return None

    def write_memory_candidate_v2(
        self,
        *,
        session_id: str,
        candidate: MemoryCandidateV2,
    ) -> MemoryCandidateV2:
        path = self._memory_candidate_log_path(session_id=session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payloads = self._read_ndjson_file(path=path)
        rendered = render_memory_candidate(candidate)
        replaced = False
        for index, payload in enumerate(payloads):
            if str(payload.get("candidate_id")) == str(rendered["candidate_id"]):
                payloads[index] = rendered
                replaced = True
                break
        if not replaced:
            payloads.append(rendered)
        path.write_text(render_ndjson(payloads), encoding="utf-8")
        return parse_memory_candidate(rendered)

    def read_memory_candidates_v2(self, *, session_id: str) -> list[MemoryCandidateV2]:
        path = self._memory_candidate_log_path(session_id=session_id)
        return [parse_memory_candidate(payload) for payload in self._read_ndjson_file(path=path)]

    def write_session_observation(
        self,
        *,
        session_id: str,
        observation: SessionObservation,
    ) -> SessionObservation:
        path = self._session_observation_log_path(session_id=session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payloads = self._read_ndjson_file(path=path)
        rendered = render_session_observation(observation)
        replaced = False
        for index, payload in enumerate(payloads):
            if str(payload.get("observation_id")) == str(rendered["observation_id"]):
                payloads[index] = rendered
                replaced = True
                break
        if not replaced:
            payloads.append(rendered)
        path.write_text(render_ndjson(payloads), encoding="utf-8")
        return parse_session_observation(rendered)

    def read_session_observations(self, *, session_id: str) -> list[SessionObservation]:
        path = self._session_observation_log_path(session_id=session_id)
        return [parse_session_observation(payload) for payload in self._read_ndjson_file(path=path)]

    def write_retrieval_index_state(self, *, state: RetrievalIndexState) -> RetrievalIndexState:
        path = self.paths.data_root / retrieval_index_relative_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        rendered = render_retrieval_index_state(state)
        path.write_text(
            json.dumps(rendered, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return parse_retrieval_index_state(self._read_json_file(path))

    def read_retrieval_index_state(self) -> RetrievalIndexState:
        path = self.paths.data_root / retrieval_index_relative_path()
        return parse_retrieval_index_state(self._read_json_file(path))

    def write_maintenance_state(self, *, state: MaintenanceState) -> MaintenanceState:
        path = self.paths.data_root / maintenance_state_relative_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        rendered = render_maintenance_state(state)
        path.write_text(
            json.dumps(rendered, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return parse_maintenance_state(self._read_json_file(path))

    def read_maintenance_state(self) -> MaintenanceState:
        path = self.paths.data_root / maintenance_state_relative_path()
        return parse_maintenance_state(self._read_json_file(path))

    def __init__(self, *, paths: StoragePaths) -> None:
        self.paths = paths
        super().__init__(
            storage_info=StorageInfo(
                backend="local",
                details={
                    "data_root": str(paths.data_root),
                    "memory_root": str(paths.memory_root),
                    "user_root": str(paths.user_root),
                    "session_root": str(paths.session_root),
                    "vision_frames_root": str(paths.vision_frames_root),
                    "sqlite_path": str(paths.sqlite_path),
                    "user_memory_path": str(paths.user_memory_path),
                    "cross_session_memory_path": str(paths.cross_session_memory_path),
                    "user_profile_markdown_path": str(paths.user_profile_markdown_path),
                },
            )
        )

    def bootstrap(self) -> StorageBootstrapResult:
        self._ensure_directories()
        self._ensure_user_memory_files()
        self._initialize_sqlite()
        return StorageBootstrapResult(
            storage_backend=self.backend_name,
            sqlite_path=self.paths.sqlite_path,
            user_profile_markdown_path=self.paths.user_memory_path,
            bootstrapped_at_ms=now_ms(),
            storage_details=dict(self.storage_info.details),
        )

    def local_storage_paths(self) -> StoragePaths:
        return self.paths

    def _memory_item_path(self, *, item_id: str):
        return self.paths.data_root / memory_item_relative_path(item_id=item_id)

    def _memory_evidence_path(self, *, evidence_id: str, session_id: str | None):
        if session_id:
            return self.paths.data_root / session_memory_evidence_relative_path(
                session_component=self._storage_component_for_id(session_id),
                evidence_id=evidence_id,
            )
        return self.paths.data_root / global_memory_evidence_relative_path(evidence_id=evidence_id)

    def _memory_candidate_log_path(self, *, session_id: str):
        return self.paths.data_root / session_memory_candidate_log_relative_path(
            session_component=self._storage_component_for_id(session_id)
        )

    def _session_observation_log_path(self, *, session_id: str):
        return self.paths.data_root / session_observation_log_relative_path(
            session_component=self._storage_component_for_id(session_id)
        )

    def _read_json_file(self, path) -> dict[str, object] | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _read_ndjson_file(self, *, path) -> list[dict[str, object]]:
        if not path.exists():
            return []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            return []
        payloads: list[dict[str, object]] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                payloads.append(payload)
        return payloads
