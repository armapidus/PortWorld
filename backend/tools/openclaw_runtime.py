from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
import json
import logging
import re
import time
from typing import Any
from urllib.parse import urljoin
from uuid import uuid4

import httpx

from backend.core.settings import Settings

logger = logging.getLogger(__name__)

OPENCLAW_TASK_STATE_QUEUED = "queued"
OPENCLAW_TASK_STATE_RUNNING = "running"
OPENCLAW_TASK_STATE_SUCCEEDED = "succeeded"
OPENCLAW_TASK_STATE_FAILED = "failed"
OPENCLAW_TASK_STATE_CANCELLED = "cancelled"

_TERMINAL_TASK_STATES = frozenset(
    {
        OPENCLAW_TASK_STATE_SUCCEEDED,
        OPENCLAW_TASK_STATE_FAILED,
        OPENCLAW_TASK_STATE_CANCELLED,
    }
)

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]+")
_AUTHORIZATION_RE = re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+")
_BEARER_TOKEN_RE = re.compile(r"(?i)(bearer\s+)[^\s]+")
_TOKEN_FIELD_RE = re.compile(r"(?i)(token|api[_-]?key|authorization)\s*[:=]\s*([^\s,;]+)")

_MAX_SUMMARY_CHARS = 240
_MAX_RESULT_PREVIEW_CHARS = 1200
_DEFAULT_AGENT_ID = "openclaw/default"


def _now_epoch_seconds() -> float:
    return time.time()


def _coerce_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    return candidate or None


def normalize_agent_id(value: str | None) -> str:
    candidate = (value or "").strip()
    if not candidate:
        return _DEFAULT_AGENT_ID

    lowered = candidate.lower()
    if lowered == "openclaw":
        return "openclaw"

    if lowered.startswith("openclaw/"):
        suffix = candidate.split("/", 1)[1].strip()
        if not suffix:
            return _DEFAULT_AGENT_ID
        return f"openclaw/{suffix}"

    return f"openclaw/{candidate}"


def sanitize_text(text: str, *, max_chars: int) -> str:
    cleaned = _CONTROL_CHAR_RE.sub(" ", text)
    cleaned = cleaned.replace("\r", " ").replace("\n", " ")
    cleaned = _AUTHORIZATION_RE.sub(r"\1<redacted>", cleaned)
    cleaned = _BEARER_TOKEN_RE.sub(r"\1<redacted>", cleaned)
    cleaned = _TOKEN_FIELD_RE.sub(r"\1=<redacted>", cleaned)
    normalized = " ".join(cleaned.split()).strip()
    if len(normalized) > max_chars:
        return normalized[: max_chars - 3].rstrip() + "..."
    return normalized


def build_summary(text: str) -> str:
    candidate = sanitize_text(text, max_chars=_MAX_SUMMARY_CHARS)
    if not candidate:
        return "OpenClaw task completed."
    return candidate


def build_result_preview(text: str) -> str:
    return sanitize_text(text, max_chars=_MAX_RESULT_PREVIEW_CHARS)


def _extract_error_message(payload: Any) -> str | None:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            for key in ("message", "detail", "error"):
                value = _coerce_text(error.get(key))
                if value:
                    return value
        for key in ("message", "detail", "error"):
            value = _coerce_text(payload.get(key))
            if value:
                return value
    return None


def _extract_output_text(payload: dict[str, Any]) -> str:
    direct_output = _coerce_text(payload.get("output_text"))
    if direct_output:
        return direct_output

    content_segments: list[str] = []
    output_items = payload.get("output")
    if isinstance(output_items, list):
        for item in output_items:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, list):
                for entry in content:
                    if not isinstance(entry, dict):
                        continue
                    text = _coerce_text(entry.get("text")) or _coerce_text(entry.get("output_text"))
                    if text:
                        content_segments.append(text)
            text = _coerce_text(item.get("text"))
            if text:
                content_segments.append(text)

    if content_segments:
        return "\n".join(content_segments)

    serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    return serialized


