from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.core.storage import now_ms
from backend.memory.indexing_v2 import live_usefulness_score, sort_memory_items_for_live_use
from backend.memory.repository_v2 import MemoryRepositoryV2
from backend.memory.types_v2 import MaintenanceState, MemoryEvidence, MemoryItem, RetrievalIndexState


def _truncate(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."


@dataclass(frozen=True, slots=True)
class LiveMemoryBundleRequest:
    session_id: str | None
    limit: int = 8
    evidence_limit_per_item: int = 3


@dataclass(frozen=True, slots=True)
class LiveMemoryBundleEntry:
    item: MemoryItem
    score: float
    ranking: dict[str, object]
    evidence: tuple[MemoryEvidence, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "item": {
                "item_id": self.item.item_id,
                "memory_class": self.item.memory_class,
                "scope": self.item.scope,
                "session_id": self.item.session_id,
                "status": self.item.status,
                "summary": self.item.summary,
                "structured_value": dict(self.item.structured_value),
                "confidence": self.item.confidence,
                "relevance": self.item.relevance,
                "maturity": self.item.maturity,
                "tags": list(self.item.tags),
                "last_seen_at_ms": self.item.last_seen_at_ms,
                "last_promoted_at_ms": self.item.last_promoted_at_ms,
            },
            "score": self.score,
            "ranking": dict(self.ranking),
            "evidence_summary": {
                "count": len(self.evidence),
                "latest_captured_at_ms": max((record.captured_at_ms for record in self.evidence), default=None),
                "records": [
                    {
                        "evidence_id": record.evidence_id,
                        "evidence_kind": record.evidence_kind,
                        "excerpt": _truncate(record.excerpt, max_chars=180),
                        "confidence": record.confidence,
                        "captured_at_ms": record.captured_at_ms,
                        "source_ref": record.source_ref,
                    }
                    for record in self.evidence
                ],
            },
        }


@dataclass(frozen=True, slots=True)
class LiveMemoryBundle:
    session_id: str | None
    generated_at_ms: int
    entries: tuple[LiveMemoryBundleEntry, ...]
    retrieval_index_state: RetrievalIndexState
    maintenance_state: MaintenanceState

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "generated_at_ms": self.generated_at_ms,
            "count": len(self.entries),
            "items": [entry.to_dict() for entry in self.entries],
            "retrieval_index": {
                "updated_at_ms": self.retrieval_index_state.updated_at_ms,
                "entry_count": len(self.retrieval_index_state.entries),
                "metadata": dict(self.retrieval_index_state.metadata),
            },
            "maintenance_state": {
                "updated_at_ms": self.maintenance_state.updated_at_ms,
                "last_candidate_consolidation_at_ms": self.maintenance_state.last_candidate_consolidation_at_ms,
                "last_observation_promotion_at_ms": self.maintenance_state.last_observation_promotion_at_ms,
                "last_dedup_at_ms": self.maintenance_state.last_dedup_at_ms,
                "metadata": dict(self.maintenance_state.metadata),
            },
        }


