from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict

from backend.memory.normalize import coerce_optional_int, normalize_string, normalize_string_list
from backend.memory.types_v2 import MemoryEvidence, SessionObservation


class AcceptedVisionEvent(TypedDict):
    event_type: str
    frame_id: str
    session_id: str
    capture_ts_ms: int
    analyzed_at_ms: int | None
    provider: str
    model: str
    scene_summary: str
    user_activity_guess: str
    entities: list[str]
    actions: list[str]
    visible_text: list[str]
    documents_seen: list[str]
    salient_change: bool
    confidence: float


def coerce_accepted_vision_event(
    payload: Mapping[str, object],
) -> tuple[AcceptedVisionEvent | None, str | None]:
    frame_id = normalize_string(payload.get("frame_id"))
    if not frame_id:
        return None, "missing_frame_id"

    session_id = normalize_string(payload.get("session_id"))
    if not session_id:
        return None, "missing_session_id"

    capture_ts_ms = coerce_optional_int(payload.get("capture_ts_ms"))
    if capture_ts_ms is None or capture_ts_ms < 0:
        return None, "invalid_capture_ts_ms"

    analyzed_at_ms = coerce_optional_int(payload.get("analyzed_at_ms"))
    confidence = _coerce_confidence(payload.get("confidence"))
    if confidence is None:
        return None, "invalid_confidence"

    event: AcceptedVisionEvent = {
        "event_type": normalize_string(payload.get("event_type")) or "accepted_visual_observation",
        "frame_id": frame_id,
        "session_id": session_id,
        "capture_ts_ms": capture_ts_ms,
        "analyzed_at_ms": analyzed_at_ms,
        "provider": normalize_string(payload.get("provider")),
        "model": normalize_string(payload.get("model")),
        "scene_summary": normalize_string(payload.get("scene_summary")),
        "user_activity_guess": normalize_string(payload.get("user_activity_guess")),
        "entities": normalize_string_list(payload.get("entities")),
        "actions": normalize_string_list(payload.get("actions")),
        "visible_text": normalize_string_list(payload.get("visible_text")),
        "documents_seen": normalize_string_list(payload.get("documents_seen")),
        "salient_change": bool(payload.get("salient_change")),
        "confidence": confidence,
    }
    return event, None


def _coerce_confidence(value: object) -> float | None:
    if value in (None, ""):
        return 0.0
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed < 0.0:
        return 0.0
    if parsed > 1.0:
        if parsed <= 100.0:
            return parsed / 100.0
        return 1.0
    return parsed


def build_session_observation_v2(
    *,
    event: Mapping[str, object],
    route_reason: str,
    routing_score: float | None,
) -> SessionObservation:
    accepted_event, _ = coerce_accepted_vision_event(event)
    if accepted_event is None:
        raise ValueError("Cannot build SessionObservation from invalid accepted vision event payload.")
    return SessionObservation(
        observation_id="",
        session_id=accepted_event["session_id"],
        frame_id=accepted_event["frame_id"],
        capture_ts_ms=accepted_event["capture_ts_ms"],
        analyzed_at_ms=accepted_event["analyzed_at_ms"],
        provider=accepted_event["provider"],
        model=accepted_event["model"],
        scene_summary=accepted_event["scene_summary"],
        user_activity_guess=accepted_event["user_activity_guess"],
        entities=tuple(accepted_event["entities"]),
        actions=tuple(accepted_event["actions"]),
        visible_text=tuple(accepted_event["visible_text"]),
        documents_seen=tuple(accepted_event["documents_seen"]),
        salient_change=accepted_event["salient_change"],
        confidence=accepted_event["confidence"],
        metadata={
            "event_type": accepted_event["event_type"],
            "route_reason": normalize_string(route_reason),
            "routing_score": routing_score,
            "source": "accepted_vision_event",
        },
    )


def build_observation_evidence_v2(
    *,
    observation: SessionObservation,
    route_reason: str,
    routing_score: float | None,
) -> MemoryEvidence:
    excerpt_parts = [observation.scene_summary]
    if observation.user_activity_guess:
        excerpt_parts.append(f"activity={observation.user_activity_guess}")
    excerpt = " | ".join(part for part in excerpt_parts if part).strip()
    return MemoryEvidence(
        evidence_id="",
        evidence_kind="vision_observation",
        session_id=observation.session_id,
        source_ref=f"vision_frame:{observation.frame_id}",
        excerpt=excerpt,
        captured_at_ms=observation.analyzed_at_ms or observation.capture_ts_ms,
        confidence=observation.confidence,
        observation_id=observation.observation_id,
        metadata={
            "frame_id": observation.frame_id,
            "provider": observation.provider,
            "model": observation.model,
            "route_reason": normalize_string(route_reason),
            "routing_score": routing_score,
            "source": "vision_runtime_dual_write",
        },
    )
