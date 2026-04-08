from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from backend.core.storage import now_ms
from backend.memory.conflicts_v2 import conflict_group_key
from backend.memory.indexing_v2 import live_usefulness_score
from backend.memory.maintenance_policy_v2 import (
    MaintenancePolicyV2,
    ObservationPromotionProposal,
    build_default_maintenance_policy,
)
from backend.memory.normalization_v2 import (
    build_memory_fingerprint,
    build_memory_item_id,
    normalize_semantic_key,
)
from backend.memory.repository_v2 import MemoryRepositoryV2
from backend.memory.types_v2 import MaintenanceState, MemoryEvidence, MemoryItem

_SEMANTIC_DUPLICATE_NOISE_TOKENS = frozenset(
    {
        "app",
        "document",
        "file",
        "home",
        "item",
        "menu",
        "note",
        "object",
        "page",
        "project",
        "screen",
        "task",
        "text",
        "thread",
        "work",
    }
)


@dataclass(frozen=True, slots=True)
class MaintenancePhaseResult:
    phase: str
    scope: str
    dry_run: bool
    session_ids: tuple[str, ...]
    promoted_count: int = 0
    merged_count: int = 0
    suppressed_count: int = 0
    rejected_count: int = 0
    conflicted_count: int = 0
    archived_count: int = 0
    decayed_count: int = 0
    refreshed_count: int = 0
    metadata: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["session_ids"] = list(self.session_ids)
        return payload


@dataclass(frozen=True, slots=True)
class MaintenanceRunResult:
    scope: str
    phase: str
    dry_run: bool
    session_ids: tuple[str, ...]
    phases: tuple[MaintenancePhaseResult, ...]
    maintenance_state: MaintenanceState
    ran_at_ms: int

    def to_dict(self) -> dict[str, object]:
        processed_sessions = len(self.session_ids)
        promoted_items = sum(phase.promoted_count for phase in self.phases)
        conflicts = sum(phase.conflicted_count for phase in self.phases)
        processed_candidates = sum(
            int((phase.metadata or {}).get("processed_candidates", 0))
            for phase in self.phases
        )
        return {
            "scope": self.scope,
            "phase": self.phase,
            "dry_run": self.dry_run,
            "session_ids": list(self.session_ids),
            "session_id": self.session_ids[0] if self.scope == "session" and self.session_ids else None,
            "processed_sessions": processed_sessions,
            "processed_candidates": processed_candidates,
            "promoted_items": promoted_items,
            "conflicts": conflicts,
            "phases": [phase.to_dict() for phase in self.phases],
            "maintenance_state": {
                "updated_at_ms": self.maintenance_state.updated_at_ms,
                "last_candidate_consolidation_at_ms": self.maintenance_state.last_candidate_consolidation_at_ms,
                "last_observation_promotion_at_ms": self.maintenance_state.last_observation_promotion_at_ms,
                "last_dedup_at_ms": self.maintenance_state.last_dedup_at_ms,
                "metadata": dict(self.maintenance_state.metadata),
            },
            "ran_at_ms": self.ran_at_ms,
        }


