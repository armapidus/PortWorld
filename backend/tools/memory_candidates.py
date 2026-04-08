from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from dataclasses import dataclass

from backend.core.storage import BackendStorage
from backend.memory.candidates import (
    MemoryCandidate,
    build_candidate_evidence_v2,
    build_memory_candidate,
    build_memory_candidate_v2,
)
from backend.memory.repository_v2 import MemoryRepositoryV2
from backend.tools.contracts import ToolCall, ToolResult
from backend.tools.results import tool_error, tool_ok

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MemoryCandidateToolExecutor:
    storage: BackendStorage

    async def __call__(self, call: ToolCall) -> ToolResult:
        candidate = build_memory_candidate(
            session_id=call.session_id,
            scope=call.arguments.get("scope"),
            section_hint=call.arguments.get("section_hint"),
            fact=call.arguments.get("fact"),
            stability=call.arguments.get("stability"),
            confidence=call.arguments.get("confidence"),
        )
        if candidate is None:
            return tool_error(
                call=call,
                error_code="INVALID_MEMORY_CANDIDATE",
                error_message="Memory candidate payload is invalid",
                payload={"session_id": call.session_id},
            )

        try:
            await asyncio.to_thread(
                self.storage.append_memory_candidate,
                session_id=call.session_id,
                candidate=dict(candidate),
            )
        except OSError as exc:
            logger.warning(
                "Memory candidate write failed session_id=%s call_id=%s",
                call.session_id,
                call.call_id,
                exc_info=exc,
            )
            return tool_error(
                call=call,
                error_code="MEMORY_CANDIDATE_WRITE_FAILED",
                error_message="Could not persist memory candidate",
                payload={"session_id": call.session_id},
            )

        try:
            await asyncio.to_thread(
                self._write_v2_candidate_and_evidence,
                candidate,
            )
        except Exception as exc:  # pragma: no cover - additive v2 failures must not break legacy capture
            logger.warning(
                "Memory candidate v2 write failed session_id=%s call_id=%s",
                call.session_id,
                call.call_id,
                exc_info=exc,
            )

        return tool_ok(
            call=call,
            payload={
                "session_id": call.session_id,
                "captured": True,
                "candidate": dict(candidate),
            },
        )

    def _write_v2_candidate_and_evidence(self, candidate: MemoryCandidate) -> None:
        repository = MemoryRepositoryV2(storage=self.storage)
        legacy_candidate = candidate
        v2_candidate = repository.create_candidate(
            session_id=legacy_candidate["session_id"],
            candidate=build_memory_candidate_v2(candidate=legacy_candidate),
        )
        evidence = build_candidate_evidence_v2(
            candidate=legacy_candidate,
            candidate_id=v2_candidate.candidate_id,
        )
        if evidence is None:
            return
        stored_evidence = self.storage.write_memory_evidence(evidence=evidence)
        repository.create_candidate(
            session_id=v2_candidate.session_id,
            candidate=replace(
                v2_candidate,
                evidence_ids=tuple(
                    dict.fromkeys([*v2_candidate.evidence_ids, stored_evidence.evidence_id])
                ),
            ),
        )
