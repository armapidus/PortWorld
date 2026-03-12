from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from backend.memory.lifecycle import SESSION_MEMORY_ARTIFACT_FILE_NAMES

_STORAGE_ID_PREFIX_MAX_LENGTH = 24


class StoragePathMixin:
    paths: Any

    def session_storage_dir(self, *, session_id: str) -> Path:
        return self._resolved_storage_dir(
            root=self.paths.session_root,
            raw_id=session_id,
        )

    def vision_frame_artifact_paths(self, *, session_id: str, frame_id: str) -> tuple[Path, Path]:
        session_dir = self.vision_frames_session_dir(session_id=session_id)
        if self._is_legacy_storage_dir(
            root=self.paths.vision_frames_root,
            directory=session_dir,
            raw_id=session_id,
        ):
            frame_stem = self._legacy_storage_component_for_id(frame_id)
        else:
            frame_stem = self._storage_component_for_id(frame_id)
        return (
            session_dir / f"{frame_stem}.jpg",
            session_dir / f"{frame_stem}.json",
        )

    def vision_frames_session_dir(self, *, session_id: str) -> Path:
        return self._resolved_storage_dir(
            root=self.paths.vision_frames_root,
            raw_id=session_id,
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

    def _ensure_text_file(self, path: Path, default_text: str) -> None:
        if not path.exists():
            path.write_text(default_text, encoding="utf-8")

    def _ensure_json_file(self, path: Path, default_payload: dict[str, Any]) -> None:
        if not path.exists():
            path.write_text(
                json.dumps(default_payload, ensure_ascii=True, indent=2) + "\n",
                encoding="utf-8",
            )

    def _build_session_storage_result(self, *, session_id: str):
        from backend.infrastructure.storage.types import SessionStorageResult

        session_dir = self.session_storage_dir(session_id=session_id)
        return SessionStorageResult(
            session_dir=session_dir,
            short_term_memory_markdown_path=session_dir / SESSION_MEMORY_ARTIFACT_FILE_NAMES[0],
            short_term_memory_json_path=session_dir / SESSION_MEMORY_ARTIFACT_FILE_NAMES[1],
            session_memory_markdown_path=session_dir / SESSION_MEMORY_ARTIFACT_FILE_NAMES[2],
            session_memory_json_path=session_dir / SESSION_MEMORY_ARTIFACT_FILE_NAMES[3],
            vision_events_log_path=session_dir / SESSION_MEMORY_ARTIFACT_FILE_NAMES[4],
            vision_routing_events_log_path=session_dir / SESSION_MEMORY_ARTIFACT_FILE_NAMES[5],
        )

    def _session_vision_frames_dir(self, *, session_id: str) -> Path:
        return self.vision_frames_session_dir(session_id=session_id)

    def _storage_component_for_id(self, raw_id: str) -> str:
        prefix = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_id.strip())
        prefix = prefix.strip("._-") or "id"
        prefix = prefix[:_STORAGE_ID_PREFIX_MAX_LENGTH]
        digest = sha256(raw_id.encode("utf-8")).hexdigest()
        return f"{prefix}--{digest}"

    def _legacy_storage_component_for_id(self, raw_id: str) -> str:
        return "".join(
            char if char.isalnum() or char in "._-" else "_"
            for char in raw_id.strip()
        ) or "unknown"

    def _resolved_storage_dir(self, *, root: Path, raw_id: str) -> Path:
        hashed_dir = root / self._storage_component_for_id(raw_id)
        if hashed_dir.exists():
            return hashed_dir

        legacy_dir = root / self._legacy_storage_component_for_id(raw_id)
        if legacy_dir.exists():
            return legacy_dir

        return hashed_dir

    def _is_legacy_storage_dir(self, *, root: Path, directory: Path, raw_id: str) -> bool:
        legacy_dir = root / self._legacy_storage_component_for_id(raw_id)
        hashed_dir = root / self._storage_component_for_id(raw_id)
        return directory == legacy_dir and directory != hashed_dir