class MemoryMaintenanceServiceV2:
    def __init__(
        self,
        *,
        repository: MemoryRepositoryV2,
        policy: MaintenancePolicyV2 | None = None,
    ) -> None:
        self.repository = repository
        self.policy = policy or build_default_maintenance_policy()

    def run_candidate_consolidation(
        self,
        *,
        scope: str,
        session_id: str | None = None,
        dry_run: bool = False,
        reference_time_ms: int | None = None,
    ) -> MaintenancePhaseResult:
        reference_ms = reference_time_ms or now_ms()
        session_ids = self._resolve_session_ids(scope=scope, session_id=session_id)
        promoted = 0
        merged = 0
        suppressed = 0
        rejected = 0
        conflicted = 0
        processed = 0
        for candidate in self._iter_pending_candidates(session_ids=session_ids):
            processed += 1
            if not self.policy.should_promote_candidate(candidate):
                suppressed += 1
                if not dry_run:
                    self.repository.create_candidate(
                        session_id=candidate.session_id,
                        candidate=replace(
                            candidate,
                            status="suppressed",
                            metadata={
                                **candidate.metadata,
                                "maintenance_decision": "suppressed_threshold",
                                "maintenance_updated_at_ms": reference_ms,
                            },
                        ),
                    )
                continue

            subject_key = self.policy.derive_candidate_subject_key(candidate)
            value_key = self.policy.derive_candidate_value_key(candidate)
            fingerprint = build_memory_fingerprint(
                memory_class=candidate.memory_class,
                scope=candidate.scope,
                subject_key=subject_key,
                value_key=value_key,
            )
            existing = self.repository.find_item_by_fingerprint(fingerprint=fingerprint)
            if existing is not None:
                merged += 1
                if not dry_run:
                    updated = self._merge_candidate_into_item(
                        item=existing,
                        candidate_session_id=candidate.session_id,
                        confidence=candidate.confidence,
                        relevance=candidate.relevance,
                        promoted_at_ms=reference_ms,
                        source_kind="conversation",
                    )
                    updated = self.repository.upsert_item(item=updated)
                    self._attach_candidate_evidence(item_id=updated.item_id, evidence_ids=candidate.evidence_ids)
                    self.repository.create_candidate(
                        session_id=candidate.session_id,
                        candidate=replace(
                            candidate,
                            status="promoted",
                            metadata={
                                **candidate.metadata,
                                "maintenance_decision": "merged_existing_item",
                                "promoted_item_id": updated.item_id,
                                "maintenance_updated_at_ms": reference_ms,
                            },
                        ),
                    )
                continue

            conflicting = self.repository.find_conflicting_item(
                memory_class=candidate.memory_class,
                scope=candidate.scope,
                subject_key=subject_key,
                value_key=value_key,
            )
            if conflicting is not None:
                conflicted += 1
                if not dry_run:
                    detected_group_key = conflict_group_key(
                        memory_class=candidate.memory_class,
                        scope=candidate.scope,
                        subject_key=subject_key,
                    )
                    conflict_item = self._candidate_to_item(
                        session_id=candidate.session_id,
                        memory_class=candidate.memory_class,
                        scope=candidate.scope,
                        summary=candidate.summary,
                        subject_key=subject_key,
                        value_key=value_key,
                        confidence=candidate.confidence,
                        relevance=candidate.relevance,
                        maturity=0.55,
                        first_seen_at_ms=candidate.captured_at_ms or reference_ms,
                        last_seen_at_ms=candidate.captured_at_ms or reference_ms,
                        last_promoted_at_ms=reference_ms,
                        source_kind="conversation",
                        status="conflicted",
                        tags=candidate.tags,
                        metadata={
                            **candidate.metadata,
                            "conflict_with_item_id": conflicting.item_id,
                            "conflict_group_key": detected_group_key,
                            "origin": "candidate_consolidation",
                        },
                    )
                    conflict_item = self.repository.upsert_item(item=conflict_item)
                    self._attach_candidate_evidence(item_id=conflict_item.item_id, evidence_ids=candidate.evidence_ids)
                    self.repository.create_candidate(
                        session_id=candidate.session_id,
                        candidate=replace(
                            candidate,
                            status="rejected",
                            metadata={
                                **candidate.metadata,
                                "maintenance_decision": "conflict_detected",
                                "conflict_item_id": conflict_item.item_id,
                                "conflict_with_item_id": conflicting.item_id,
                                "conflict_group_key": detected_group_key,
                                "maintenance_updated_at_ms": reference_ms,
                            },
                        ),
                    )
                rejected += 1
                continue

            promoted += 1
            if not dry_run:
                item = self._candidate_to_item(
                    session_id=candidate.session_id,
                    memory_class=candidate.memory_class,
                    scope=candidate.scope,
                    summary=candidate.summary,
                    subject_key=subject_key,
                    value_key=value_key,
                    confidence=candidate.confidence,
                    relevance=candidate.relevance,
                    maturity=0.45,
                    first_seen_at_ms=candidate.captured_at_ms or reference_ms,
                    last_seen_at_ms=candidate.captured_at_ms or reference_ms,
                    last_promoted_at_ms=reference_ms,
                    source_kind="conversation",
                    status="active",
                    tags=candidate.tags,
                    metadata={
                        **candidate.metadata,
                        "candidate_id": candidate.candidate_id,
                        "origin": "candidate_consolidation",
                    },
                )
                item = self.repository.upsert_item(item=item)
                self._attach_candidate_evidence(item_id=item.item_id, evidence_ids=candidate.evidence_ids)
                self.repository.create_candidate(
                    session_id=candidate.session_id,
                    candidate=replace(
                        candidate,
                        status="promoted",
                        metadata={
                            **candidate.metadata,
                            "maintenance_decision": "promoted_new_item",
                            "promoted_item_id": item.item_id,
                            "maintenance_updated_at_ms": reference_ms,
                        },
                    ),
                )

        return MaintenancePhaseResult(
            phase="candidates",
            scope=scope,
            dry_run=dry_run,
            session_ids=tuple(session_ids),
            promoted_count=promoted,
            merged_count=merged,
            suppressed_count=suppressed,
            rejected_count=rejected,
            conflicted_count=conflicted,
            metadata={
                "processed_candidates": processed,
                "detected_conflict_groups": len(self.repository.list_conflict_groups()),
            },
        )

    def run_observation_promotion(
        self,
        *,
        scope: str,
        session_id: str | None = None,
        dry_run: bool = False,
        reference_time_ms: int | None = None,
    ) -> MaintenancePhaseResult:
        reference_ms = reference_time_ms or now_ms()
        session_ids = self._resolve_session_ids(scope=scope, session_id=session_id)
        promoted = 0
        merged = 0
        conflicted = 0
        processed = 0
        for current_session_id in session_ids:
            observations = self.repository.list_observations(session_id=current_session_id)
            proposals = self.policy.derive_observation_proposals(observations)
            processed += len(proposals)
            observation_map = {observation.observation_id: observation for observation in observations}
            for proposal in proposals:
                fingerprint = build_memory_fingerprint(
                    memory_class=proposal.memory_class,
                    scope=proposal.scope,
                    subject_key=proposal.subject_key,
                    value_key=proposal.value_key,
                )
                existing = self.repository.find_item_by_fingerprint(fingerprint=fingerprint)
                if existing is not None:
                    merged += 1
                    if not dry_run:
                        updated = self._merge_observation_proposal_into_item(
                            item=existing,
                            proposal=proposal,
                            reference_ms=reference_ms,
                        )
                        updated = self.repository.upsert_item(item=updated)
                        self._attach_observation_evidence(
                            item_id=updated.item_id,
                            observation_ids=proposal.observation_ids,
                            observation_map=observation_map,
                        )
                        self._attach_derived_pattern_evidence(
                            item_id=updated.item_id,
                            proposal=proposal,
                            session_id=current_session_id,
                            captured_at_ms=self._proposal_last_seen_at_ms(
                                proposal,
                                observation_map,
                                reference_ms,
                            ),
                        )
                    continue
                semantic_duplicate = self._find_semantic_duplicate_for_proposal(proposal=proposal)
                if semantic_duplicate is not None:
                    merged += 1
                    if not dry_run:
                        updated = self._merge_observation_proposal_into_item(
                            item=semantic_duplicate,
                            proposal=proposal,
                            reference_ms=reference_ms,
                        )
                        updated = self.repository.upsert_item(item=updated)
                        self._attach_observation_evidence(
                            item_id=updated.item_id,
                            observation_ids=proposal.observation_ids,
                            observation_map=observation_map,
                        )
                        self._attach_derived_pattern_evidence(
                            item_id=updated.item_id,
                            proposal=proposal,
                            session_id=current_session_id,
                            captured_at_ms=self._proposal_last_seen_at_ms(
                                proposal,
                                observation_map,
                                reference_ms,
                            ),
                        )
                    continue

                conflicting = self.repository.find_conflicting_item(
                    memory_class=proposal.memory_class,
                    scope=proposal.scope,
                    subject_key=proposal.subject_key,
                    value_key=proposal.value_key,
                )
                status = "active" if conflicting is None else "conflicted"
                detected_group_key = (
                    conflict_group_key(
                        memory_class=proposal.memory_class,
                        scope=proposal.scope,
                        subject_key=proposal.subject_key,
                    )
                    if conflicting is not None
                    else None
                )
                if conflicting is not None:
                    conflicted += 1
                else:
                    promoted += 1
                if dry_run:
                    continue
                item = self._candidate_to_item(
                    session_id=None,
                    memory_class=proposal.memory_class,
                    scope=proposal.scope,
                    summary=proposal.summary,
                    subject_key=proposal.subject_key,
                    value_key=proposal.value_key,
                    confidence=proposal.confidence,
                    relevance=proposal.relevance,
                    maturity=proposal.maturity,
                    first_seen_at_ms=self._proposal_first_seen_at_ms(proposal, observation_map, reference_ms),
                    last_seen_at_ms=self._proposal_last_seen_at_ms(proposal, observation_map, reference_ms),
                    last_promoted_at_ms=reference_ms,
                    source_kind="derived_pattern",
                    status=status,
                    tags=proposal.tags,
                    metadata={
                        **proposal.metadata,
                        **(
                            {
                                "conflict_with_item_id": conflicting.item_id,
                                "conflict_group_key": detected_group_key,
                            }
                            if conflicting is not None
                            else {}
                        ),
                        "origin": "observation_promotion",
                    },
                )
                item = self.repository.upsert_item(item=item)
                self._attach_observation_evidence(
                    item_id=item.item_id,
                    observation_ids=proposal.observation_ids,
                    observation_map=observation_map,
                )
                self._attach_derived_pattern_evidence(
                    item_id=item.item_id,
                    proposal=proposal,
                    session_id=current_session_id,
                    captured_at_ms=self._proposal_last_seen_at_ms(
                        proposal,
                        observation_map,
                        reference_ms,
                    ),
                )

        return MaintenancePhaseResult(
            phase="observations",
            scope=scope,
            dry_run=dry_run,
            session_ids=tuple(session_ids),
            promoted_count=promoted,
            merged_count=merged,
            conflicted_count=conflicted,
            metadata={
                "processed_proposals": processed,
                "detected_conflict_groups": len(self.repository.list_conflict_groups()),
            },
        )

    def run_retrieval_refresh(
        self,
        *,
        scope: str,
        session_id: str | None = None,
        dry_run: bool = False,
        reference_time_ms: int | None = None,
    ) -> MaintenancePhaseResult:
        _ = session_id
        reference_ms = reference_time_ms or now_ms()
        session_ids = self._resolve_session_ids(scope=scope, session_id=session_id)
        eligible_items = [
            item for item in self.repository.list_items() if self.policy.is_live_bundle_candidate(item)
        ]
        if not dry_run:
            self.repository.rebuild_retrieval_index_state()
        return MaintenancePhaseResult(
            phase="retrieval",
            scope=scope,
            dry_run=dry_run,
            session_ids=tuple(session_ids),
            refreshed_count=len(eligible_items),
            metadata={"updated_at_ms": reference_ms},
        )

    def run_decay_and_archive(
        self,
        *,
        scope: str,
        session_id: str | None = None,
        dry_run: bool = False,
        reference_time_ms: int | None = None,
    ) -> MaintenancePhaseResult:
        reference_ms = reference_time_ms or now_ms()
        session_ids = self._resolve_session_ids(scope=scope, session_id=session_id)
        decayed = 0
        archived = 0
        items = self.repository.list_items()
        session_filter = set(session_ids)
        for item in items:
            if scope == "session" and item.session_id not in session_filter:
                continue
            updated = item
            decayed_relevance = self.policy.decayed_relevance(item, reference_time_ms=reference_ms)
            if decayed_relevance < item.relevance:
                decayed += 1
                updated = replace(updated, relevance=decayed_relevance)
            if self.policy.should_archive_item(updated, reference_time_ms=reference_ms):
                archived += 1
                updated = replace(updated, status="archived")
            if not dry_run and updated != item:
                self.repository.upsert_item(item=updated)

        return MaintenancePhaseResult(
            phase="decay",
            scope=scope,
            dry_run=dry_run,
            session_ids=tuple(session_ids),
            archived_count=archived,
            decayed_count=decayed,
        )

    def run_full_maintenance(
        self,
        *,
        scope: str,
        session_id: str | None = None,
        dry_run: bool = False,
    ) -> MaintenanceRunResult:
        reference_ms = now_ms()
        candidate_result = self.run_candidate_consolidation(
            scope=scope,
            session_id=session_id,
            dry_run=dry_run,
            reference_time_ms=reference_ms,
        )
        observation_result = self.run_observation_promotion(
            scope=scope,
            session_id=session_id,
            dry_run=dry_run,
            reference_time_ms=reference_ms,
        )
        retrieval_result = self.run_retrieval_refresh(
            scope=scope,
            session_id=session_id,
            dry_run=dry_run,
            reference_time_ms=reference_ms,
        )
        decay_result = self.run_decay_and_archive(
            scope=scope,
            session_id=session_id,
            dry_run=dry_run,
            reference_time_ms=reference_ms,
        )
        return self._finalize_run(
            scope=scope,
            phase="full",
            dry_run=dry_run,
            session_id=session_id,
            phase_results=(
                candidate_result,
                observation_result,
                retrieval_result,
                decay_result,
            ),
            reference_ms=reference_ms,
        )

    def run_phase(
        self,
        *,
        phase: str,
        scope: str,
        session_id: str | None = None,
        dry_run: bool = False,
    ) -> MaintenanceRunResult:
        normalized_phase = phase.strip().lower()
        reference_ms = now_ms()
        if normalized_phase == "full":
            return self.run_full_maintenance(scope=scope, session_id=session_id, dry_run=dry_run)
        phase_map = {
            "candidates": self.run_candidate_consolidation,
            "observations": self.run_observation_promotion,
            "retrieval": self.run_retrieval_refresh,
            "decay": self.run_decay_and_archive,
        }
        try:
            runner = phase_map[normalized_phase]
        except KeyError as exc:
            supported = ", ".join(["full", *sorted(phase_map)])
            raise ValueError(f"Unsupported maintenance phase {phase!r}. Supported: {supported}") from exc
        result = runner(
            scope=scope,
            session_id=session_id,
            dry_run=dry_run,
            reference_time_ms=reference_ms,
        )
        return self._finalize_run(
            scope=scope,
            phase=normalized_phase,
            dry_run=dry_run,
            session_id=session_id,
            phase_results=(result,),
            reference_ms=reference_ms,
        )

    def _finalize_run(
        self,
        *,
        scope: str,
        phase: str,
        dry_run: bool,
        session_id: str | None,
        phase_results: tuple[MaintenancePhaseResult, ...],
        reference_ms: int,
    ) -> MaintenanceRunResult:
        session_ids = tuple(self._resolve_session_ids(scope=scope, session_id=session_id))
        current_state = self.repository.read_maintenance_state()
        state = replace(
            current_state,
            updated_at_ms=reference_ms,
            last_candidate_consolidation_at_ms=(
                reference_ms
                if any(result.phase == "candidates" for result in phase_results)
                else current_state.last_candidate_consolidation_at_ms
            ),
            last_observation_promotion_at_ms=(
                reference_ms
                if any(result.phase == "observations" for result in phase_results)
                else current_state.last_observation_promotion_at_ms
            ),
            last_dedup_at_ms=(
                reference_ms
                if any(result.phase in {"candidates", "observations"} for result in phase_results)
                else current_state.last_dedup_at_ms
            ),
            metadata={
                **current_state.metadata,
                "last_scope": scope,
                "last_phase": phase,
                "last_dry_run": dry_run,
                "last_session_ids": list(session_ids),
                "last_results": [result.to_dict() for result in phase_results],
            },
        )
        if not dry_run:
            state = self.repository.write_maintenance_state(state=state)
        return MaintenanceRunResult(
            scope=scope,
            phase=phase,
            dry_run=dry_run,
            session_ids=session_ids,
            phases=phase_results,
            maintenance_state=state,
            ran_at_ms=reference_ms,
        )

    def _resolve_session_ids(self, *, scope: str, session_id: str | None) -> list[str]:
        normalized_scope = scope.strip().lower()
        if normalized_scope not in {"global", "session"}:
            raise ValueError("Maintenance scope must be 'global' or 'session'.")
        if normalized_scope == "session":
            if not session_id:
                raise ValueError("session_id is required when scope='session'.")
            return [session_id.strip()]
        return self.repository.list_session_ids_with_memory_activity()

    def _iter_pending_candidates(self, *, session_ids: list[str]):
        for session_id in session_ids:
            for candidate in self.repository.list_candidates(session_id=session_id):
                if candidate.status == "pending":
                    yield candidate

    def _attach_candidate_evidence(self, *, item_id: str, evidence_ids: tuple[str, ...]) -> None:
        for evidence in self.repository.list_evidence_records(evidence_ids=evidence_ids):
            self.repository.attach_evidence(item_id=item_id, evidence=evidence)

    def _attach_observation_evidence(
        self,
        *,
        item_id: str,
        observation_ids: tuple[str, ...],
        observation_map: dict[str, object],
    ) -> None:
        evidence_ids: list[str] = []
        for observation_id in observation_ids:
            observation = observation_map.get(observation_id)
            if observation is None:
                continue
            evidence_ids.extend(getattr(observation, "evidence_ids", ()))
        for evidence in self.repository.list_evidence_records(evidence_ids=tuple(evidence_ids)):
            self.repository.attach_evidence(item_id=item_id, evidence=evidence)

    def _attach_derived_pattern_evidence(
        self,
        *,
        item_id: str,
        proposal: ObservationPromotionProposal,
        session_id: str,
        captured_at_ms: int,
    ) -> None:
        evidence = MemoryEvidence(
            evidence_id="",
            evidence_kind="derived_pattern",
            session_id=session_id,
            source_ref=f"maintenance:{proposal.memory_class}",
            excerpt=proposal.summary,
            captured_at_ms=captured_at_ms,
            confidence=proposal.confidence,
            item_id=item_id,
            tags=proposal.tags,
            metadata={
                **proposal.metadata,
                "observation_ids": list(proposal.observation_ids),
                "derived_from": "observation_promotion",
            },
        )
        self.repository.attach_evidence(item_id=item_id, evidence=evidence)

    def _merge_candidate_into_item(
        self,
        *,
        item: MemoryItem,
        candidate_session_id: str,
        confidence: float,
        relevance: float,
        promoted_at_ms: int,
        source_kind: str,
    ) -> MemoryItem:
        source_kinds = tuple(dict.fromkeys([*item.source_kinds, source_kind]))
        metadata = {
            **item.metadata,
            "maintenance_merge_count": int(item.metadata.get("maintenance_merge_count", 0)) + 1,
        }
        return replace(
            item,
            session_id=item.session_id or candidate_session_id,
            confidence=max(item.confidence, confidence),
            relevance=max(item.relevance, relevance),
            maturity=min(1.0, max(item.maturity, 0.5) + 0.08),
            last_seen_at_ms=promoted_at_ms,
            last_promoted_at_ms=promoted_at_ms,
            source_kinds=source_kinds,
            metadata=metadata,
        )

    def _merge_observation_proposal_into_item(
        self,
        *,
        item: MemoryItem,
        proposal: ObservationPromotionProposal,
        reference_ms: int,
    ) -> MemoryItem:
        source_kinds = tuple(dict.fromkeys([*item.source_kinds, "derived_pattern"]))
        tags = tuple(dict.fromkeys([*item.tags, *proposal.tags]))
        previous_observation_count = int(item.metadata.get("latest_observation_count", 0))
        current_observation_count = int(
            proposal.metadata.get("observation_count", len(proposal.observation_ids))
        )
        maturity = max(item.maturity, proposal.maturity)
        if current_observation_count > previous_observation_count:
            maturity = min(1.0, maturity + 0.04)
        metadata = {
            **item.metadata,
            "maintenance_merge_count": int(item.metadata.get("maintenance_merge_count", 0)) + 1,
            "latest_observation_count": current_observation_count,
        }
        return replace(
            item,
            confidence=max(item.confidence, proposal.confidence),
            relevance=max(item.relevance, proposal.relevance),
            maturity=maturity,
            last_seen_at_ms=reference_ms,
            last_promoted_at_ms=reference_ms,
            source_kinds=source_kinds,
            tags=tags,
            metadata=metadata,
        )

    def _proposal_first_seen_at_ms(
        self,
        proposal: ObservationPromotionProposal,
        observation_map: dict[str, object],
        fallback_ms: int,
    ) -> int:
        timestamps = [
            getattr(observation_map.get(observation_id), "capture_ts_ms", None)
            for observation_id in proposal.observation_ids
        ]
        values = [timestamp for timestamp in timestamps if isinstance(timestamp, int)]
        return min(values) if values else fallback_ms

    def _proposal_last_seen_at_ms(
        self,
        proposal: ObservationPromotionProposal,
        observation_map: dict[str, object],
        fallback_ms: int,
    ) -> int:
        timestamps = [
            getattr(observation_map.get(observation_id), "capture_ts_ms", None)
            for observation_id in proposal.observation_ids
        ]
        values = [timestamp for timestamp in timestamps if isinstance(timestamp, int)]
        return max(values) if values else fallback_ms

    def _candidate_to_item(
        self,
        *,
        session_id: str | None,
        memory_class: str,
        scope: str,
        summary: str,
        subject_key: str,
        value_key: str,
        confidence: float,
        relevance: float,
        maturity: float,
        first_seen_at_ms: int,
        last_seen_at_ms: int,
        last_promoted_at_ms: int,
        source_kind: str,
        status: str,
        tags: tuple[str, ...],
        metadata: dict[str, object],
    ) -> MemoryItem:
        fingerprint = build_memory_fingerprint(
            memory_class=memory_class,
            scope=scope,
            subject_key=subject_key,
            value_key=value_key,
        )
        return MemoryItem(
            item_id=build_memory_item_id(fingerprint=fingerprint),
            memory_class=memory_class,
            scope=scope,
            session_id=session_id,
            status=status,
            summary=summary,
            structured_value={
                "subject_key": subject_key,
                "value_key": value_key,
                "summary": summary,
            },
            confidence=confidence,
            relevance=relevance,
            maturity=maturity,
            fingerprint=fingerprint,
            subject_key=subject_key,
            value_key=value_key,
            first_seen_at_ms=first_seen_at_ms,
            last_seen_at_ms=last_seen_at_ms,
            last_promoted_at_ms=last_promoted_at_ms,
            source_kinds=(source_kind,),
            tags=tags,
            metadata=metadata,
        )

    def _find_semantic_duplicate_for_proposal(
        self,
        *,
        proposal: ObservationPromotionProposal,
    ) -> MemoryItem | None:
        if proposal.memory_class not in {"important_object", "ongoing_thread"}:
            return None
        proposal_tokens = self._semantic_tokens_for_proposal(proposal=proposal)
        if not proposal_tokens:
            return None
        candidates = self.repository.list_items(
            scope=proposal.scope,
            memory_class=proposal.memory_class,
        )
        for item in candidates:
            if item.status != "active":
                continue
            item_tokens = self._semantic_tokens_for_item(item=item)
            if not item_tokens:
                continue
            shared = proposal_tokens.intersection(item_tokens)
            if not shared:
                continue
            union = proposal_tokens.union(item_tokens)
            overlap_ratio = len(shared) / len(union)
            if proposal.memory_class == "important_object":
                if overlap_ratio >= 0.7 or self._is_subterm_match(proposal_tokens, item_tokens):
                    return item
                continue
            if overlap_ratio >= 0.6:
                return item
        return None

    def _semantic_tokens_for_proposal(
        self,
        *,
        proposal: ObservationPromotionProposal,
    ) -> set[str]:
        values = [proposal.subject_key, proposal.value_key, *proposal.tags]
        return self._semantic_tokens(values)

    def _semantic_tokens_for_item(self, *, item: MemoryItem) -> set[str]:
        values = [item.subject_key, item.value_key, *item.tags]
        return self._semantic_tokens(values)

    def _semantic_tokens(self, values: list[str]) -> set[str]:
        tokens: set[str] = set()
        for value in values:
            normalized = normalize_semantic_key(value)
            if not normalized:
                continue
            for part in normalized.split("-"):
                if len(part) < 3:
                    continue
                if part.isdigit():
                    continue
                if part in _SEMANTIC_DUPLICATE_NOISE_TOKENS:
                    continue
                tokens.add(part)
        return tokens

    def _is_subterm_match(self, left: set[str], right: set[str]) -> bool:
        for token in left:
            if any(token in other or other in token for other in right):
                return True
        return False


def summarize_live_memory_item(item: MemoryItem) -> dict[str, object]:
    return {
        "item_id": item.item_id,
        "memory_class": item.memory_class,
        "scope": item.scope,
        "summary": item.summary,
        "status": item.status,
        "score": live_usefulness_score(item),
        "confidence": item.confidence,
        "relevance": item.relevance,
        "maturity": item.maturity,
        "tags": list(item.tags),
        "last_seen_at_ms": item.last_seen_at_ms,
    }


__all__ = [
    "MaintenancePhaseResult",
    "MaintenanceRunResult",
    "MemoryMaintenanceServiceV2",
    "summarize_live_memory_item",
]
