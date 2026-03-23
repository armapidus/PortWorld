from __future__ import annotations

from typing import Any, Mapping

from backend.infrastructure.storage.types import ArtifactRecord, VisionFrameIndexRecord


RowLike = Mapping[str, Any]


def to_vision_frame_index_record(row: RowLike) -> VisionFrameIndexRecord:
    return VisionFrameIndexRecord(
        session_id=str(row["session_id"]),
        frame_id=str(row["frame_id"]),
        capture_ts_ms=int(row["capture_ts_ms"]),
        ingest_ts_ms=int(row["ingest_ts_ms"]),
        width=int(row["width"]),
        height=int(row["height"]),
        processing_status=str(row["processing_status"]),
        gate_status=str(row["gate_status"]) if row["gate_status"] is not None else None,
        gate_reason=str(row["gate_reason"]) if row["gate_reason"] is not None else None,
        phash=str(row["phash"]) if row["phash"] is not None else None,
        provider=str(row["provider"]) if row["provider"] is not None else None,
        model=str(row["model"]) if row["model"] is not None else None,
        analyzed_at_ms=int(row["analyzed_at_ms"]) if row["analyzed_at_ms"] is not None else None,
        next_retry_at_ms=int(row["next_retry_at_ms"]) if row["next_retry_at_ms"] is not None else None,
        attempt_count=int(row["attempt_count"] or 0),
        error_code=str(row["error_code"]) if row["error_code"] is not None else None,
        error_details_json=(str(row["error_details_json"]) if row["error_details_json"] is not None else None),
        summary_snippet=(str(row["summary_snippet"]) if row["summary_snippet"] is not None else None),
        routing_status=(str(row["routing_status"]) if row["routing_status"] is not None else None),
        routing_reason=(str(row["routing_reason"]) if row["routing_reason"] is not None else None),
        routing_score=float(row["routing_score"]) if row["routing_score"] is not None else None,
        routing_metadata_json=(
            str(row["routing_metadata_json"]) if row["routing_metadata_json"] is not None else None
        ),
    )


def to_artifact_record(row: RowLike) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=str(row["artifact_id"]),
        session_id=str(row["session_id"]) if row["session_id"] is not None else None,
        artifact_kind=str(row["artifact_kind"]),
        relative_path=str(row["relative_path"]),
        content_type=str(row["content_type"]),
        metadata_json=str(row["metadata_json"]),
        created_at_ms=int(row["created_at_ms"]),
    )
