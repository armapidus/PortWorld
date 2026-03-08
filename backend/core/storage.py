from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import time_ns
from typing import Any, Iterator

SCHEMA_VERSION = "1"


def now_ms() -> int:
    return time_ns() // 1_000_000


@dataclass(frozen=True, slots=True)
class StoragePaths:
    data_root: Path
    user_root: Path
    session_root: Path
    vision_frames_root: Path
    debug_audio_root: Path
    sqlite_path: Path
    user_profile_markdown_path: Path
    user_profile_json_path: Path


@dataclass(frozen=True, slots=True)
class StorageBootstrapResult:
    sqlite_path: Path
    user_profile_markdown_path: Path
    user_profile_json_path: Path
    bootstrapped_at_ms: int


@dataclass(frozen=True, slots=True)
class SessionStorageResult:
    session_dir: Path
    session_memory_markdown_path: Path
    session_memory_json_path: Path


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact_id: str
    session_id: str | None
    artifact_kind: str
    relative_path: str
    content_type: str
    metadata_json: str
    created_at_ms: int


class BackendStorage:
    def __init__(self, *, paths: StoragePaths) -> None:
        self.paths = paths

    def bootstrap(self) -> StorageBootstrapResult:
        self._ensure_directories()
        self._ensure_user_profile_files()
        self._initialize_sqlite()
        return StorageBootstrapResult(
            sqlite_path=self.paths.sqlite_path,
            user_profile_markdown_path=self.paths.user_profile_markdown_path,
            user_profile_json_path=self.paths.user_profile_json_path,
            bootstrapped_at_ms=now_ms(),
        )

    def ensure_session_storage(self, *, session_id: str) -> SessionStorageResult:
        session_dir = self.paths.session_root / self._sanitize_session_id(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        session_memory_markdown_path = session_dir / "session_memory.md"
        session_memory_json_path = session_dir / "session_memory.json"
        if not session_memory_markdown_path.exists():
            session_memory_markdown_path.write_text(
                "# Session Memory\n\n",
                encoding="utf-8",
            )
        if not session_memory_json_path.exists():
            session_memory_json_path.write_text(
                json.dumps({}, ensure_ascii=True, indent=2) + "\n",
                encoding="utf-8",
            )
        return SessionStorageResult(
            session_dir=session_dir,
            session_memory_markdown_path=session_memory_markdown_path,
            session_memory_json_path=session_memory_json_path,
        )

    def upsert_session_status(self, *, session_id: str, status: str) -> None:
        timestamp_ms = now_ms()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO session_index(session_id, status, created_at_ms, updated_at_ms)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    status=excluded.status,
                    updated_at_ms=excluded.updated_at_ms
                """,
                (session_id, status, timestamp_ms, timestamp_ms),
            )
            connection.commit()

    def register_artifact(
        self,
        *,
        artifact_id: str,
        session_id: str | None,
        artifact_kind: str,
        artifact_path: Path,
        content_type: str,
        metadata: dict[str, Any],
    ) -> ArtifactRecord:
        relative_path = str(artifact_path.relative_to(self.paths.data_root))
        created_at_ms = now_ms()
        metadata_json = json.dumps(metadata, ensure_ascii=True, sort_keys=True)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO artifact_index(
                    artifact_id,
                    session_id,
                    artifact_kind,
                    relative_path,
                    content_type,
                    metadata_json,
                    created_at_ms
                )
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(artifact_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    artifact_kind=excluded.artifact_kind,
                    relative_path=excluded.relative_path,
                    content_type=excluded.content_type,
                    metadata_json=excluded.metadata_json,
                    created_at_ms=excluded.created_at_ms
                """,
                (
                    artifact_id,
                    session_id,
                    artifact_kind,
                    relative_path,
                    content_type,
                    metadata_json,
                    created_at_ms,
                ),
            )
            connection.commit()
        return ArtifactRecord(
            artifact_id=artifact_id,
            session_id=session_id,
            artifact_kind=artifact_kind,
            relative_path=relative_path,
            content_type=content_type,
            metadata_json=metadata_json,
            created_at_ms=created_at_ms,
        )

    def _ensure_directories(self) -> None:
        for path in (
            self.paths.data_root,
            self.paths.user_root,
            self.paths.session_root,
            self.paths.vision_frames_root,
            self.paths.debug_audio_root,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def _ensure_user_profile_files(self) -> None:
        if not self.paths.user_profile_markdown_path.exists():
            self.paths.user_profile_markdown_path.write_text(
                "# User Profile\n\n",
                encoding="utf-8",
            )
        if not self.paths.user_profile_json_path.exists():
            self.paths.user_profile_json_path.write_text(
                json.dumps({}, ensure_ascii=True, indent=2) + "\n",
                encoding="utf-8",
            )

    def _initialize_sqlite(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS session_index (
                    session_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS artifact_index (
                    artifact_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    artifact_kind TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL
                );
                """
            )
            connection.execute(
                """
                INSERT INTO schema_meta(key, value)
                VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                ("schema_version", SCHEMA_VERSION),
            )
            connection.commit()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.paths.sqlite_path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            yield connection
        finally:
            connection.close()

    def _sanitize_session_id(self, session_id: str) -> str:
        return "".join(
            char if char.isalnum() or char in "._-" else "_"
            for char in session_id.strip()
        ) or "unknown"
