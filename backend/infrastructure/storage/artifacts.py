from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.infrastructure.storage.memory_v2_layout import MEMORY_V2_ROOT
from backend.infrastructure.storage.types import ArtifactRecord, MemoryExportArtifact, now_ms


class ArtifactStorageMixin:
    def register_artifact(
        self,
        *,
        artifact_id: str,
        session_id: str | None,
        artifact_kind: str,
        artifact_path,
        content_type: str,
        metadata: dict[str, Any],
    ) -> ArtifactRecord:
        relative_path = str(artifact_path.relative_to(self.paths.data_root))
        created_at_ms = now_ms()
        updated_at_ms = created_at_ms
        metadata_json = json.dumps(metadata, ensure_ascii=True, sort_keys=True)

        def _operation() -> None:
            with self.connect() as connection:
                self._upsert_artifact_record(
                    artifact_id=artifact_id,
                    session_id=session_id,
                    artifact_kind=artifact_kind,
                    relative_path=relative_path,
                    content_type=content_type,
                    metadata_json=metadata_json,
                    created_at_ms=created_at_ms,
                    updated_at_ms=updated_at_ms,
                    connection=connection,
                )
                connection.commit()

        self._run_with_sqlite_retry(_operation)
        return ArtifactRecord(
            artifact_id=artifact_id,
            session_id=session_id,
            artifact_kind=artifact_kind,
            relative_path=relative_path,
            content_type=content_type,
            metadata_json=metadata_json,
            created_at_ms=created_at_ms,
        )

    def list_memory_export_artifacts(self) -> list[MemoryExportArtifact]:
        artifacts: list[MemoryExportArtifact] = []
        profile_artifacts = (
            (
                "user_memory_markdown",
                self.paths.user_memory_path,
                "text/markdown",
            ),
            (
                "cross_session_memory_markdown",
                self.paths.cross_session_memory_path,
                "text/markdown",
            ),
        )
        for artifact_kind, artifact_path, content_type in profile_artifacts:
            if not artifact_path.exists():
                continue
            artifacts.append(
                MemoryExportArtifact(
                    artifact_id=None,
                    session_id=None,
                    artifact_kind=artifact_kind,
                    relative_path=str(artifact_path.relative_to(self.paths.data_root)),
                    content_type=content_type,
                    created_at_ms=None,
                    read_bytes=lambda artifact_path=artifact_path: artifact_path.read_bytes(),
                )
            )

        if self.paths.session_root.exists():
            session_dirs = sorted(
                [path for path in self.paths.session_root.iterdir() if path.is_dir()],
                key=lambda item: item.name,
            )
        else:
            session_dirs = []

        for session_dir in session_dirs:
            self._append_session_export_artifact(
                artifacts=artifacts,
                session_dir=session_dir,
                file_name="SHORT_TERM.md",
                artifact_kind="short_term_memory_markdown",
                content_type="text/markdown",
            )
            self._append_session_export_artifact(
                artifacts=artifacts,
                session_dir=session_dir,
                file_name="LONG_TERM.md",
                artifact_kind="session_memory_markdown",
                content_type="text/markdown",
            )
            self._append_session_export_artifact(
                artifacts=artifacts,
                session_dir=session_dir,
                file_name="MEMORY_CANDIDATES.ndjson",
                artifact_kind="memory_candidate_log",
                content_type="application/x-ndjson",
            )
            self._append_session_export_artifact(
                artifacts=artifacts,
                session_dir=session_dir,
                file_name="EVENTS.ndjson",
                artifact_kind="vision_event_log",
                content_type="application/x-ndjson",
            )
        self._append_memory_v2_export_artifacts(artifacts=artifacts)
        return artifacts

    def _append_session_export_artifact(
        self,
        *,
        artifacts: list[MemoryExportArtifact],
        session_dir: Path,
        file_name: str,
        artifact_kind: str,
        content_type: str,
    ) -> None:
        path = session_dir / file_name
        if not path.exists():
            return
        artifacts.append(
            MemoryExportArtifact(
                artifact_id=None,
                session_id=session_dir.name,
                artifact_kind=artifact_kind,
                relative_path=str(path.relative_to(self.paths.data_root)),
                content_type=content_type,
                created_at_ms=None,
                read_bytes=lambda path=path: path.read_bytes(),
            )
        )

    def _append_memory_v2_export_artifacts(
        self,
        *,
        artifacts: list[MemoryExportArtifact],
    ) -> None:
        memory_v2_root = self.paths.data_root / MEMORY_V2_ROOT
        if not memory_v2_root.exists():
            return
        for path in sorted(p for p in memory_v2_root.rglob("*") if p.is_file()):
            relative_path = path.relative_to(self.paths.data_root)
            session_id = None
            artifact_kind = "memory_v2_artifact"
            content_type = "application/json"
            suffix = path.suffix.lower()
            if suffix == ".ndjson":
                content_type = "application/x-ndjson"
            if suffix == ".md":
                content_type = "text/markdown"
            parts = relative_path.parts
            if len(parts) >= 5 and parts[:3] == ("memory", "v2", "sessions"):
                session_id = parts[3]
            if "items" in parts:
                artifact_kind = "memory_v2_item"
            elif "evidence" in parts:
                artifact_kind = "memory_v2_evidence"
            elif path.name == "candidates.ndjson":
                artifact_kind = "memory_v2_candidate_log"
            elif path.name == "observations.ndjson":
                artifact_kind = "memory_v2_observation_log"
            elif path.name == "retrieval.json":
                artifact_kind = "memory_v2_retrieval_index"
            elif path.name == "maintenance_state.json":
                artifact_kind = "memory_v2_maintenance_state"
            artifacts.append(
                MemoryExportArtifact(
                    artifact_id=None,
                    session_id=session_id,
                    artifact_kind=artifact_kind,
                    relative_path=str(relative_path),
                    content_type=content_type,
                    created_at_ms=None,
                    read_bytes=lambda path=path: path.read_bytes(),
                )
            )