@dataclass(frozen=True, slots=True)
class OpenClawTaskSnapshot:
    task_id: str
    state: str
    submitted_at: float
    updated_at: float
    error_code: str | None
    summary: str | None
    result_preview: str | None
    agent_id: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "state": self.state,
            "submitted_at": self.submitted_at,
            "updated_at": self.updated_at,
            "error_code": self.error_code,
            "summary": self.summary,
            "result_preview": self.result_preview,
            "agent_id": self.agent_id,
        }


@dataclass(slots=True)
class _OpenClawTaskRecord:
    task_id: str
    session_id: str
    state: str
    submitted_at: float
    updated_at: float
    error_code: str | None
    summary: str | None
    result_preview: str | None
    agent_id: str
    request_payload: dict[str, Any]
    worker_task: asyncio.Task[None] | None = None

    def snapshot(self) -> OpenClawTaskSnapshot:
        return OpenClawTaskSnapshot(
            task_id=self.task_id,
            state=self.state,
            submitted_at=self.submitted_at,
            updated_at=self.updated_at,
            error_code=self.error_code,
            summary=self.summary,
            result_preview=self.result_preview,
            agent_id=self.agent_id,
        )


class OpenClawRequestError(RuntimeError):
    def __init__(self, *, error_code: str, message: str) -> None:
        self.error_code = error_code
        self.message = message
        super().__init__(message)


