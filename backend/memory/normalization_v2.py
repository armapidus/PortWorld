from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from typing import Any, Mapping, TypeVar

from backend.memory.normalize import coerce_optional_int, normalize_string, normalize_string_list
from backend.memory.types_v2 import (
    MEMORY_CANDIDATE_STATUSES,
    MEMORY_EVIDENCE_KINDS,
    MEMORY_ITEM_CLASSES,
    MEMORY_ITEM_SCOPES,
    MEMORY_ITEM_STATUSES,
    MaintenanceState,
    MemoryCandidateV2,
    MemoryEvidence,
    MemoryItem,
    RetrievalIndexEntry,
    RetrievalIndexState,
    SessionObservation,
)

_TypeT = TypeVar("_TypeT", MemoryItem, MemoryEvidence, MemoryCandidateV2, SessionObservation)


def normalize_score(value: object, *, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed < 0.0:
        return 0.0
    if parsed > 1.0:
        return 1.0
    return parsed


def normalize_timestamp_ms(value: object) -> int | None:
    parsed = coerce_optional_int(value)
    if parsed is None or parsed < 0:
        return None
    return parsed


def normalize_tags(value: object) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in normalize_string_list(value):
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(lowered)
    return tuple(normalized)


def normalize_string_tuple(value: object, *, lowercase: bool = False) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in normalize_string_list(value):
        candidate = item.lower() if lowercase else item
        dedupe_key = candidate.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(candidate)
    return tuple(normalized)


def normalize_json_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    try:
        rendered = json.dumps(value, ensure_ascii=True, sort_keys=True)
        payload = json.loads(rendered)
    except (TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def normalize_semantic_key(value: object) -> str:
    raw = normalize_string(value).lower()
    if not raw:
        return ""
    components: list[str] = []
    current: list[str] = []
    for char in raw:
        if char.isalnum():
            current.append(char)
            continue
        if current:
            components.append("".join(current))
            current = []
    if current:
        components.append("".join(current))
    return "-".join(components)


def build_stable_hash(namespace: str, *parts: object) -> str:
    joined = "||".join([namespace, *(normalize_string(part) for part in parts)])
    return sha256(joined.encode("utf-8")).hexdigest()


def build_memory_fingerprint(
    *,
    memory_class: object,
    scope: object,
    subject_key: object,
    value_key: object,
) -> str:
    return build_stable_hash(
        "memory_fingerprint",
        normalize_semantic_key(memory_class),
        normalize_semantic_key(scope),
        normalize_semantic_key(subject_key),
        normalize_semantic_key(value_key),
    )


def build_memory_item_id(*, fingerprint: object) -> str:
    return build_stable_hash("memory_item", fingerprint)


def build_memory_evidence_id(
    *,
    evidence_kind: object,
    session_id: object,
    source_ref: object,
    captured_at_ms: object,
    excerpt: object,
) -> str:
    return build_stable_hash(
        "memory_evidence",
        evidence_kind,
        session_id,
        source_ref,
        captured_at_ms,
        excerpt,
    )


def build_memory_candidate_id(
    *,
    session_id: object,
    scope: object,
    fact: object,
    captured_at_ms: object,
) -> str:
    return build_stable_hash("memory_candidate", session_id, scope, fact, captured_at_ms)


def build_session_observation_id(*, session_id: object, frame_id: object) -> str:
    return build_stable_hash("session_observation", session_id, frame_id)


def normalize_memory_item(item: MemoryItem) -> MemoryItem:
    memory_class = normalize_string(item.memory_class).lower()
    scope = normalize_string(item.scope).lower()
    status = normalize_string(item.status).lower() or "candidate"
    subject_key = normalize_semantic_key(item.subject_key or item.summary)
    value_key = normalize_semantic_key(item.value_key or item.structured_value)
    fingerprint = item.fingerprint or build_memory_fingerprint(
        memory_class=memory_class,
        scope=scope,
        subject_key=subject_key,
        value_key=value_key,
    )
    item_id = normalize_string(item.item_id) or build_memory_item_id(fingerprint=fingerprint)
    normalized = replace(
        item,
        item_id=item_id,
        memory_class=_validated_enum(memory_class, MEMORY_ITEM_CLASSES, fallback="recent_fact"),
        scope=_validated_enum(scope, MEMORY_ITEM_SCOPES, fallback="session"),
        session_id=_normalize_optional_text(item.session_id),
        status=_validated_enum(status, MEMORY_ITEM_STATUSES, fallback="candidate"),
        summary=normalize_string(item.summary),
        structured_value=normalize_json_mapping(item.structured_value),
        confidence=normalize_score(item.confidence),
        relevance=normalize_score(item.relevance),
        maturity=normalize_score(item.maturity),
        fingerprint=fingerprint,
        subject_key=subject_key,
        value_key=value_key,
        first_seen_at_ms=normalize_timestamp_ms(item.first_seen_at_ms),
        last_seen_at_ms=normalize_timestamp_ms(item.last_seen_at_ms),
        last_promoted_at_ms=normalize_timestamp_ms(item.last_promoted_at_ms),
        source_kinds=normalize_string_tuple(item.source_kinds, lowercase=True),
        evidence_ids=normalize_string_tuple(item.evidence_ids),
        relation_ids=normalize_string_tuple(item.relation_ids),
        tags=normalize_tags(item.tags),
        correction_notes=normalize_string_tuple(item.correction_notes),
        metadata=normalize_json_mapping(item.metadata),
    )
    return normalized


def normalize_memory_evidence(evidence: MemoryEvidence) -> MemoryEvidence:
    evidence_kind = normalize_string(evidence.evidence_kind).lower()
    captured_at_ms = normalize_timestamp_ms(evidence.captured_at_ms) or 0
    evidence_id = normalize_string(evidence.evidence_id) or build_memory_evidence_id(
        evidence_kind=evidence_kind,
        session_id=evidence.session_id,
        source_ref=evidence.source_ref,
        captured_at_ms=captured_at_ms,
        excerpt=evidence.excerpt,
    )
    return replace(
        evidence,
        evidence_id=evidence_id,
        evidence_kind=_validated_enum(
            evidence_kind,
            MEMORY_EVIDENCE_KINDS,
            fallback="conversation",
        ),
        session_id=_normalize_optional_text(evidence.session_id),
        source_ref=normalize_string(evidence.source_ref),
        excerpt=normalize_string(evidence.excerpt),
        captured_at_ms=captured_at_ms,
        confidence=normalize_score(evidence.confidence),
        item_id=_normalize_optional_text(evidence.item_id),
        observation_id=_normalize_optional_text(evidence.observation_id),
        candidate_id=_normalize_optional_text(evidence.candidate_id),
        tags=normalize_tags(evidence.tags),
        metadata=normalize_json_mapping(evidence.metadata),
    )


def normalize_memory_candidate(candidate: MemoryCandidateV2) -> MemoryCandidateV2:
    session_id = normalize_string(candidate.session_id)
    scope = normalize_string(candidate.scope).lower()
    captured_at_ms = normalize_timestamp_ms(candidate.captured_at_ms)
    candidate_id = normalize_string(candidate.candidate_id) or build_memory_candidate_id(
        session_id=session_id,
        scope=scope,
        fact=candidate.fact,
        captured_at_ms=captured_at_ms or 0,
    )
    summary = normalize_string(candidate.summary) or normalize_string(candidate.fact)
    return replace(
        candidate,
        candidate_id=candidate_id,
        session_id=session_id,
        scope=_validated_enum(scope, MEMORY_ITEM_SCOPES, fallback="session"),
        memory_class=_validated_enum(
            normalize_string(candidate.memory_class).lower(),
            MEMORY_ITEM_CLASSES,
            fallback=_infer_memory_class(candidate.section_hint),
        ),
        section_hint=normalize_semantic_key(candidate.section_hint),
        fact=normalize_string(candidate.fact),
        summary=summary,
        stability=normalize_string(candidate.stability).lower() or "stable",
        status=_validated_enum(
            normalize_string(candidate.status).lower(),
            MEMORY_CANDIDATE_STATUSES,
            fallback="pending",
        ),
        confidence=normalize_score(candidate.confidence),
        relevance=normalize_score(candidate.relevance),
        fingerprint=normalize_string(candidate.fingerprint)
        or build_memory_fingerprint(
            memory_class=candidate.memory_class or _infer_memory_class(candidate.section_hint),
            scope=scope,
            subject_key=summary,
            value_key=candidate.fact,
        ),
        evidence_ids=normalize_string_tuple(candidate.evidence_ids),
        source=normalize_string(candidate.source),
        captured_at_ms=captured_at_ms,
        tags=normalize_tags(candidate.tags),
        metadata=normalize_json_mapping(candidate.metadata),
    )


def normalize_session_observation(observation: SessionObservation) -> SessionObservation:
    session_id = normalize_string(observation.session_id)
    frame_id = normalize_string(observation.frame_id)
    observation_id = normalize_string(observation.observation_id) or build_session_observation_id(
        session_id=session_id,
        frame_id=frame_id,
    )
    scene_summary = normalize_string(observation.scene_summary)
    return replace(
        observation,
        observation_id=observation_id,
        session_id=session_id,
        frame_id=frame_id,
        capture_ts_ms=normalize_timestamp_ms(observation.capture_ts_ms) or 0,
        analyzed_at_ms=normalize_timestamp_ms(observation.analyzed_at_ms),
        provider=normalize_string(observation.provider),
        model=normalize_string(observation.model),
        scene_summary=scene_summary,
        user_activity_guess=normalize_string(observation.user_activity_guess),
        entities=normalize_string_tuple(observation.entities),
        actions=normalize_string_tuple(observation.actions),
        visible_text=normalize_string_tuple(observation.visible_text),
        documents_seen=normalize_string_tuple(observation.documents_seen),
        salient_change=bool(observation.salient_change),
        confidence=normalize_score(observation.confidence),
        fingerprint=normalize_string(observation.fingerprint)
        or build_memory_fingerprint(
            memory_class="recent_fact",
            scope="session",
            subject_key=frame_id,
            value_key=scene_summary,
        ),
        evidence_ids=normalize_string_tuple(observation.evidence_ids),
        tags=normalize_tags(observation.tags),
        metadata=normalize_json_mapping(observation.metadata),
    )


def normalize_retrieval_index_state(state: RetrievalIndexState | None) -> RetrievalIndexState:
    if state is None:
        return RetrievalIndexState(updated_at_ms=None, entries=(), metadata={})
    entries: list[RetrievalIndexEntry] = []
    for entry in state.entries:
        entries.append(
            RetrievalIndexEntry(
                item_id=normalize_string(entry.item_id),
                score=normalize_score(entry.score),
                reasons=normalize_string_tuple(entry.reasons),
                tags=normalize_tags(entry.tags),
                updated_at_ms=normalize_timestamp_ms(entry.updated_at_ms),
            )
        )
    return RetrievalIndexState(
        updated_at_ms=normalize_timestamp_ms(state.updated_at_ms),
        entries=tuple(entries),
        metadata=normalize_json_mapping(state.metadata),
    )


def normalize_maintenance_state(state: MaintenanceState | None) -> MaintenanceState:
    if state is None:
        return MaintenanceState(updated_at_ms=None, metadata={})
    return MaintenanceState(
        updated_at_ms=normalize_timestamp_ms(state.updated_at_ms),
        last_candidate_consolidation_at_ms=normalize_timestamp_ms(
            state.last_candidate_consolidation_at_ms
        ),
        last_observation_promotion_at_ms=normalize_timestamp_ms(
            state.last_observation_promotion_at_ms
        ),
        last_dedup_at_ms=normalize_timestamp_ms(state.last_dedup_at_ms),
        metadata=normalize_json_mapping(state.metadata),
    )


def render_memory_item(item: MemoryItem) -> dict[str, Any]:
    normalized = normalize_memory_item(item)
    return {
        "item_id": normalized.item_id,
        "memory_class": normalized.memory_class,
        "scope": normalized.scope,
        "session_id": normalized.session_id,
        "status": normalized.status,
        "summary": normalized.summary,
        "structured_value": normalized.structured_value,
        "confidence": normalized.confidence,
        "relevance": normalized.relevance,
        "maturity": normalized.maturity,
        "fingerprint": normalized.fingerprint,
        "subject_key": normalized.subject_key,
        "value_key": normalized.value_key,
        "first_seen_at_ms": normalized.first_seen_at_ms,
        "last_seen_at_ms": normalized.last_seen_at_ms,
        "last_promoted_at_ms": normalized.last_promoted_at_ms,
        "source_kinds": list(normalized.source_kinds),
        "evidence_ids": list(normalized.evidence_ids),
        "relation_ids": list(normalized.relation_ids),
        "tags": list(normalized.tags),
        "correction_notes": list(normalized.correction_notes),
        "metadata": normalized.metadata,
    }


def parse_memory_item(payload: Mapping[str, object]) -> MemoryItem:
    return normalize_memory_item(
        MemoryItem(
            item_id=normalize_string(payload.get("item_id")),
            memory_class=normalize_string(payload.get("memory_class")),
            scope=normalize_string(payload.get("scope")),
            session_id=_normalize_optional_text(payload.get("session_id")),
            status=normalize_string(payload.get("status")),
            summary=normalize_string(payload.get("summary")),
            structured_value=normalize_json_mapping(payload.get("structured_value")),
            confidence=payload.get("confidence") or 0.0,
            relevance=payload.get("relevance") or 0.0,
            maturity=payload.get("maturity") or 0.0,
            fingerprint=normalize_string(payload.get("fingerprint")),
            subject_key=normalize_string(payload.get("subject_key")),
            value_key=normalize_string(payload.get("value_key")),
            first_seen_at_ms=normalize_timestamp_ms(payload.get("first_seen_at_ms")),
            last_seen_at_ms=normalize_timestamp_ms(payload.get("last_seen_at_ms")),
            last_promoted_at_ms=normalize_timestamp_ms(payload.get("last_promoted_at_ms")),
            source_kinds=normalize_string_tuple(payload.get("source_kinds"), lowercase=True),
            evidence_ids=normalize_string_tuple(payload.get("evidence_ids")),
            relation_ids=normalize_string_tuple(payload.get("relation_ids")),
            tags=normalize_tags(payload.get("tags")),
            correction_notes=normalize_string_tuple(payload.get("correction_notes")),
            metadata=normalize_json_mapping(payload.get("metadata")),
        )
    )


def render_memory_evidence(evidence: MemoryEvidence) -> dict[str, Any]:
    normalized = normalize_memory_evidence(evidence)
    return {
        "evidence_id": normalized.evidence_id,
        "evidence_kind": normalized.evidence_kind,
        "session_id": normalized.session_id,
        "source_ref": normalized.source_ref,
        "excerpt": normalized.excerpt,
        "captured_at_ms": normalized.captured_at_ms,
        "confidence": normalized.confidence,
        "item_id": normalized.item_id,
        "observation_id": normalized.observation_id,
        "candidate_id": normalized.candidate_id,
        "tags": list(normalized.tags),
        "metadata": normalized.metadata,
    }


def parse_memory_evidence(payload: Mapping[str, object]) -> MemoryEvidence:
    return normalize_memory_evidence(
        MemoryEvidence(
            evidence_id=normalize_string(payload.get("evidence_id")),
            evidence_kind=normalize_string(payload.get("evidence_kind")),
            session_id=_normalize_optional_text(payload.get("session_id")),
            source_ref=normalize_string(payload.get("source_ref")),
            excerpt=normalize_string(payload.get("excerpt")),
            captured_at_ms=normalize_timestamp_ms(payload.get("captured_at_ms")) or 0,
            confidence=payload.get("confidence") or 0.0,
            item_id=_normalize_optional_text(payload.get("item_id")),
            observation_id=_normalize_optional_text(payload.get("observation_id")),
            candidate_id=_normalize_optional_text(payload.get("candidate_id")),
            tags=normalize_tags(payload.get("tags")),
            metadata=normalize_json_mapping(payload.get("metadata")),
        )
    )


def render_memory_candidate(candidate: MemoryCandidateV2) -> dict[str, Any]:
    normalized = normalize_memory_candidate(candidate)
    return {
        "candidate_id": normalized.candidate_id,
        "session_id": normalized.session_id,
        "scope": normalized.scope,
        "memory_class": normalized.memory_class,
        "section_hint": normalized.section_hint,
        "fact": normalized.fact,
        "summary": normalized.summary,
        "stability": normalized.stability,
        "status": normalized.status,
        "confidence": normalized.confidence,
        "relevance": normalized.relevance,
        "fingerprint": normalized.fingerprint,
        "evidence_ids": list(normalized.evidence_ids),
        "source": normalized.source,
        "captured_at_ms": normalized.captured_at_ms,
        "tags": list(normalized.tags),
        "metadata": normalized.metadata,
    }


def parse_memory_candidate(payload: Mapping[str, object]) -> MemoryCandidateV2:
    return normalize_memory_candidate(
        MemoryCandidateV2(
            candidate_id=normalize_string(payload.get("candidate_id")),
            session_id=normalize_string(payload.get("session_id")),
            scope=normalize_string(payload.get("scope")),
            memory_class=normalize_string(payload.get("memory_class")),
            section_hint=normalize_string(payload.get("section_hint")),
            fact=normalize_string(payload.get("fact")),
            summary=normalize_string(payload.get("summary")),
            stability=normalize_string(payload.get("stability")),
            status=normalize_string(payload.get("status")),
            confidence=payload.get("confidence") or 0.0,
            relevance=payload.get("relevance") or 0.0,
            fingerprint=normalize_string(payload.get("fingerprint")),
            evidence_ids=normalize_string_tuple(payload.get("evidence_ids")),
            source=normalize_string(payload.get("source")),
            captured_at_ms=normalize_timestamp_ms(payload.get("captured_at_ms")),
            tags=normalize_tags(payload.get("tags")),
            metadata=normalize_json_mapping(payload.get("metadata")),
        )
    )


def render_session_observation(observation: SessionObservation) -> dict[str, Any]:
    normalized = normalize_session_observation(observation)
    return {
        "observation_id": normalized.observation_id,
        "session_id": normalized.session_id,
        "frame_id": normalized.frame_id,
        "capture_ts_ms": normalized.capture_ts_ms,
        "analyzed_at_ms": normalized.analyzed_at_ms,
        "provider": normalized.provider,
        "model": normalized.model,
        "scene_summary": normalized.scene_summary,
        "user_activity_guess": normalized.user_activity_guess,
        "entities": list(normalized.entities),
        "actions": list(normalized.actions),
        "visible_text": list(normalized.visible_text),
        "documents_seen": list(normalized.documents_seen),
        "salient_change": normalized.salient_change,
        "confidence": normalized.confidence,
        "fingerprint": normalized.fingerprint,
        "evidence_ids": list(normalized.evidence_ids),
        "tags": list(normalized.tags),
        "metadata": normalized.metadata,
    }


def parse_session_observation(payload: Mapping[str, object]) -> SessionObservation:
    return normalize_session_observation(
        SessionObservation(
            observation_id=normalize_string(payload.get("observation_id")),
            session_id=normalize_string(payload.get("session_id")),
            frame_id=normalize_string(payload.get("frame_id")),
            capture_ts_ms=normalize_timestamp_ms(payload.get("capture_ts_ms")) or 0,
            analyzed_at_ms=normalize_timestamp_ms(payload.get("analyzed_at_ms")),
            provider=normalize_string(payload.get("provider")),
            model=normalize_string(payload.get("model")),
            scene_summary=normalize_string(payload.get("scene_summary")),
            user_activity_guess=normalize_string(payload.get("user_activity_guess")),
            entities=normalize_string_tuple(payload.get("entities")),
            actions=normalize_string_tuple(payload.get("actions")),
            visible_text=normalize_string_tuple(payload.get("visible_text")),
            documents_seen=normalize_string_tuple(payload.get("documents_seen")),
            salient_change=bool(payload.get("salient_change")),
            confidence=payload.get("confidence") or 0.0,
            fingerprint=normalize_string(payload.get("fingerprint")),
            evidence_ids=normalize_string_tuple(payload.get("evidence_ids")),
            tags=normalize_tags(payload.get("tags")),
            metadata=normalize_json_mapping(payload.get("metadata")),
        )
    )


def render_retrieval_index_state(state: RetrievalIndexState | None) -> dict[str, Any]:
    normalized = normalize_retrieval_index_state(state)
    return {
        "updated_at_ms": normalized.updated_at_ms,
        "entries": [
            {
                "item_id": entry.item_id,
                "score": entry.score,
                "reasons": list(entry.reasons),
                "tags": list(entry.tags),
                "updated_at_ms": entry.updated_at_ms,
            }
            for entry in normalized.entries
        ],
        "metadata": normalized.metadata,
    }


def parse_retrieval_index_state(payload: Mapping[str, object] | None) -> RetrievalIndexState:
    if not isinstance(payload, Mapping):
        return normalize_retrieval_index_state(None)
    entries_raw = payload.get("entries")
    entries: list[RetrievalIndexEntry] = []
    if isinstance(entries_raw, list):
        for item in entries_raw:
            if not isinstance(item, Mapping):
                continue
            entries.append(
                RetrievalIndexEntry(
                    item_id=normalize_string(item.get("item_id")),
                    score=normalize_score(item.get("score")),
                    reasons=normalize_string_tuple(item.get("reasons")),
                    tags=normalize_tags(item.get("tags")),
                    updated_at_ms=normalize_timestamp_ms(item.get("updated_at_ms")),
                )
            )
    return normalize_retrieval_index_state(
        RetrievalIndexState(
            updated_at_ms=normalize_timestamp_ms(payload.get("updated_at_ms")),
            entries=tuple(entries),
            metadata=normalize_json_mapping(payload.get("metadata")),
        )
    )


def render_maintenance_state(state: MaintenanceState | None) -> dict[str, Any]:
    normalized = normalize_maintenance_state(state)
    return {
        "updated_at_ms": normalized.updated_at_ms,
        "last_candidate_consolidation_at_ms": normalized.last_candidate_consolidation_at_ms,
        "last_observation_promotion_at_ms": normalized.last_observation_promotion_at_ms,
        "last_dedup_at_ms": normalized.last_dedup_at_ms,
        "metadata": normalized.metadata,
    }


def parse_maintenance_state(payload: Mapping[str, object] | None) -> MaintenanceState:
    if not isinstance(payload, Mapping):
        return normalize_maintenance_state(None)
    return normalize_maintenance_state(
        MaintenanceState(
            updated_at_ms=normalize_timestamp_ms(payload.get("updated_at_ms")),
            last_candidate_consolidation_at_ms=normalize_timestamp_ms(
                payload.get("last_candidate_consolidation_at_ms")
            ),
            last_observation_promotion_at_ms=normalize_timestamp_ms(
                payload.get("last_observation_promotion_at_ms")
            ),
            last_dedup_at_ms=normalize_timestamp_ms(payload.get("last_dedup_at_ms")),
            metadata=normalize_json_mapping(payload.get("metadata")),
        )
    )


def render_ndjson(payloads: list[dict[str, Any]]) -> str:
    if not payloads:
        return ""
    return "".join(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n" for payload in payloads)


def _validated_enum(value: str, allowed: frozenset[str], *, fallback: str) -> str:
    return value if value in allowed else fallback


def _normalize_optional_text(value: object) -> str | None:
    normalized = normalize_string(value)
    return normalized or None


def _infer_memory_class(section_hint: object) -> str:
    normalized = normalize_semantic_key(section_hint)
    mapping = {
        "identity": "identity",
        "preferences": "preference",
        "stable-facts": "recent_fact",
        "ongoing-threads": "ongoing_thread",
        "follow-ups": "ongoing_thread",
        "recent-facts": "recent_fact",
    }
    return mapping.get(normalized, "recent_fact")
