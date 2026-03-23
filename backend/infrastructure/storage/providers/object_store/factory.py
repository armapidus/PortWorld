from __future__ import annotations

from importlib import import_module

from backend.infrastructure.storage.providers.object_store.base import ObjectStore

_OBJECT_STORE_TYPES: dict[str, tuple[str, str]] = {
    # Keep compatibility module paths so test monkeypatching and legacy imports still work.
    "gcs": ("backend.infrastructure.storage.gcs", "GCSObjectStore"),
    "s3": ("backend.infrastructure.storage.s3", "S3ObjectStore"),
    "azure_blob": ("backend.infrastructure.storage.azure_blob", "AzureBlobObjectStore"),
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

    object_store_type = _OBJECT_STORE_TYPES.get(provider)
    if object_store_type is None:
        raise RuntimeError(f"Unsupported managed object store provider: {provider!r}")
    module_name, class_name = object_store_type
    module = import_module(module_name)
    object_store_class = getattr(module, class_name)
    return object_store_class(
        store_name=resolved_store_name,
        endpoint=endpoint,
        key_prefix=key_prefix,
    )
