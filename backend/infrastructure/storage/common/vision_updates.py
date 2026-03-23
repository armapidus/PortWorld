from __future__ import annotations

import json
from typing import Any


UNSET = object()


def resolve_next_retry_at_ms(
    value: int | object | None,
    existing_value: int | None,
) -> int | None:
    if isinstance(value, int):
        return value
    if value is UNSET and existing_value is not None:
        return int(existing_value)
    return None


def resolve_error_details_json(
    error_details: dict[str, Any] | object | None,
    error_code: str | None,
    existing_json: str | None,
) -> str | None:
    if isinstance(error_details, dict):
        return json.dumps(error_details, ensure_ascii=True, sort_keys=True)
    if error_details is None:
        return None
    if error_details is UNSET and error_code is not None and existing_json is not None:
        return existing_json
    return None
