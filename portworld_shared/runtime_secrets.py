from __future__ import annotations

from typing import Mapping


ADDITIONAL_DEPLOY_SENSITIVE_ENV_KEYS: tuple[str, ...] = (
    "OPENCLAW_AUTH_TOKEN",
)


def additional_required_secret_env_keys(env_values: Mapping[str, str]) -> tuple[str, ...]:
    if _parse_bool(env_values.get("OPENCLAW_ENABLED"), default=False):
        return ("OPENCLAW_AUTH_TOKEN",)
    return ()


def _parse_bool(value: str | None, *, default: bool) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default
