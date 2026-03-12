from __future__ import annotations

import json
import shutil
from typing import Any

from backend.infrastructure.storage.types import SessionMemoryResetResult, SessionStorageResult, now_ms
from backend.memory.lifecycle import SessionMemoryResetEligibility, SessionMemoryRetentionEligibility


class SessionStorageMixin:
    def ensure_session_storage(self, *, session_id: str) -> SessionStorageResult:
        session_dir = self.session_storage_dir(session_id=session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        short_term_memory_markdown_path = session_dir / "short_term_memory.md"
        short_term_memory_json_path = session_dir / "short_term_memory.json"
        session_memory_markdown_path = session_dir / "session_memory.md"
        session_memory_json_path = session_dir / "session_memory.json"
        vision_events_log_path = session_dir / "vision_events.jsonl"
        vision_routing_events_log_path = session_dir / "vision_routing_events.jsonl"

        self._ensure_text_file(
            short_term_memory_markdown_path,
            "# Short-Term Visual Memory\n\n",
        )
        self._ensure_json_file(short_term_memory_json_path, {})
        self._ensure_text_file(
            session_memory_markdown_path,
            "# Session Memory\n\n",
        )
        self._ensure_json_file(session_memory_json_path, {})
        self._ensure_text_file(vision_events_log_path, "")
        self._ensure_text_file(vision_routing_events_log_path, "")

        artifact_metadata = {"session_id": session_id, "artifact_role": "derived_memory"}
        self.register_artifact(
            artifact_id=f"{session_id}:short_term_memory_markdown",
            session_id=session_id,
            artifact_kind="short_term_memory_markdown",
            artifact_path=short_term_memory_markdown_path,
            content_type="text/markdown",
            metadata=artifact_metadata,
        )
        self.register_artifact(
            artifact_id=f"{session_id}:short_term_memory_json",
            session_id=session_id,
            artifact_kind="short_term_memory_json",
            artifact_path=short_term_memory_json_path,
            content_type="application/json",
            metadata=artifact_metadata,
        )
        self.register_artifact(
            artifact_id=f"{session_id}:session_memory_markdown",
            session_id=session_id,
            artifact_kind="session_memory_markdown",
            artifact_path=session_memory_markdown_path,
            content_type="text/markdown",
            metadata=artifact_metadata,
        )
        self.register_artifact(
            artifact_id=f"{session_id}:session_memory_json",
            session_id=session_id,
            artifact_kind="session_memory_json",
            artifact_path=session_memory_json_path,
            content_type="application/json",
            metadata=artifact_metadata,
        )
        self.register_artifact(
            artifact_id=f"{session_id}:vision_event_log",
            session_id=session_id,
            artifact_kind="vision_event_log",
            artifact_path=vision_events_log_path,
            content_type="application/x-ndjson",
            metadata=artifact_metadata,
        )
        self.register_artifact(
            artifact_id=f"{session_id}:vision_routing_event_log",
            session_id=session_id,
            artifact_kind="vision_routing_event_log",
            artifact_path=vision_routing_events_log_path,
            content_type="application/x-ndjson",
            metadata=artifact_metadata,
        )

        return SessionStorageResult(
            session_dir=session_dir,
            short_term_memory_markdown_path=short_term_memory_markdown_path,
            short_term_memory_json_path=short_term_memory_json_path,
            session_memory_markdown_path=session_memory_markdown_path,
            session_memory_json_path=session_memory_json_path,
            vision_events_log_path=vision_events_log_path,
            vision_routing_events_log_path=vision_routing_events_log_path,
        )

    def upsert_session_status(self, *, session_id: str, status: str) -> None:
        timestamp_ms = now_ms()

        def _operation() -> None:
            with self.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO session_index(session_id, status, created_at_ms, updated_at_ms)
                    VALUES(?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        status=excluded.status,
                        updated_at_ms=excluded.updated_at_ms
                    """,
                    (session_id, status, timestamp_ms, timestamp_ms),
                )
                connection.commit()

        self._run_with_sqlite_retry(_operation)

    def append_vision_event(self, *, session_id: str, event: dict[str, Any]) -> None:
        session_storage = self.ensure_session_storage(session_id=session_id)
        with session_storage.vision_events_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")

    def append_vision_routing_event(self, *, session_id: str, event: dict[str, Any]) -> None:
        session_storage = self.ensure_session_storage(session_id=session_id)
        with session_storage.vision_routing_events_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")

    def read_vision_events(self, *, session_id: str) -> list[dict[str, Any]]:
        session_storage = self.ensure_session_storage(session_id=session_id)
        events: list[dict[str, Any]] = []
        for line in session_storage.vision_events_log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            events.append(json.loads(line))
        return events

    def read_session_memory(self, *, session_id: str) -> dict[str, Any]:
        session_storage = self.ensure_session_storage(session_id=session_id)
        return json.loads(session_storage.session_memory_json_path.read_text(encoding="utf-8"))

    def read_short_term_memory(self, *, session_id: str) -> dict[str, Any]:
        session_storage = self.ensure_session_storage(session_id=session_id)
        return json.loads(session_storage.short_term_memory_json_path.read_text(encoding="utf-8"))

    def get_session_memory_reset_eligibility(
        self,
        *,
        session_id: str,
    ) -> SessionMemoryResetEligibility:
        session_storage = self._build_session_storage_result(session_id=session_id)
        raw_vision_dir = self._session_vision_frames_dir(session_id=session_id)
        with self.connect() as connection:
            session_row = connection.execute(
                """
                SELECT status
                FROM session_index
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            artifact_count = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM artifact_index
                    WHERE session_id = ?
                    """,
                    (session_id,),
                ).fetchone()[0]
            )
            vision_frame_count = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM vision_frame_index
                    WHERE session_id = ?
                    """,
                    (session_id,),
                ).fetchone()[0]
            )

        has_persisted_memory = any(
            [
                session_row is not None,
                artifact_count > 0,
                vision_frame_count > 0,
                session_storage.session_dir.exists(),
                raw_vision_dir.exists(),
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
        return self._delete_session_memory(session_id=session_id)

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
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT session_id, status, updated_at_ms
                FROM session_index
                ORDER BY updated_at_ms ASC, session_id ASC
                """
            ).fetchall()

        results: list[SessionMemoryRetentionEligibility] = []
        for row in rows:
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
            if not eligibility.eligible:
                continue
            results.append(self._delete_session_memory(session_id=eligibility.session_id))
        return results

    def write_short_term_memory(
        self,
        *,
        session_id: str,
        payload: dict[str, Any],
        markdown_text: str,
    ) -> None:
        session_storage = self.ensure_session_storage(session_id=session_id)
        session_storage.short_term_memory_json_path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
        session_storage.short_term_memory_markdown_path.write_text(
            markdown_text,
            encoding="utf-8",
        )

    def write_session_memory(
        self,
        *,
        session_id: str,
        payload: dict[str, Any],
        markdown_text: str,
    ) -> None:
        session_storage = self.ensure_session_storage(session_id=session_id)
        session_storage.session_memory_json_path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
        session_storage.session_memory_markdown_path.write_text(
            markdown_text,
            encoding="utf-8",
        )

    def read_session_memory_status(
        self,
        *,
        session_id: str,
        recent_limit: int = 10,
    ) -> dict[str, Any]:
        session_storage = self.ensure_session_storage(session_id=session_id)
        short_term_memory = self.read_short_term_memory(session_id=session_id)
        session_memory = self.read_session_memory(session_id=session_id)
        accepted_events = self.read_vision_events(session_id=session_id)

        with self.connect() as connection:
            session_row = connection.execute(
                """
                SELECT status, created_at_ms, updated_at_ms
                FROM session_index
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            total_frames = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM vision_frame_index
                    WHERE session_id = ?
                    """,
                    (session_id,),
                ).fetchone()[0]
            )
            recent_rows = connection.execute(
                """
                SELECT *
                FROM vision_frame_index
                WHERE session_id = ?
                ORDER BY capture_ts_ms DESC
                LIMIT ?
                """,
                (session_id, max(1, recent_limit)),
            ).fetchall()

        status = (
            str(session_memory.get("status") or short_term_memory.get("status") or "")
            or ("ready" if accepted_events else "unbootstrapped")
        )
        recent_frames: list[dict[str, Any]] = []
        for row in recent_rows:
            recent_frames.append(
                {
                    "frame_id": str(row["frame_id"]),
                    "capture_ts_ms": int(row["capture_ts_ms"]),
                    "processing_status": str(row["processing_status"]),
                    "gate_status": str(row["gate_status"]) if row["gate_status"] is not None else None,
                    "gate_reason": str(row["gate_reason"]) if row["gate_reason"] is not None else None,
                    "provider": str(row["provider"]) if row["provider"] is not None else None,
                    "model": str(row["model"]) if row["model"] is not None else None,
                    "analyzed_at_ms": int(row["analyzed_at_ms"]) if row["analyzed_at_ms"] is not None else None,
                    "next_retry_at_ms": int(row["next_retry_at_ms"]) if row["next_retry_at_ms"] is not None else None,
                    "attempt_count": int(row["attempt_count"] or 0),
                    "error_code": str(row["error_code"]) if row["error_code"] is not None else None,
                    "error_details": (
                        json.loads(str(row["error_details_json"]))
                        if row["error_details_json"] is not None
                        else None
                    ),
                    "routing_status": str(row["routing_status"]) if row["routing_status"] is not None else None,
                    "routing_reason": str(row["routing_reason"]) if row["routing_reason"] is not None else None,
                    "routing_score": float(row["routing_score"]) if row["routing_score"] is not None else None,
                }
            )

        return {
            "session_id": session_id,
            "status": status,
            "session_state": str(session_row["status"]) if session_row is not None else None,
            "session_created_at_ms": int(session_row["created_at_ms"]) if session_row is not None else None,
            "session_updated_at_ms": int(session_row["updated_at_ms"]) if session_row is not None else None,
            "accepted_event_count": len(accepted_events),
            "total_frames": total_frames,
            "short_term_memory": short_term_memory,
            "session_memory": session_memory,
            "recent_frames": recent_frames,
            "session_dir_exists": session_storage.session_dir.exists(),
        }

    def _delete_session_memory(self, *, session_id: str) -> SessionMemoryResetResult:
        eligibility = self.get_session_memory_reset_eligibility(session_id=session_id)
        if eligibility.is_active:
            raise RuntimeError(f"Cannot delete active session memory for {session_id!r}")

        session_storage = self._build_session_storage_result(session_id=session_id)
        raw_vision_dir = self._session_vision_frames_dir(session_id=session_id)
        with self.connect() as connection:
            artifact_delete = connection.execute(
                """
                DELETE FROM artifact_index
                WHERE session_id = ?
                """,
                (session_id,),
            )
            vision_delete = connection.execute(
                """
                DELETE FROM vision_frame_index
                WHERE session_id = ?
                """,
                (session_id,),
            )
            session_delete = connection.execute(
                """
                DELETE FROM session_index
                WHERE session_id = ?
                """,
                (session_id,),
            )
            connection.commit()

        removed_session_dir = False
        if session_storage.session_dir.exists():
            shutil.rmtree(session_storage.session_dir)
            removed_session_dir = True

        removed_vision_frames_dir = False
        if raw_vision_dir.exists():
            shutil.rmtree(raw_vision_dir)
            removed_vision_frames_dir = True

        return SessionMemoryResetResult(
            session_id=session_id,
            deleted_artifact_rows=max(artifact_delete.rowcount, 0),
            deleted_vision_frame_rows=max(vision_delete.rowcount, 0),
            deleted_session_rows=max(session_delete.rowcount, 0),
            removed_session_dir=removed_session_dir,
            removed_vision_frames_dir=removed_vision_frames_dir,
        )
