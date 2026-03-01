"""Persistent run-log storage for pipeline queries.

Every query (iOS or HTTP) records a ``RunLogEntry`` that captures all model
inputs and outputs so you can review real-world performance offline.

Logs are stored as newline-delimited JSON (JSONL) files under ``RUN_LOG_DIR``
(default: ``framework/run_logs/``).  Each server start creates one file.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RUN_LOG_DIR = Path(os.getenv("RUN_LOG_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "run_logs")))

# In-memory buffer so the /v1/runs endpoint can return recent entries quickly.
_MAX_MEMORY_ENTRIES = 200


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class RunLogEntry:
    """One complete query run through the pipeline."""

    # Identifiers
    query_id: str
    session_id: str = ""
    source: str = "unknown"  # "ios_query" | "pipeline" | "debug"

    # Timestamps
    started_at: str = ""
    finished_at: str = ""

    # STT (Voxtral)
    stt_model: str = ""
    stt_audio_bytes: int = 0
    stt_transcript: str | None = None
    stt_error: str | None = None

    # Video analysis (Nemotron)
    video_model: str = ""
    video_prompt_sent: str = ""
    video_summary: str | None = None
    video_error: str | None = None

    # Tools / skills
    tool_runs: list[dict[str, Any]] = field(default_factory=list)

    # Main LLM
    main_llm_model: str = ""
    main_llm_system_prompt: str = ""
    main_llm_user_content: str = ""
    main_llm_messages_count: int = 0
    main_llm_response: str = ""
    main_llm_tokens: int = 0
    main_llm_error: str | None = None

    # TTS (ElevenLabs)
    tts_model: str = ""
    tts_voice_id: str = ""
    tts_audio_bytes: int = 0
    tts_error: str | None = None

    # Overall status
    status: str = "ok"  # "ok" | "partial" | "error"
    error: str | None = None

    # Extra metadata the caller wants to attach
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Writer (thread-safe, async-friendly)
# ---------------------------------------------------------------------------

class RunLogWriter:
    """Append-only JSONL writer with in-memory ring buffer."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[dict[str, Any]] = []
        self._file_path: Path | None = None
        self._file_handle: Any = None

    # -- lifecycle -----------------------------------------------------------

    def open(self) -> Path:
        """Create the log file for this server session."""
        RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._file_path = RUN_LOG_DIR / f"runs_{ts}.jsonl"
        self._file_handle = open(self._file_path, "a", encoding="utf-8")
        logger.info(f"Run-log file: {self._file_path}")
        return self._file_path

    def close(self) -> None:
        if self._file_handle is not None:
            self._file_handle.close()
            self._file_handle = None

    # -- writing -------------------------------------------------------------

    def record(self, entry: RunLogEntry) -> None:
        """Persist an entry to disk and keep it in memory."""
        if not entry.finished_at:
            entry.finished_at = datetime.now(timezone.utc).isoformat()
        row = asdict(entry)
        line = json.dumps(row, ensure_ascii=False, default=str)

        with self._lock:
            # disk
            if self._file_handle is not None:
                self._file_handle.write(line + "\n")
                self._file_handle.flush()
            # memory ring-buffer
            self._entries.append(row)
            if len(self._entries) > _MAX_MEMORY_ENTRIES:
                self._entries = self._entries[-_MAX_MEMORY_ENTRIES:]

    # -- reading -------------------------------------------------------------

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent *limit* entries (newest last)."""
        with self._lock:
            return list(self._entries[-limit:])

    def get(self, query_id: str) -> dict[str, Any] | None:
        """Find a single entry by query_id."""
        with self._lock:
            for entry in reversed(self._entries):
                if entry.get("query_id") == query_id:
                    return entry
        return None

    @property
    def file_path(self) -> Path | None:
        return self._file_path

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._entries)


# Singleton -----------------------------------------------------------------

RUN_LOG = RunLogWriter()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