class OpenClawDelegationRuntime:
    def __init__(
        self,
        *,
        enabled: bool,
        base_url: str | None,
        auth_token: str | None,
        agent_id: str,
        request_timeout_ms: int,
        task_ttl_seconds: int,
        max_concurrent_tasks: int,
    ) -> None:
        self._enabled = enabled
        self._base_url = (base_url or "").strip().rstrip("/")
        self._auth_token = (auth_token or "").strip()
        self._agent_id = normalize_agent_id(agent_id)
        self._request_timeout_seconds = max(1.0, float(request_timeout_ms) / 1000.0)
        self._task_ttl_seconds = max(60, int(task_ttl_seconds))
        self._semaphore = asyncio.Semaphore(max(1, int(max_concurrent_tasks)))
        self._tasks: dict[str, _OpenClawTaskRecord] = {}
        self._lock = asyncio.Lock()
        self._client: httpx.AsyncClient | None = None
        self._worker_tasks: set[asyncio.Task[None]] = set()
        self._cleanup_task: asyncio.Task[None] | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenClawDelegationRuntime | None:
        if not settings.openclaw_enabled:
            return None
        return cls(
            enabled=settings.openclaw_enabled,
            base_url=settings.openclaw_base_url,
            auth_token=settings.openclaw_auth_token,
            agent_id=settings.openclaw_agent_id,
            request_timeout_ms=settings.openclaw_request_timeout_ms,
            task_ttl_seconds=settings.openclaw_task_ttl_seconds,
            max_concurrent_tasks=settings.openclaw_max_concurrent_tasks,
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def configured(self) -> bool:
        return bool(self._base_url and self._auth_token)

    async def startup(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._request_timeout_seconds)
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(
                self._cleanup_loop(),
                name="openclaw-task-registry-cleanup",
            )

    async def shutdown(self) -> None:
        worker_tasks = tuple(self._worker_tasks)
        for worker_task in worker_tasks:
            worker_task.cancel()
        if worker_tasks:
            await asyncio.gather(*worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()

        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
            self._cleanup_task = None

        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def enqueue_task(
        self,
        *,
        session_id: str,
        prompt: str,
        context: dict[str, Any] | None,
        requested_agent_id: str | None,
    ) -> OpenClawTaskSnapshot:
        await self._purge_expired_terminal_tasks()

        now = _now_epoch_seconds()
        task_id = uuid4().hex
        agent_id = normalize_agent_id(requested_agent_id or self._agent_id)
        request_payload = self._build_request_payload(
            task_id=task_id,
            session_id=session_id,
            prompt=prompt,
            context=context,
            agent_id=agent_id,
        )

        record = _OpenClawTaskRecord(
            task_id=task_id,
            session_id=session_id,
            state=OPENCLAW_TASK_STATE_QUEUED,
            submitted_at=now,
            updated_at=now,
            error_code=None,
            summary="Task queued.",
            result_preview=None,
            agent_id=agent_id,
            request_payload=request_payload,
        )

        async with self._lock:
            self._tasks[task_id] = record

        worker_task = asyncio.create_task(
            self._run_task(task_id),
            name=f"openclaw-task-{task_id[:8]}",
        )
        record.worker_task = worker_task
        self._worker_tasks.add(worker_task)
        worker_task.add_done_callback(self._worker_tasks.discard)
        return record.snapshot()

    async def get_task_status(self, task_id: str) -> OpenClawTaskSnapshot | None:
        await self._purge_expired_terminal_tasks()
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return None
            return record.snapshot()

    async def cancel_task(self, task_id: str) -> OpenClawTaskSnapshot | None:
        await self._purge_expired_terminal_tasks()
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return None
            if record.state in _TERMINAL_TASK_STATES:
                return record.snapshot()
            record.state = OPENCLAW_TASK_STATE_CANCELLED
            record.error_code = "OPENCLAW_TASK_CANCELLED"
            record.summary = "Task cancelled."
            record.updated_at = _now_epoch_seconds()
            worker_task = record.worker_task

        if worker_task is not None and not worker_task.done():
            worker_task.cancel()
        return record.snapshot()

    async def _run_task(self, task_id: str) -> None:
        await self._set_task_running(task_id)
        try:
            async with self._semaphore:
                payload = await self._execute_request(task_id)
        except asyncio.CancelledError:
            await self._set_task_cancelled(task_id)
            raise
        except OpenClawRequestError as exc:
            await self._set_task_failed(
                task_id,
                error_code=exc.error_code,
                summary=exc.message,
            )
            return
        except Exception:  # pragma: no cover - defensive fallback
            logger.exception("OpenClaw task failed task_id=%s", task_id)
            await self._set_task_failed(
                task_id,
                error_code="OPENCLAW_TASK_FAILED",
                summary="OpenClaw task failed unexpectedly.",
            )
            return

        output_text = _extract_output_text(payload)
        await self._set_task_succeeded(
            task_id,
            output_text=output_text,
        )

    async def _set_task_running(self, task_id: str) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None or record.state in _TERMINAL_TASK_STATES:
                return
            record.state = OPENCLAW_TASK_STATE_RUNNING
            record.summary = "Task running."
            record.updated_at = _now_epoch_seconds()

    async def _set_task_succeeded(self, task_id: str, *, output_text: str) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None or record.state in _TERMINAL_TASK_STATES:
                return
            record.state = OPENCLAW_TASK_STATE_SUCCEEDED
            record.error_code = None
            record.summary = build_summary(output_text)
            record.result_preview = build_result_preview(output_text)
            record.updated_at = _now_epoch_seconds()

    async def _set_task_failed(
        self,
        task_id: str,
        *,
        error_code: str,
        summary: str,
    ) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None or record.state in _TERMINAL_TASK_STATES:
                return
            record.state = OPENCLAW_TASK_STATE_FAILED
            record.error_code = error_code
            record.summary = build_summary(summary)
            record.result_preview = None
            record.updated_at = _now_epoch_seconds()

    async def _set_task_cancelled(self, task_id: str) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return
            record.state = OPENCLAW_TASK_STATE_CANCELLED
            record.error_code = "OPENCLAW_TASK_CANCELLED"
            record.summary = "Task cancelled."
            record.updated_at = _now_epoch_seconds()

    async def _execute_request(self, task_id: str) -> dict[str, Any]:
        if not self.configured:
            raise OpenClawRequestError(
                error_code="OPENCLAW_NOT_CONFIGURED",
                message="OpenClaw is enabled but OPENCLAW_BASE_URL or OPENCLAW_AUTH_TOKEN is missing.",
            )
        if self._client is None:
            raise OpenClawRequestError(
                error_code="OPENCLAW_RUNTIME_NOT_READY",
                message="OpenClaw runtime is not ready yet.",
            )

        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                raise OpenClawRequestError(
                    error_code="OPENCLAW_TASK_NOT_FOUND",
                    message="OpenClaw task is no longer available.",
                )
            request_payload = dict(record.request_payload)

        request_url = urljoin(f"{self._base_url}/", "v1/responses")
        try:
            response = await self._client.post(
                request_url,
                headers={
                    "Authorization": f"Bearer {self._auth_token}",
                    "Content-Type": "application/json",
                },
                json=request_payload,
            )
        except httpx.TimeoutException as exc:
            raise OpenClawRequestError(
                error_code="OPENCLAW_TIMEOUT",
                message="OpenClaw request timed out.",
            ) from exc
        except httpx.HTTPError as exc:
            raise OpenClawRequestError(
                error_code="OPENCLAW_UNREACHABLE",
                message="OpenClaw gateway is unreachable.",
            ) from exc

        if response.status_code >= 400:
            try:
                error_payload = response.json()
            except ValueError:
                error_payload = None
            error_message = _extract_error_message(error_payload) or (
                f"OpenClaw gateway responded with HTTP {response.status_code}."
            )
            if response.status_code == 401:
                error_code = "OPENCLAW_UNAUTHORIZED"
            elif response.status_code == 403:
                error_code = "OPENCLAW_FORBIDDEN"
            elif response.status_code == 404:
                error_code = "OPENCLAW_NOT_FOUND"
            elif response.status_code >= 500:
                error_code = "OPENCLAW_UPSTREAM_ERROR"
            else:
                error_code = "OPENCLAW_REQUEST_FAILED"
            raise OpenClawRequestError(
                error_code=error_code,
                message=build_summary(error_message),
            )

        try:
            response_payload = response.json()
        except ValueError as exc:
            raise OpenClawRequestError(
                error_code="OPENCLAW_BAD_RESPONSE",
                message="OpenClaw gateway returned invalid JSON.",
            ) from exc
        if not isinstance(response_payload, dict):
            raise OpenClawRequestError(
                error_code="OPENCLAW_BAD_RESPONSE",
                message="OpenClaw gateway returned an unexpected response payload.",
            )
        return response_payload

    async def _cleanup_loop(self) -> None:
        interval_seconds = min(60, max(5, self._task_ttl_seconds // 3))
        while True:
            try:
                await asyncio.sleep(float(interval_seconds))
                await self._purge_expired_terminal_tasks()
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover - defensive fallback
                logger.exception("OpenClaw task cleanup loop failed")

    async def _purge_expired_terminal_tasks(self) -> None:
        now = _now_epoch_seconds()
        async with self._lock:
            expired_ids = [
                task_id
                for task_id, record in self._tasks.items()
                if record.state in _TERMINAL_TASK_STATES
                and (now - record.updated_at) >= float(self._task_ttl_seconds)
            ]
            for task_id in expired_ids:
                self._tasks.pop(task_id, None)

    @staticmethod
    def _build_request_payload(
        *,
        task_id: str,
        session_id: str,
        prompt: str,
        context: dict[str, Any] | None,
        agent_id: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": agent_id,
            "input": prompt,
            "metadata": {
                "source": "portworld",
                "task_id": task_id,
                "session_id": session_id,
            },
        }
        if context:
            payload["metadata"]["context"] = context
        return payload
