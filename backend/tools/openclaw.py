from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.tools.contracts import ToolCall, ToolResult
from backend.tools.openclaw_runtime import OpenClawDelegationRuntime
from backend.tools.results import tool_error, tool_ok

_MAX_TASK_CHARS = 4000


def _error(
    *,
    call: ToolCall,
    error_code: str,
    error_message: str,
    payload: dict[str, Any] | None = None,
) -> ToolResult:
    return tool_error(
        call=call,
        error_code=error_code,
        error_message=error_message,
        payload={} if payload is None else payload,
    )


@dataclass(frozen=True, slots=True)
class DelegateToOpenClawToolExecutor:
    runtime: OpenClawDelegationRuntime

    async def __call__(self, call: ToolCall) -> ToolResult:
        task = call.arguments.get("task")
        if not isinstance(task, str) or not task.strip():
            return _error(
                call=call,
                error_code="INVALID_TOOL_ARGUMENTS",
                error_message="delegate_to_openclaw requires a non-empty string `task` argument.",
            )
        normalized_task = task.strip()
        if len(normalized_task) > _MAX_TASK_CHARS:
            return _error(
                call=call,
                error_code="INVALID_TOOL_ARGUMENTS",
                error_message=f"delegate_to_openclaw `task` exceeds {_MAX_TASK_CHARS} characters.",
            )

        context_value = call.arguments.get("context")
        context: dict[str, Any] | None
        if context_value is None:
            context = None
        elif isinstance(context_value, dict):
            context = context_value
        else:
            return _error(
                call=call,
                error_code="INVALID_TOOL_ARGUMENTS",
                error_message="delegate_to_openclaw `context` must be an object when provided.",
            )

        agent_id = call.arguments.get("agent_id")
        if agent_id is not None and (not isinstance(agent_id, str) or not agent_id.strip()):
            return _error(
                call=call,
                error_code="INVALID_TOOL_ARGUMENTS",
                error_message="delegate_to_openclaw `agent_id` must be a non-empty string when provided.",
            )

        try:
            snapshot = await self.runtime.enqueue_task(
                session_id=call.session_id,
                prompt=normalized_task,
                context=context,
                requested_agent_id=agent_id.strip() if isinstance(agent_id, str) else None,
            )
        except RuntimeError as exc:
            return _error(
                call=call,
                error_code="OPENCLAW_ENQUEUE_FAILED",
                error_message=str(exc) or "Failed to enqueue OpenClaw task.",
            )

        payload = snapshot.to_payload()
        payload["queued"] = True
        return tool_ok(call=call, payload=payload)


@dataclass(frozen=True, slots=True)
class OpenClawTaskStatusToolExecutor:
    runtime: OpenClawDelegationRuntime

    async def __call__(self, call: ToolCall) -> ToolResult:
        task_id = call.arguments.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            return _error(
                call=call,
                error_code="INVALID_TOOL_ARGUMENTS",
                error_message="openclaw_task_status requires a non-empty string `task_id` argument.",
            )
        normalized_task_id = task_id.strip()
        snapshot = await self.runtime.get_task_status(normalized_task_id)
        if snapshot is None:
            return _error(
                call=call,
                error_code="OPENCLAW_TASK_NOT_FOUND",
                error_message="No OpenClaw task found for the requested task_id.",
                payload={"task_id": normalized_task_id},
            )
        return tool_ok(call=call, payload=snapshot.to_payload())


@dataclass(frozen=True, slots=True)
class OpenClawTaskCancelToolExecutor:
    runtime: OpenClawDelegationRuntime

    async def __call__(self, call: ToolCall) -> ToolResult:
        task_id = call.arguments.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            return _error(
                call=call,
                error_code="INVALID_TOOL_ARGUMENTS",
                error_message="openclaw_task_cancel requires a non-empty string `task_id` argument.",
            )
        normalized_task_id = task_id.strip()
        snapshot = await self.runtime.cancel_task(normalized_task_id)
        if snapshot is None:
            return _error(
                call=call,
                error_code="OPENCLAW_TASK_NOT_FOUND",
                error_message="No OpenClaw task found for the requested task_id.",
                payload={"task_id": normalized_task_id},
            )
        return tool_ok(call=call, payload=snapshot.to_payload())

