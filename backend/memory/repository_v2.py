from __future__ import annotations

from dataclasses import replace
from typing import Any

from backend.core.storage import BackendStorage, now_ms
from backend.memory.indexing_v2 import build_retrieval_index_state, filter_memory_items
from backend.memory.normalization_v2 import (
    normalize_memory_candidate,
    normalize_memory_evidence,
    normalize_memory_item,
    normalize_session_observation,
)
from backend.memory.types_v2 import (
    MaintenanceState,
    MemoryCandidateV2,
    MemoryEvidence,
    MemoryItem,
    RetrievalIndexState,
    SessionObservation,
)


class MemoryRepositoryV2:
    def __init__(self, *, storage: BackendStorage) -> None:
        self.storage = storage

    def upsert_item(self, *, item: MemoryItem) -> MemoryItem:
        normalized = normalize_memory_item(item)
        return self.storage.write_memory_item(item=normalized)

    def get_item(self, *, item_id: str) -> MemoryItem | None:
        return self.storage.read_memory_item(item_id=item_id)

    def list_items(
        self,
        *,
        scope: str | None = None,
        memory_class: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        session_id: str | None = None,
        limit: int | None = None,
    ) -> list[MemoryItem]:
        items = filter_memory_items(
            self.storage.list_memory_items(),
            scope=scope,
            memory_class=memory_class,
            status=status,
            tag=tag,
            session_id=session_id,
        )
        if limit is not None and limit >= 0:
            return items[:limit]
        return items

    def find_item_by_fingerprint(self, *, fingerprint: str) -> MemoryItem | None:
        normalized_fingerprint = fingerprint.strip()
        if not normalized_fingerprint:
            return None
        for item in self.storage.list_memory_items():
            if item.fingerprint == normalized_fingerprint:
                return item
        return None

    def suppress_item(
        self,
        *,
        item_id: str,
        note: str | None = None,
        updated_at_ms: int | None = None,
    ) -> MemoryItem | None:
        item = self.get_item(item_id=item_id)
        if item is None:
            return None
        notes = list(item.correction_notes)
        if note:
            notes.append(note.strip())
        updated = replace(
            item,
            status="suppressed",
            correction_notes=tuple(note for note in notes if note),
            last_seen_at_ms=updated_at_ms if updated_at_ms is not None else item.last_seen_at_ms,
        )
        return self.upsert_item(item=updated)

    def correct_item(
        self,
        *,
        item_id: str,
        summary: str | None = None,
        structured_value: dict[str, Any] | None = None,
        confidence: float | None = None,
        relevance: float | None = None,
        maturity: float | None = None,
        tags: list[str] | tuple[str, ...] | None = None,
        correction_note: str | None = None,
        session_id: str | None = None,
        status: str | None = None,
    ) -> MemoryItem | None:
        item = self.get_item(item_id=item_id)
        if item is None:
            return None
        notes = list(item.correction_notes)
        if correction_note:
            notes.append(correction_note.strip())
        updated = replace(
            item,
            session_id=session_id if session_id is not None else item.session_id,
            summary=summary if summary is not None else item.summary,
            structured_value=structured_value if structured_value is not None else item.structured_value,
            confidence=confidence if confidence is not None else item.confidence,
            relevance=relevance if relevance is not None else item.relevance,
            maturity=maturity if maturity is not None else item.maturity,
            tags=tuple(tags) if tags is not None else item.tags,
            correction_notes=tuple(note for note in notes if note),
            status=status if status is not None else item.status,
            last_seen_at_ms=now_ms(),
        )
        return self.upsert_item(item=updated)

    def delete_item(self, *, item_id: str) -> bool:
        return self.storage.delete_memory_item(item_id=item_id)

    def attach_evidence(
        self,
        *,
        item_id: str,
        evidence: MemoryEvidence,
    ) -> MemoryEvidence:
        item = self.get_item(item_id=item_id)
        if item is None:
            raise KeyError(f"Memory item not found: {item_id!r}")
        stored_evidence = self.storage.write_memory_evidence(
            evidence=normalize_memory_evidence(replace(evidence, item_id=item_id))
        )
        evidence_ids = tuple(dict.fromkeys([*item.evidence_ids, stored_evidence.evidence_id]))
        source_kinds = tuple(dict.fromkeys([*item.source_kinds, stored_evidence.evidence_kind]))
        updated_item = replace(
            item,
            evidence_ids=evidence_ids,
            source_kinds=source_kinds,
            last_seen_at_ms=max(item.last_seen_at_ms or 0, stored_evidence.captured_at_ms),
        )
        self.upsert_item(item=updated_item)
        return stored_evidence

    def list_item_evidence(self, *, item_id: str) -> list[MemoryEvidence]:
        item = self.get_item(item_id=item_id)
        if item is None:
            return []
        evidence: list[MemoryEvidence] = []
        for evidence_id in item.evidence_ids:
            record = self.storage.read_memory_evidence(evidence_id=evidence_id)
            if record is not None:
                evidence.append(record)
        evidence.sort(key=lambda record: (record.captured_at_ms, record.evidence_id), reverse=True)
        return evidence

    def create_candidate(
        self,
        *,
        session_id: str,
        candidate: MemoryCandidateV2,
    ) -> MemoryCandidateV2:
        normalized = normalize_memory_candidate(candidate)
        return self.storage.write_memory_candidate_v2(session_id=session_id, candidate=normalized)

    def list_candidates(self, *, session_id: str) -> list[MemoryCandidateV2]:
        return self.storage.read_memory_candidates_v2(session_id=session_id)

    def create_observation(
        self,
        *,
        session_id: str,
        observation: SessionObservation,
    ) -> SessionObservation:
        normalized = normalize_session_observation(observation)
        return self.storage.write_session_observation(session_id=session_id, observation=normalized)

    def list_observations(self, *, session_id: str) -> list[SessionObservation]:
        return self.storage.read_session_observations(session_id=session_id)

    def read_retrieval_index_state(self) -> RetrievalIndexState:
        return self.storage.read_retrieval_index_state()

    def rebuild_retrieval_index_state(self) -> RetrievalIndexState:
        state = build_retrieval_index_state(self.storage.list_memory_items())
        return self.storage.write_retrieval_index_state(state=state)

    def write_retrieval_index_state(self, *, state: RetrievalIndexState) -> RetrievalIndexState:
        return self.storage.write_retrieval_index_state(state=state)

    def read_maintenance_state(self) -> MaintenanceState:
        return self.storage.read_maintenance_state()

    def write_maintenance_state(self, *, state: MaintenanceState) -> MaintenanceState:
        return self.storage.write_maintenance_state(state=state)