class MemoryRetrievalServiceV2:
    def __init__(self, *, repository: MemoryRepositoryV2) -> None:
        self.repository = repository

    def build_live_bundle(self, *, request: LiveMemoryBundleRequest) -> LiveMemoryBundle:
        limit = max(0, request.limit)
        evidence_limit = max(0, request.evidence_limit_per_item)
        generated_at_ms = now_ms()

        retrieval_state = self.repository.read_retrieval_index_state()
        maintenance_state = self.repository.read_maintenance_state()
        indexed_scores = {
            entry.item_id: {
                "index_score": entry.score,
                "index_reasons": list(entry.reasons),
            }
            for entry in retrieval_state.entries
        }

        eligible_items = [
            item
            for item in self.repository.list_items()
            if item.status not in {"suppressed", "deleted", "archived"}
        ]
        sorted_items = sort_memory_items_for_live_use(eligible_items)

        scored_entries: list[tuple[float, MemoryItem, dict[str, object]]] = []
        for item in sorted_items:
            base_score = float(indexed_scores.get(item.item_id, {}).get("index_score", 0.0))
            fallback_score = live_usefulness_score(item, reference_time_ms=generated_at_ms)
            effective_base = base_score if base_score > 0.0 else fallback_score
            session_affinity_bonus = 0.12 if request.session_id and item.session_id == request.session_id else 0.0
            recency_bonus = self._compute_recency_bonus(item=item, reference_time_ms=generated_at_ms)
            conflict_penalty = 0.18 if item.status == "conflicted" else 0.0
            final_score = effective_base + session_affinity_bonus + recency_bonus - conflict_penalty
            scored_entries.append(
                (
                    final_score,
                    item,
                    {
                        "final_score": round(final_score, 6),
                        "index_score": round(base_score, 6),
                        "fallback_score": round(fallback_score, 6),
                        "session_affinity_bonus": round(session_affinity_bonus, 6),
                        "recency_bonus": round(recency_bonus, 6),
                        "conflict_penalty": round(conflict_penalty, 6),
                        "index_reasons": list(indexed_scores.get(item.item_id, {}).get("index_reasons", [])),
                        "confidence": item.confidence,
                        "relevance": item.relevance,
                        "maturity": item.maturity,
                        "last_seen_at_ms": item.last_seen_at_ms,
                        "status": item.status,
                    },
                )
            )

        scored_entries.sort(key=lambda row: (row[0], row[1].last_seen_at_ms or 0, row[1].item_id), reverse=True)
        selected = scored_entries[:limit] if limit else []
        entries: list[LiveMemoryBundleEntry] = []
        for score, item, ranking in selected:
            evidence = self.repository.list_item_evidence(item_id=item.item_id)
            if evidence_limit:
                evidence = evidence[:evidence_limit]
            entries.append(
                LiveMemoryBundleEntry(
                    item=item,
                    score=score,
                    ranking=ranking,
                    evidence=tuple(evidence),
                )
            )

        return LiveMemoryBundle(
            session_id=request.session_id,
            generated_at_ms=generated_at_ms,
            entries=tuple(entries),
            retrieval_index_state=retrieval_state,
            maintenance_state=maintenance_state,
        )

    @staticmethod
    def _compute_recency_bonus(*, item: MemoryItem, reference_time_ms: int) -> float:
        if item.last_seen_at_ms is None:
            return 0.0
        age_ms = max(0, reference_time_ms - item.last_seen_at_ms)
        one_day_ms = 24 * 60 * 60 * 1000
        if age_ms <= one_day_ms:
            return 0.08
        if age_ms <= (3 * one_day_ms):
            return 0.04
        return 0.0


def summarize_recent_maintenance(maintenance_state: MaintenanceState) -> dict[str, Any]:
    metadata = dict(maintenance_state.metadata)
    raw_results = metadata.get("last_results")
    if not isinstance(raw_results, list):
        raw_results = []
    recent_results: list[dict[str, object]] = []
    for raw in raw_results[:10]:
        if isinstance(raw, dict):
            recent_results.append(dict(raw))
    return {
        "updated_at_ms": maintenance_state.updated_at_ms,
        "last_candidate_consolidation_at_ms": maintenance_state.last_candidate_consolidation_at_ms,
        "last_observation_promotion_at_ms": maintenance_state.last_observation_promotion_at_ms,
        "last_dedup_at_ms": maintenance_state.last_dedup_at_ms,
        "last_scope": metadata.get("last_scope"),
        "last_phase": metadata.get("last_phase"),
        "last_dry_run": metadata.get("last_dry_run"),
        "last_session_ids": metadata.get("last_session_ids"),
        "last_results": recent_results,
    }


__all__ = [
    "LiveMemoryBundle",
    "LiveMemoryBundleEntry",
    "LiveMemoryBundleRequest",
    "MemoryRetrievalServiceV2",
    "summarize_recent_maintenance",
]
