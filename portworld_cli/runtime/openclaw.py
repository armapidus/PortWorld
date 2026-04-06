from __future__ import annotations

import ipaddress
from typing import Mapping
from urllib.parse import urlparse

import httpx

from portworld_cli.output import DiagnosticCheck

_DEFAULT_PROBE_TIMEOUT_SECONDS = 4.0


def build_openclaw_doctor_checks(
    *,
    env_values: Mapping[str, str],
) -> tuple[DiagnosticCheck, ...]:
    if not _parse_bool(env_values.get("OPENCLAW_ENABLED"), default=False):
        return ()

    checks: list[DiagnosticCheck] = []
    tooling_enabled = _parse_bool(env_values.get("REALTIME_TOOLING_ENABLED"), default=False)
    checks.append(
        DiagnosticCheck(
            id="openclaw_tooling_dependency",
            status="pass" if tooling_enabled else "fail",
            message=(
                "OpenClaw delegation is enabled and realtime tooling is enabled."
                if tooling_enabled
                else "OpenClaw delegation requires REALTIME_TOOLING_ENABLED=true."
            ),
            action=(
                None
                if tooling_enabled
                else "Set REALTIME_TOOLING_ENABLED=true or disable OPENCLAW_ENABLED."
            ),
        )
    )

    base_url = (env_values.get("OPENCLAW_BASE_URL") or "").strip()
    auth_token = (env_values.get("OPENCLAW_AUTH_TOKEN") or "").strip()
    agent_id = (env_values.get("OPENCLAW_AGENT_ID") or "openclaw/default").strip() or "openclaw/default"

    checks.append(
        DiagnosticCheck(
            id="openclaw_base_url_present",
            status="pass" if bool(base_url) else "fail",
            message=(
                "OPENCLAW_BASE_URL is configured."
                if base_url
                else "OPENCLAW_BASE_URL is required when OPENCLAW_ENABLED=true."
            ),
            action=None if base_url else "Set OPENCLAW_BASE_URL to your OpenClaw gateway URL.",
        )
    )
    checks.append(
        DiagnosticCheck(
            id="openclaw_auth_token_present",
            status="pass" if bool(auth_token) else "fail",
            message=(
                "OPENCLAW_AUTH_TOKEN is configured."
                if auth_token
                else "OPENCLAW_AUTH_TOKEN is required when OPENCLAW_ENABLED=true."
            ),
            action=None if auth_token else "Set OPENCLAW_AUTH_TOKEN with a valid gateway token.",
        )
    )
    checks.append(
        DiagnosticCheck(
            id="openclaw_agent_id",
            status="pass",
            message=f"OPENCLAW_AGENT_ID set to '{agent_id}'.",
        )
    )

    parsed_url = _validate_url(base_url) if base_url else None
    if base_url:
        checks.append(
            DiagnosticCheck(
                id="openclaw_base_url_format",
                status="pass" if parsed_url is not None else "fail",
                message=(
                    "OPENCLAW_BASE_URL format looks valid."
                    if parsed_url is not None
                    else "OPENCLAW_BASE_URL must be an absolute http(s) URL."
                ),
                action=(
                    None
                    if parsed_url is not None
                    else "Use a full URL like http://127.0.0.1:8100 or https://gateway.internal."
                ),
            )
        )
    if parsed_url is not None:
        host = parsed_url.hostname or ""
        host_is_private = _is_private_or_local_host(host)
        checks.append(
            DiagnosticCheck(
                id="openclaw_url_scope",
                status="pass" if host_is_private else "warn",
                message=(
                    "OpenClaw URL points to a local/private host."
                    if host_is_private
                    else "Red flag: OpenClaw URL points to a public host. Restrict exposure and rotate credentials if needed."
                ),
                action=(
                    None
                    if host_is_private
                    else "Prefer localhost/private-network routing or lock ingress/auth before production use."
                ),
            )
        )

    prerequisites_ok = tooling_enabled and bool(base_url) and bool(auth_token) and parsed_url is not None
    if prerequisites_ok:
        timeout_seconds = _probe_timeout_seconds(env_values.get("OPENCLAW_REQUEST_TIMEOUT_MS"))
        checks.append(
            _probe_openclaw_models(
                base_url=base_url,
                auth_token=auth_token,
                timeout_seconds=timeout_seconds,
            )
        )

    return tuple(checks)


def _probe_openclaw_models(
    *,
    base_url: str,
    auth_token: str,
    timeout_seconds: float,
) -> DiagnosticCheck:
    probe_url = f"{base_url.rstrip('/')}/v1/models"
    try:
        response = httpx.get(
            probe_url,
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=timeout_seconds,
        )
    except httpx.TimeoutException:
        return DiagnosticCheck(
            id="openclaw_connectivity_probe",
            status="fail",
            message="OpenClaw connectivity probe timed out.",
            action="Verify OPENCLAW_BASE_URL reachability and increase OPENCLAW_REQUEST_TIMEOUT_MS if needed.",
        )
    except httpx.HTTPError:
        return DiagnosticCheck(
            id="openclaw_connectivity_probe",
            status="fail",
            message="OpenClaw connectivity probe failed: gateway unreachable.",
            action="Verify network routing, DNS, and firewall rules for OPENCLAW_BASE_URL.",
        )

    if 200 <= response.status_code < 300:
        return DiagnosticCheck(
            id="openclaw_connectivity_probe",
            status="pass",
            message="OpenClaw connectivity/auth probe succeeded via GET /v1/models.",
        )
    if response.status_code == 401:
        return DiagnosticCheck(
            id="openclaw_connectivity_probe",
            status="fail",
            message="OpenClaw probe returned 401 Unauthorized.",
            action="Replace OPENCLAW_AUTH_TOKEN with a valid token for the configured gateway.",
        )
    if response.status_code == 403:
        return DiagnosticCheck(
            id="openclaw_connectivity_probe",
            status="fail",
            message="OpenClaw probe returned 403 Forbidden.",
            action="Grant token access to /v1/models and verify gateway authorization policy.",
        )
    return DiagnosticCheck(
        id="openclaw_connectivity_probe",
        status="fail",
        message=f"OpenClaw probe failed with HTTP {response.status_code}.",
        action="Verify gateway health and the OPENCLAW_BASE_URL path.",
    )


def _validate_url(value: str) -> object | None:
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None
    return parsed


def _parse_bool(value: str | None, *, default: bool) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _probe_timeout_seconds(raw_timeout_ms: str | None) -> float:
    try:
        timeout_ms = int((raw_timeout_ms or "").strip())
    except ValueError:
        timeout_ms = int(_DEFAULT_PROBE_TIMEOUT_SECONDS * 1000)
    clamped_ms = min(max(timeout_ms, 1000), 15000)
    return float(clamped_ms) / 1000.0


def _is_private_or_local_host(host: str) -> bool:
    candidate = host.strip().lower()
    if not candidate:
        return False
    if candidate in {"localhost", "127.0.0.1", "::1"}:
        return True
    if candidate.endswith(".local") or candidate.endswith(".internal"):
        return True

    try:
        ip = ipaddress.ip_address(candidate)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
    )

