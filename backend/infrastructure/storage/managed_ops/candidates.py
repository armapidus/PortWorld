from __future__ import annotations

import json
from typing import Any

from backend.memory.candidates import coerce_memory_candidate


def append_memory_candidate(storage: object, *, session_id: str, candidate: dict[str, Any]) -> None:
    storage.ensure_session_storage(session_id=session_id)
    storage.metadata_store.append_session_event(
        session_id=session_id,
        log_kind="memory_candidates",
        payload_json=json.dumps(candidate, ensure_ascii=True, sort_keys=True),
        created_at_ms=storage.now_ms(),
    )
    storage._append_event_to_log_artifact(
        session_id=session_id,
        log_kind="memory_candidates",
        event=candidate,
    )


def read_memory_candidates(storage: object, *, session_id: str) -> list[dict[str, Any]]:
    storage._require_session_persisted(session_id=session_id)
    payloads = storage._read_session_event_payloads(
        session_id=session_id,
        log_kind="memory_candidates",
    )
    candidates: list[dict[str, Any]] = []
    for payload in payloads:
        candidate, _ = coerce_memory_candidate(payload)
        if candidate is not None:
            candidates.append(dict(candidate))
    return candidates
