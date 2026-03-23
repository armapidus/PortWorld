from __future__ import annotations

import re
from hashlib import sha256

_STORAGE_ID_PREFIX_MAX_LENGTH = 24


def storage_component_for_id(raw_id: str) -> str:
    prefix = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_id.strip())
    prefix = prefix.strip("._-") or "id"
    prefix = prefix[:_STORAGE_ID_PREFIX_MAX_LENGTH]
    digest = sha256(raw_id.encode("utf-8")).hexdigest()
    return f"{prefix}--{digest}"


def legacy_storage_component_for_id(raw_id: str) -> str:
    return "".join(
        char if char.isalnum() or char in "._-" else "_"
        for char in raw_id.strip()
    ) or "unknown"
