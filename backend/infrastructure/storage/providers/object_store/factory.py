from __future__ import annotations

from collections.abc import Callable

from backend.infrastructure.storage.providers.object_store.azure_blob import AzureBlobObjectStore
from backend.infrastructure.storage.providers.object_store.base import ObjectStore
from backend.infrastructure.storage.providers.object_store.gcs import GCSObjectStore
from backend.infrastructure.storage.providers.object_store.s3 import S3ObjectStore


ObjectStoreBuilder = Callable[[str, str | None, str], ObjectStore]


def _build_gcs(store_name: str, endpoint: str | None, key_prefix: str) -> ObjectStore:
    return GCSObjectStore(store_name=store_name, endpoint=endpoint, key_prefix=key_prefix)


def _build_s3(store_name: str, endpoint: str | None, key_prefix: str) -> ObjectStore:
    return S3ObjectStore(store_name=store_name, endpoint=endpoint, key_prefix=key_prefix)


def _build_azure_blob(store_name: str, endpoint: str | None, key_prefix: str) -> ObjectStore:
    return AzureBlobObjectStore(store_name=store_name, endpoint=endpoint, key_prefix=key_prefix)


_OBJECT_STORE_BUILDERS: dict[str, ObjectStoreBuilder] = {
    "gcs": _build_gcs,
    "s3": _build_s3,
    "azure_blob": _build_azure_blob,
}


def build_object_store(
    *,
    provider: str,
    store_name: str | None = None,
    bucket_name: str | None = None,
    key_prefix: str,
    endpoint: str | None = None,
) -> ObjectStore:
    resolved_store_name = (store_name or bucket_name or "").strip()
    if not resolved_store_name:
        raise RuntimeError("Managed object store name is required.")

    builder = _OBJECT_STORE_BUILDERS.get(provider)
    if builder is None:
        raise RuntimeError(f"Unsupported managed object store provider: {provider!r}")
    return builder(resolved_store_name, endpoint, key_prefix)
