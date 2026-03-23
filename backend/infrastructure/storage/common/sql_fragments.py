from __future__ import annotations

ARTIFACT_INDEX_UPSERT_SQLITE = """
INSERT INTO artifact_index(
    artifact_id,
    session_id,
    artifact_kind,
    relative_path,
    content_type,
    metadata_json,
    created_at_ms,
    updated_at_ms
)
VALUES(?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(artifact_id) DO UPDATE SET
    session_id=excluded.session_id,
    artifact_kind=excluded.artifact_kind,
    relative_path=excluded.relative_path,
    content_type=excluded.content_type,
    metadata_json=excluded.metadata_json,
    updated_at_ms=excluded.updated_at_ms
"""

ARTIFACT_INDEX_UPSERT_POSTGRES = """
INSERT INTO artifact_index(
    artifact_id,
    session_id,
    artifact_kind,
    relative_path,
    content_type,
    metadata_json,
    created_at_ms,
    updated_at_ms
)
VALUES(%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT(artifact_id) DO UPDATE SET
    session_id=EXCLUDED.session_id,
    artifact_kind=EXCLUDED.artifact_kind,
    relative_path=EXCLUDED.relative_path,
    content_type=EXCLUDED.content_type,
    metadata_json=EXCLUDED.metadata_json,
    updated_at_ms=EXCLUDED.updated_at_ms
"""

VISION_FRAME_INDEX_UPSERT_SQLITE = """
INSERT INTO vision_frame_index(
    session_id,
    frame_id,
    capture_ts_ms,
    ingest_ts_ms,
    width,
    height,
    processing_status,
    gate_status,
    gate_reason,
    phash,
    provider,
    model,
    analyzed_at_ms,
    next_retry_at_ms,
    attempt_count,
    error_code,
    error_details_json,
    summary_snippet,
    routing_status,
    routing_reason,
    routing_score,
    routing_metadata_json
)
VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(session_id, frame_id) DO UPDATE SET
    capture_ts_ms=excluded.capture_ts_ms,
    ingest_ts_ms=excluded.ingest_ts_ms,
    width=excluded.width,
    height=excluded.height,
    processing_status=excluded.processing_status,
    gate_status=excluded.gate_status,
    gate_reason=excluded.gate_reason,
    phash=excluded.phash,
    provider=excluded.provider,
    model=excluded.model,
    analyzed_at_ms=excluded.analyzed_at_ms,
    next_retry_at_ms=excluded.next_retry_at_ms,
    attempt_count=excluded.attempt_count,
    error_code=excluded.error_code,
    error_details_json=excluded.error_details_json,
    summary_snippet=excluded.summary_snippet,
    routing_status=excluded.routing_status,
    routing_reason=excluded.routing_reason,
    routing_score=excluded.routing_score,
    routing_metadata_json=excluded.routing_metadata_json
"""

VISION_FRAME_INDEX_UPSERT_POSTGRES = """
INSERT INTO vision_frame_index(
    session_id,
    frame_id,
    capture_ts_ms,
    ingest_ts_ms,
    width,
    height,
    processing_status,
    gate_status,
    gate_reason,
    phash,
    provider,
    model,
    analyzed_at_ms,
    next_retry_at_ms,
    attempt_count,
    error_code,
    error_details_json,
    summary_snippet,
    routing_status,
    routing_reason,
    routing_score,
    routing_metadata_json
)
VALUES(
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
)
ON CONFLICT(session_id, frame_id) DO UPDATE SET
    capture_ts_ms=EXCLUDED.capture_ts_ms,
    ingest_ts_ms=EXCLUDED.ingest_ts_ms,
    width=EXCLUDED.width,
    height=EXCLUDED.height,
    processing_status=EXCLUDED.processing_status,
    gate_status=EXCLUDED.gate_status,
    gate_reason=EXCLUDED.gate_reason,
    phash=EXCLUDED.phash,
    provider=EXCLUDED.provider,
    model=EXCLUDED.model,
    analyzed_at_ms=EXCLUDED.analyzed_at_ms,
    next_retry_at_ms=EXCLUDED.next_retry_at_ms,
    attempt_count=EXCLUDED.attempt_count,
    error_code=EXCLUDED.error_code,
    error_details_json=EXCLUDED.error_details_json,
    summary_snippet=EXCLUDED.summary_snippet,
    routing_status=EXCLUDED.routing_status,
    routing_reason=EXCLUDED.routing_reason,
    routing_score=EXCLUDED.routing_score,
    routing_metadata_json=EXCLUDED.routing_metadata_json
"""
