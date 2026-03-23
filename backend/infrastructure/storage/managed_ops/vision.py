from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.infrastructure.storage.types import ArtifactRecord, VisionFrameIndexRecord, VisionFrameIngestResult


def update_vision_frame_processing(
    storage: object,
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
    existing = storage.metadata_store.get_vision_frame_record(
        session_id=session_id,
        frame_id=frame_id,
    )
    if existing is None:
        raise KeyError(
            f"Vision frame record not found for session_id={session_id!r} frame_id={frame_id!r}"
        )
    record = VisionFrameIndexRecord(
        session_id=session_id,
        frame_id=frame_id,
        capture_ts_ms=existing.capture_ts_ms,
        ingest_ts_ms=existing.ingest_ts_ms,
        width=existing.width,
        height=existing.height,
        processing_status=processing_status,
        gate_status=gate_status,
        gate_reason=gate_reason,
        phash=phash,
        provider=provider,
        model=model,
        analyzed_at_ms=analyzed_at_ms,
        next_retry_at_ms=storage._resolve_next_retry_at_ms(
            next_retry_at_ms,
            existing.next_retry_at_ms,
        ),
        attempt_count=(
            int(attempt_count)
            if isinstance(attempt_count, int)
            else int(existing.attempt_count or 0)
        ),
        error_code=error_code,
        error_details_json=storage._resolve_error_details_json(
            error_details,
            error_code,
            existing.error_details_json,
        ),
        summary_snippet=summary_snippet,
        routing_status=routing_status,
        routing_reason=routing_reason,
        routing_score=routing_score,
        routing_metadata_json=(
            json.dumps(routing_metadata, ensure_ascii=True, sort_keys=True)
            if routing_metadata is not None
            else None
        ),
    )
    storage.metadata_store.upsert_vision_frame_index(record)


def get_vision_frame_record(
    storage: object,
    *,
    session_id: str,
    frame_id: str,
):
    return storage.metadata_store.get_vision_frame_record(
        session_id=session_id,
        frame_id=frame_id,
    )


def store_vision_frame_ingest(
    storage: object,
    *,
    session_id: str,
    frame_id: str,
    ts_ms: int,
    capture_ts_ms: int,
    width: int,
    height: int,
    frame_bytes: bytes,
) -> VisionFrameIngestResult:
    storage.ensure_session_storage(session_id=session_id)
    frame_relative_path, metadata_relative_path = storage._vision_frame_relative_paths(
        session_id=session_id,
        frame_id=frame_id,
    )
    ingest_ts_ms = storage.now_ms()
    artifact_metadata = {
        "session_id": session_id,
        "frame_id": frame_id,
        "ts_ms": ts_ms,
        "capture_ts_ms": capture_ts_ms,
        "width": width,
        "height": height,
        "stored_bytes": len(frame_bytes),
    }
    metadata_payload = {
        **artifact_metadata,
        "relative_path": frame_relative_path,
        "object_key": storage.object_store.resolve_location(relative_path=frame_relative_path),
    }
    ingest_record = VisionFrameIndexRecord(
        session_id=session_id,
        frame_id=frame_id,
        capture_ts_ms=capture_ts_ms,
        ingest_ts_ms=ingest_ts_ms,
        width=width,
        height=height,
        processing_status="queued",
        gate_status=None,
        gate_reason=None,
        phash=None,
        provider=None,
        model=None,
        analyzed_at_ms=None,
        next_retry_at_ms=None,
        attempt_count=0,
        error_code=None,
        error_details_json=None,
        summary_snippet=None,
        routing_status=None,
        routing_reason=None,
        routing_score=None,
        routing_metadata_json=None,
    )
    metadata_text = json.dumps(metadata_payload, ensure_ascii=True, indent=2) + "\n"
    uploaded_paths: list[str] = []
    try:
        storage.object_store.put_bytes(
            relative_path=frame_relative_path,
            content=frame_bytes,
            content_type="image/jpeg",
        )
        uploaded_paths.append(frame_relative_path)
        storage.object_store.put_text(
            relative_path=metadata_relative_path,
            content=metadata_text,
            content_type="application/json",
        )
        uploaded_paths.append(metadata_relative_path)
        storage.metadata_store.register_vision_frame_ingest(
            frame_artifact=ArtifactRecord(
                artifact_id=f"{session_id}:vision_frame_jpeg:{frame_id}",
                session_id=session_id,
                artifact_kind="vision_frame_jpeg",
                relative_path=frame_relative_path,
                content_type="image/jpeg",
                metadata_json=json.dumps(artifact_metadata, ensure_ascii=True, sort_keys=True),
                created_at_ms=ingest_ts_ms,
            ),
            metadata_artifact=ArtifactRecord(
                artifact_id=f"{session_id}:vision_frame_metadata:{frame_id}",
                session_id=session_id,
                artifact_kind="vision_frame_metadata",
                relative_path=metadata_relative_path,
                content_type="application/json",
                metadata_json=json.dumps(artifact_metadata, ensure_ascii=True, sort_keys=True),
                created_at_ms=ingest_ts_ms,
            ),
            ingest_record=ingest_record,
        )
    except Exception:
        for relative_path in reversed(uploaded_paths):
            try:
                storage.object_store.delete(relative_path=relative_path)
            except Exception:
                storage.logger.warning(
                    "Failed cleaning up partial managed ingest artifact path=%s",
                    relative_path,
                    exc_info=True,
                )
        raise

    return VisionFrameIngestResult(
        frame_path=Path(frame_relative_path),
        metadata_path=Path(metadata_relative_path),
        stored_bytes=len(frame_bytes),
    )


def delete_vision_ingest_artifacts(storage: object, *, session_id: str, frame_id: str) -> None:
    for relative_path in storage._vision_frame_relative_paths(
        session_id=session_id,
        frame_id=frame_id,
    ):
        storage.object_store.delete(relative_path=relative_path)
