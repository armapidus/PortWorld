from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Final, Iterable

from backend.memory.normalization_v2 import normalize_semantic_key
from backend.memory.types_v2 import MemoryCandidateV2, MemoryItem, SessionObservation

_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "and",
        "at",
        "desk",
        "for",
        "in",
        "inside",
        "near",
        "of",
        "on",
        "outside",
        "room",
        "scene",
        "the",
        "to",
        "view",
        "with",
    }
)
_GENERIC_OBJECT_TERMS: Final[frozenset[str]] = frozenset(
    {
        "desk",
        "floor",
        "hand",
        "light",
        "person",
        "room",
        "screen",
        "table",
        "wall",
        "window",
    }
)


@dataclass(frozen=True, slots=True)
class CandidatePromotionThreshold:
    memory_class: str
    min_confidence: float
    min_relevance: float
    accepted_stabilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ObservationPromotionThreshold:
    memory_class: str
    min_observations: int
    min_average_confidence: float


@dataclass(frozen=True, slots=True)
class ObservationPromotionProposal:
    memory_class: str
    scope: str
    subject_key: str
    value_key: str
    summary: str
    confidence: float
    relevance: float
    maturity: float
    observation_ids: tuple[str, ...]
    tags: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MaintenancePolicyV2:
    candidate_thresholds: dict[str, CandidatePromotionThreshold]
    observation_thresholds: dict[str, ObservationPromotionThreshold]
    archive_relevance_threshold: float = 0.2
    archive_maturity_threshold: float = 0.35
    decay_age_ms: int = 30 * 24 * 60 * 60 * 1000
    archive_age_ms: int = 90 * 24 * 60 * 60 * 1000
    proposal_caps_by_class: dict[str, int] = field(
        default_factory=lambda: {
            "location": 1,
            "routine": 1,
            "important_object": 1,
            "ongoing_thread": 1,
        }
    )

    def candidate_threshold_for(self, memory_class: str) -> CandidatePromotionThreshold:
        return self.candidate_thresholds.get(
            memory_class,
            CandidatePromotionThreshold(
                memory_class=memory_class,
                min_confidence=0.75,
                min_relevance=0.6,
                accepted_stabilities=("stable",),
            ),
        )

    def observation_threshold_for(self, memory_class: str) -> ObservationPromotionThreshold:
        return self.observation_thresholds[memory_class]

    def should_promote_candidate(self, candidate: MemoryCandidateV2) -> bool:
        threshold = self.candidate_threshold_for(candidate.memory_class)
        return (
            candidate.confidence >= threshold.min_confidence
            and candidate.relevance >= threshold.min_relevance
            and candidate.stability in threshold.accepted_stabilities
        )

    def derive_candidate_subject_key(self, candidate: MemoryCandidateV2) -> str:
        if candidate.memory_class == "preference":
            if candidate.section_hint == "preferences":
                return "preference"
        if candidate.memory_class == "identity":
            return "identity"
        if candidate.memory_class == "ongoing_thread":
            return normalize_semantic_key(candidate.section_hint or "ongoing-thread")
        return normalize_semantic_key(candidate.section_hint or candidate.memory_class or "fact")

    def derive_candidate_value_key(self, candidate: MemoryCandidateV2) -> str:
        return normalize_semantic_key(candidate.fact or candidate.summary)

    def conflict_subject_key(self, item: MemoryItem) -> str:
        return normalize_semantic_key(item.subject_key or item.summary or item.memory_class)

    def decayed_relevance(self, item: MemoryItem, *, reference_time_ms: int) -> float:
        if item.last_seen_at_ms is None:
            return item.relevance
        age_ms = max(0, reference_time_ms - item.last_seen_at_ms)
        if age_ms < self.decay_age_ms:
            return item.relevance
        decay_steps = max(1, age_ms // self.decay_age_ms)
        decayed = item.relevance
        for _ in range(int(decay_steps)):
            decayed *= 0.9
        return max(0.0, min(decayed, 1.0))

    def should_archive_item(self, item: MemoryItem, *, reference_time_ms: int) -> bool:
        if item.status in {"suppressed", "deleted", "archived"}:
            return False
        if item.last_seen_at_ms is None:
            return False
        age_ms = max(0, reference_time_ms - item.last_seen_at_ms)
        return (
            age_ms >= self.archive_age_ms
            and self.decayed_relevance(item, reference_time_ms=reference_time_ms)
            <= self.archive_relevance_threshold
            and item.maturity <= self.archive_maturity_threshold
        )

    def is_live_bundle_candidate(self, item: MemoryItem) -> bool:
        return item.status not in {"suppressed", "deleted"} and item.status != "archived"

    def derive_observation_proposals(
        self,
        observations: Iterable[SessionObservation],
    ) -> list[ObservationPromotionProposal]:
        ordered = sorted(
            observations,
            key=lambda observation: (observation.capture_ts_ms, observation.observation_id),
        )
        proposals: list[ObservationPromotionProposal] = []
        proposals.extend(self._derive_location_proposals(ordered))
        proposals.extend(self._derive_routine_proposals(ordered))
        proposals.extend(self._derive_important_object_proposals(ordered))
        proposals.extend(self._derive_ongoing_thread_proposals(ordered))
        return self._limit_observation_proposals(proposals)

    def _derive_location_proposals(
        self,
        observations: list[SessionObservation],
    ) -> list[ObservationPromotionProposal]:
        grouped = self._group_observations(
            observations=observations,
            key_builder=self._location_key,
        )
        proposals: list[ObservationPromotionProposal] = []
        threshold = self.observation_threshold_for("location")
        for key, grouped_observations in grouped.items():
            if len(grouped_observations) < threshold.min_observations:
                continue
            average_confidence = _average_confidence(grouped_observations)
            if average_confidence < threshold.min_average_confidence:
                continue
            entities = _most_common_terms(
                term_lists=(observation.entities for observation in grouped_observations),
                limit=3,
            )
            summary = "Repeated location context: " + ", ".join(entities or [key.replace("-", " ")])
            proposals.append(
                ObservationPromotionProposal(
                    memory_class="location",
                    scope="cross_session",
                    subject_key=key,
                    value_key=key,
                    summary=summary,
                    confidence=average_confidence,
                    relevance=min(1.0, 0.55 + 0.1 * len(grouped_observations)),
                    maturity=min(1.0, 0.4 + 0.15 * len(grouped_observations)),
                    observation_ids=tuple(
                        observation.observation_id for observation in grouped_observations
                    ),
                    tags=tuple(entities),
                    metadata={"observation_count": len(grouped_observations)},
                )
            )
        return proposals

    def _derive_routine_proposals(
        self,
        observations: list[SessionObservation],
    ) -> list[ObservationPromotionProposal]:
        grouped = self._group_observations(
            observations=observations,
            key_builder=self._routine_key,
        )
        proposals: list[ObservationPromotionProposal] = []
        threshold = self.observation_threshold_for("routine")
        for key, grouped_observations in grouped.items():
            if len(grouped_observations) < threshold.min_observations:
                continue
            average_confidence = _average_confidence(grouped_observations)
            if average_confidence < threshold.min_average_confidence:
                continue
            activity = grouped_observations[0].user_activity_guess or "routine"
            proposals.append(
                ObservationPromotionProposal(
                    memory_class="routine",
                    scope="cross_session",
                    subject_key=key,
                    value_key=key,
                    summary=f"Repeated routine context around {activity}.",
                    confidence=average_confidence,
                    relevance=min(1.0, 0.5 + 0.08 * len(grouped_observations)),
                    maturity=min(1.0, 0.35 + 0.12 * len(grouped_observations)),
                    observation_ids=tuple(
                        observation.observation_id for observation in grouped_observations
                    ),
                    tags=(normalize_semantic_key(activity or "routine"),),
                    metadata={"observation_count": len(grouped_observations)},
                )
            )
        return proposals

    def _derive_important_object_proposals(
        self,
        observations: list[SessionObservation],
    ) -> list[ObservationPromotionProposal]:
        grouped: dict[str, list[SessionObservation]] = {}
        for observation in observations:
            for entity in observation.entities:
                normalized = normalize_semantic_key(entity)
                if not normalized or normalized in _GENERIC_OBJECT_TERMS:
                    continue
                grouped.setdefault(normalized, []).append(observation)
        proposals: list[ObservationPromotionProposal] = []
        threshold = self.observation_threshold_for("important_object")
        for key, grouped_observations in grouped.items():
            unique_observation_ids = {
                observation.observation_id for observation in grouped_observations
            }
            if len(unique_observation_ids) < threshold.min_observations:
                continue
            average_confidence = _average_confidence(grouped_observations)
            if average_confidence < threshold.min_average_confidence:
                continue
            proposals.append(
                ObservationPromotionProposal(
                    memory_class="important_object",
                    scope="cross_session",
                    subject_key=key,
                    value_key=key,
                    summary=f"Repeatedly seen important object: {key.replace('-', ' ')}.",
                    confidence=average_confidence,
                    relevance=min(1.0, 0.5 + 0.06 * len(unique_observation_ids)),
                    maturity=min(1.0, 0.35 + 0.1 * len(unique_observation_ids)),
                    observation_ids=tuple(sorted(unique_observation_ids)),
                    tags=(key,),
                    metadata={"observation_count": len(unique_observation_ids)},
                )
            )
        return proposals

    def _derive_ongoing_thread_proposals(
        self,
        observations: list[SessionObservation],
    ) -> list[ObservationPromotionProposal]:
        grouped: dict[str, list[SessionObservation]] = {}
        for observation in observations:
            terms = [
                *observation.documents_seen,
                *[token for token in observation.visible_text if len(token.strip()) >= 4],
            ]
            for term in terms:
                normalized = normalize_semantic_key(term)
                if not normalized or normalized in _STOPWORDS:
                    continue
                grouped.setdefault(normalized, []).append(observation)
        proposals: list[ObservationPromotionProposal] = []
        threshold = self.observation_threshold_for("ongoing_thread")
        for key, grouped_observations in grouped.items():
            unique_observation_ids = {
                observation.observation_id for observation in grouped_observations
            }
            if len(unique_observation_ids) < threshold.min_observations:
                continue
            average_confidence = _average_confidence(grouped_observations)
            if average_confidence < threshold.min_average_confidence:
                continue
            proposals.append(
                ObservationPromotionProposal(
                    memory_class="ongoing_thread",
                    scope="cross_session",
                    subject_key=key,
                    value_key=key,
                    summary=f"Repeated ongoing thread around {key.replace('-', ' ')}.",
                    confidence=average_confidence,
                    relevance=min(1.0, 0.55 + 0.08 * len(unique_observation_ids)),
                    maturity=min(1.0, 0.4 + 0.12 * len(unique_observation_ids)),
                    observation_ids=tuple(sorted(unique_observation_ids)),
                    tags=(key,),
                    metadata={"observation_count": len(unique_observation_ids)},
                )
            )
        return proposals

    def _group_observations(
        self,
        *,
        observations: list[SessionObservation],
        key_builder,
    ) -> dict[str, list[SessionObservation]]:
        grouped: dict[str, list[SessionObservation]] = {}
        for observation in observations:
            key = key_builder(observation)
            if not key:
                continue
            grouped.setdefault(key, []).append(observation)
        return grouped

    def _location_key(self, observation: SessionObservation) -> str:
        entity_terms = [
            normalize_semantic_key(entity)
            for entity in observation.entities
            if normalize_semantic_key(entity) and normalize_semantic_key(entity) not in _STOPWORDS
        ]
        if len(entity_terms) >= 2:
            return "-".join(sorted(entity_terms[:3]))
        summary_terms = _summary_terms(observation.scene_summary, limit=3)
        return "-".join(summary_terms)

    def _routine_key(self, observation: SessionObservation) -> str:
        activity = normalize_semantic_key(observation.user_activity_guess)
        entity_terms = _most_common_terms([observation.entities], limit=2)
        joined = "-".join([part for part in (activity, *entity_terms) if part])
        return joined

    def _limit_observation_proposals(
        self,
        proposals: list[ObservationPromotionProposal],
    ) -> list[ObservationPromotionProposal]:
        capped: list[ObservationPromotionProposal] = []
        grouped: dict[str, list[ObservationPromotionProposal]] = {}
        for proposal in proposals:
            grouped.setdefault(proposal.memory_class, []).append(proposal)
        for memory_class, class_proposals in grouped.items():
            limit = max(0, int(self.proposal_caps_by_class.get(memory_class, len(class_proposals))))
            ordered = sorted(
                class_proposals,
                key=lambda proposal: (
                    int(proposal.metadata.get("observation_count", len(proposal.observation_ids))),
                    proposal.confidence,
                    proposal.relevance,
                    proposal.summary,
                ),
                reverse=True,
            )
            capped.extend(ordered[:limit])
        return capped


def build_default_maintenance_policy() -> MaintenancePolicyV2:
    return MaintenancePolicyV2(
        candidate_thresholds={
            "identity": CandidatePromotionThreshold("identity", 0.8, 0.7, ("stable",)),
            "preference": CandidatePromotionThreshold("preference", 0.72, 0.62, ("stable",)),
            "ongoing_thread": CandidatePromotionThreshold(
                "ongoing_thread",
                0.68,
                0.58,
                ("stable", "semi_stable"),
            ),
            "recent_fact": CandidatePromotionThreshold(
                "recent_fact",
                0.8,
                0.7,
                ("stable",),
            ),
        },
        observation_thresholds={
            "location": ObservationPromotionThreshold("location", 2, 0.66),
            "routine": ObservationPromotionThreshold("routine", 3, 0.68),
            "important_object": ObservationPromotionThreshold("important_object", 3, 0.7),
            "ongoing_thread": ObservationPromotionThreshold("ongoing_thread", 2, 0.7),
        },
    )


def _summary_terms(summary: str, *, limit: int) -> list[str]:
    words = [normalize_semantic_key(match) for match in re.findall(r"[A-Za-z0-9][A-Za-z0-9 _-]*", summary)]
    filtered = [word for word in words if word and word not in _STOPWORDS]
    deduped: list[str] = []
    for word in filtered:
        if word in deduped:
            continue
        deduped.append(word)
        if len(deduped) >= limit:
            break
    return deduped


def _average_confidence(observations: Iterable[SessionObservation]) -> float:
    values = [observation.confidence for observation in observations]
    if not values:
        return 0.0
    return sum(values) / len(values)


def _most_common_terms(
    term_lists: Iterable[Iterable[str]],
    *,
    limit: int,
) -> list[str]:
    counts: dict[str, int] = {}
    for terms in term_lists:
        for term in terms:
            normalized = normalize_semantic_key(term)
            if not normalized or normalized in _STOPWORDS:
                continue
            counts[normalized] = counts.get(normalized, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [term for term, _count in ordered[:limit]]
