from __future__ import annotations

from backend.core.storage import BackendStorage
from backend.infrastructure.storage.artifacts import ArtifactStorageMixin
from backend.infrastructure.storage.paths import StoragePathMixin
from backend.infrastructure.storage.user_memory import UserMemoryStorageMixin
from backend.infrastructure.storage.sessions import SessionStorageMixin
from backend.infrastructure.storage.sqlite import SQLiteStorageMixin
from backend.infrastructure.storage.types import StorageBootstrapResult, StorageInfo, StoragePaths, now_ms
from backend.infrastructure.storage.vision import VisionFrameStorageMixin


class LocalBackendStorage(
    SessionStorageMixin,
    UserMemoryStorageMixin,
    ArtifactStorageMixin,
    VisionFrameStorageMixin,
    SQLiteStorageMixin,
    StoragePathMixin,
    BackendStorage,
):
    """SQLite/filesystem storage implementation used for local mode."""

    # Explicit forwarding methods make the intended MRO resolution visible to
    # static analysis without changing the concrete mixin implementation used.
    def bootstrap_session_storage(self, *args, **kwargs):
        return super().bootstrap_session_storage(*args, **kwargs)

    def ensure_session_storage(self, *args, **kwargs):
        return super().ensure_session_storage(*args, **kwargs)

    def get_session_storage_paths(self, *args, **kwargs):
        return super().get_session_storage_paths(*args, **kwargs)

    def upsert_session_status(self, *args, **kwargs):
        return super().upsert_session_status(*args, **kwargs)

    def append_vision_event(self, *args, **kwargs):
        return super().append_vision_event(*args, **kwargs)

    def append_vision_routing_event(self, *args, **kwargs):
        return super().append_vision_routing_event(*args, **kwargs)

    def read_vision_events(self, *args, **kwargs):
        return super().read_vision_events(*args, **kwargs)

    def read_session_memory(self, *args, **kwargs):
        return super().read_session_memory(*args, **kwargs)

    def read_short_term_memory(self, *args, **kwargs):
        return super().read_short_term_memory(*args, **kwargs)

    def read_session_memory_markdown(self, *args, **kwargs):
        return super().read_session_memory_markdown(*args, **kwargs)

    def read_short_term_memory_markdown(self, *args, **kwargs):
        return super().read_short_term_memory_markdown(*args, **kwargs)

    def get_session_memory_reset_eligibility(self, *args, **kwargs):
        return super().get_session_memory_reset_eligibility(*args, **kwargs)

    def reset_session_memory(self, *args, **kwargs):
        return super().reset_session_memory(*args, **kwargs)

    def list_session_memory_retention_eligibility(self, *args, **kwargs):
        return super().list_session_memory_retention_eligibility(*args, **kwargs)

    def sweep_expired_session_memory(self, *args, **kwargs):
        return super().sweep_expired_session_memory(*args, **kwargs)

    def write_short_term_memory(self, *args, **kwargs):
        return super().write_short_term_memory(*args, **kwargs)

    def write_session_memory(self, *args, **kwargs):
        return super().write_session_memory(*args, **kwargs)

    def read_session_memory_status(self, *args, **kwargs):
        return super().read_session_memory_status(*args, **kwargs)

    def register_artifact(self, *args, **kwargs):
        return super().register_artifact(*args, **kwargs)

    def list_memory_export_artifacts(self, *args, **kwargs):
        return super().list_memory_export_artifacts(*args, **kwargs)

    def read_cross_session_memory(self, *args, **kwargs):
        return super().read_cross_session_memory(*args, **kwargs)

    def read_user_memory_payload(self, *args, **kwargs):
        return super().read_user_memory_payload(*args, **kwargs)

    def read_user_memory_markdown(self, *args, **kwargs):
        return super().read_user_memory_markdown(*args, **kwargs)

    def write_user_memory_payload(self, *args, **kwargs):
        return super().write_user_memory_payload(*args, **kwargs)

    def reset_user_memory_payload(self, *args, **kwargs):
        return super().reset_user_memory_payload(*args, **kwargs)

    def write_user_memory(self, *args, **kwargs):
        return super().write_user_memory(*args, **kwargs)

    def write_cross_session_memory(self, *args, **kwargs):
        return super().write_cross_session_memory(*args, **kwargs)

    def append_memory_candidate(self, *args, **kwargs):
        return super().append_memory_candidate(*args, **kwargs)

    def read_memory_candidates(self, *args, **kwargs):
        return super().read_memory_candidates(*args, **kwargs)

    def store_vision_frame_ingest(self, *args, **kwargs):
        return super().store_vision_frame_ingest(*args, **kwargs)

    def delete_vision_ingest_artifacts(self, *args, **kwargs):
        return super().delete_vision_ingest_artifacts(*args, **kwargs)

    def update_vision_frame_processing(self, *args, **kwargs):
        return super().update_vision_frame_processing(*args, **kwargs)

    def get_vision_frame_record(self, *args, **kwargs):
        return super().get_vision_frame_record(*args, **kwargs)

    def __init__(self, *, paths: StoragePaths) -> None:
        self.paths = paths
        super().__init__(
            storage_info=StorageInfo(
                backend="local",
                details={
                    "data_root": str(paths.data_root),
                    "memory_root": str(paths.memory_root),
                    "user_root": str(paths.user_root),
                    "session_root": str(paths.session_root),
                    "vision_frames_root": str(paths.vision_frames_root),
                    "sqlite_path": str(paths.sqlite_path),
                    "user_memory_path": str(paths.user_memory_path),
                    "cross_session_memory_path": str(paths.cross_session_memory_path),
                    "user_profile_markdown_path": str(paths.user_profile_markdown_path),
                },
            )
        )

    def bootstrap(self) -> StorageBootstrapResult:
        self._ensure_directories()
        self._ensure_user_memory_files()
        self._initialize_sqlite()
        return StorageBootstrapResult(
            storage_backend=self.backend_name,
            sqlite_path=self.paths.sqlite_path,
            user_profile_markdown_path=self.paths.user_memory_path,
            bootstrapped_at_ms=now_ms(),
            storage_details=dict(self.storage_info.details),
        )

    def local_storage_paths(self) -> StoragePaths:
        return self.paths
