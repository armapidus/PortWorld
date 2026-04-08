from __future__ import annotations

from pathlib import Path

MEMORY_V2_ROOT = Path("memory") / "v2"
MEMORY_V2_ITEMS_DIR = MEMORY_V2_ROOT / "items"
MEMORY_V2_GLOBAL_EVIDENCE_DIR = MEMORY_V2_ROOT / "evidence"
MEMORY_V2_INDEXES_DIR = MEMORY_V2_ROOT / "indexes"
MEMORY_V2_SESSIONS_DIR = MEMORY_V2_ROOT / "sessions"

MEMORY_V2_ITEM_ARTIFACT_KIND = "memory_v2_item"
MEMORY_V2_EVIDENCE_ARTIFACT_KIND = "memory_v2_evidence"
MEMORY_V2_CANDIDATE_LOG_ARTIFACT_KIND = "memory_v2_candidate_log"
MEMORY_V2_OBSERVATION_LOG_ARTIFACT_KIND = "memory_v2_observation_log"
MEMORY_V2_RETRIEVAL_INDEX_ARTIFACT_KIND = "memory_v2_retrieval_index"
MEMORY_V2_MAINTENANCE_STATE_ARTIFACT_KIND = "memory_v2_maintenance_state"


def memory_item_relative_path(*, item_id: str) -> Path:
    return MEMORY_V2_ITEMS_DIR / f"{item_id}.json"


def global_memory_evidence_relative_path(*, evidence_id: str) -> Path:
    return MEMORY_V2_GLOBAL_EVIDENCE_DIR / f"{evidence_id}.json"


def session_memory_v2_dir(*, session_component: str) -> Path:
    return MEMORY_V2_SESSIONS_DIR / session_component


def session_memory_candidate_log_relative_path(*, session_component: str) -> Path:
    return session_memory_v2_dir(session_component=session_component) / "candidates.ndjson"


def session_observation_log_relative_path(*, session_component: str) -> Path:
    return session_memory_v2_dir(session_component=session_component) / "observations.ndjson"


def session_memory_evidence_relative_path(*, session_component: str, evidence_id: str) -> Path:
    return session_memory_v2_dir(session_component=session_component) / "evidence" / f"{evidence_id}.json"


def retrieval_index_relative_path() -> Path:
    return MEMORY_V2_INDEXES_DIR / "retrieval.json"


def maintenance_state_relative_path() -> Path:
    return MEMORY_V2_INDEXES_DIR / "maintenance_state.json"

