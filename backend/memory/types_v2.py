from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

MEMORY_V2_SCHEMA_VERSION: Final[str] = "1"

MEMORY_ITEM_STATUSES: Final[frozenset[str]] = frozenset(
    {"candidate", "active", "suppressed", "archived", "deleted", "conflicted"}
)
MEMORY_ITEM_SCOPES: Final[frozenset[str]] = frozenset({"user", "cross_session", "session"})
MEMORY_ITEM_CLASSES: Final[frozenset[str]] = frozenset(
    {
        "identity",
        "preference",
        "routine",
        "ongoing_thread",
        "social",
        "location",
        "important_object",
        "habit",
        "recent_fact",
    }
)
MEMORY_EVIDENCE_KINDS: Final[frozenset[str]] = frozenset(
    {
        "conversation",
        "vision_observation",
        "derived_pattern",
        "user_edit",
        "maintenance_merge",
    }
)
MEMORY_CANDIDATE_STATUSES: Final[frozenset[str]] = frozenset(
    {"pending", "promoted", "suppressed", "rejected"}
)


@dataclass(frozen=True, slots=True)
class MemoryItem:
    item_id: str
    memory_class: str
    scope: str
    session_id: str | None
    status: str
    summary: str
    structured_value: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    relevance: float = 0.0
    maturity: float = 0.0
    fingerprint: str = ""
    subject_key: str = ""
    value_key: str = ""
    first_seen_at_ms: int | None = None
    last_seen_at_ms: int | None = None
    last_promoted_at_ms: int | None = None
    source_kinds: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    relation_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    correction_notes: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MemoryEvidence:
    evidence_id: str
    evidence_kind: str
    session_id: str | None
    source_ref: str
    excerpt: str
    captured_at_ms: int
    confidence: float = 0.0
    item_id: str | None = None
    observation_id: str | None = None
    candidate_id: str | None = None
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MemoryCandidateV2:
    candidate_id: str
    session_id: str
    scope: str
    memory_class: str
    section_hint: str
    fact: str
    summary: str
    stability: str
    status: str
    confidence: float = 0.0
    relevance: float = 0.0
    fingerprint: str = ""
    evidence_ids: tuple[str, ...] = ()
    source: str = ""
    captured_at_ms: int | None = None
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SessionObservation:
    observation_id: str
    session_id: str
    frame_id: str
    capture_ts_ms: int
    analyzed_at_ms: int | None
    provider: str
    model: str
    scene_summary: str
    user_activity_guess: str
    entities: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()
    visible_text: tuple[str, ...] = ()
    documents_seen: tuple[str, ...] = ()
    salient_change: bool = False
    confidence: float = 0.0
    fingerprint: str = ""
    evidence_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievalIndexEntry:
    item_id: str
    score: float
    reasons: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    updated_at_ms: int | None = None


@dataclass(frozen=True, slots=True)
class RetrievalIndexState:
    updated_at_ms: int | None = None
    entries: tuple[RetrievalIndexEntry, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MaintenanceState:
    updated_at_ms: int | None = None
    last_candidate_consolidation_at_ms: int | None = None
    last_observation_promotion_at_ms: int | None = None
    last_dedup_at_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "MEMORY_CANDIDATE_STATUSES",
    "MEMORY_EVIDENCE_KINDS",
    "MEMORY_ITEM_CLASSES",
    "MEMORY_ITEM_SCOPES",
    "MEMORY_ITEM_STATUSES",
    "MEMORY_V2_SCHEMA_VERSION",
    "MaintenanceState",
    "MemoryCandidateV2",
    "MemoryEvidence",
    "MemoryItem",
    "RetrievalIndexEntry",
    "RetrievalIndexState",
    "SessionObservation",
]
