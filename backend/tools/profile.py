from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any

from backend.core.storage import BackendStorage
from backend.memory.lifecycle import PROFILE_METADATA_KEY, allowed_profile_fields
from backend.tools.contracts import ToolCall, ToolResult

logger = logging.getLogger(__name__)
ONBOARDING_REQUIRED_FIELDS = (
    "name",
    "job",
    "company",
    "preferred_language",
    "location",
    "intended_use",
    "preferences",
    "projects",
)


@dataclass(frozen=True, slots=True)
class ProfileToolExecutor:
    storage: BackendStorage
    mode: str

    async def __call__(self, call: ToolCall) -> ToolResult:
        try:
            if self.mode == "get":
                profile_payload = await asyncio.to_thread(self.storage.read_user_profile)
            elif self.mode == "update":
                profile_payload = await asyncio.to_thread(
                    self._update_profile,
                    call.arguments,
                )
            elif self.mode == "complete":
                profile_payload = await asyncio.to_thread(self.storage.read_user_profile)
            else:
                raise ValueError(f"Unsupported profile tool mode: {self.mode}")
        except (JSONDecodeError, OSError, ValueError) as exc:
            logger.warning(
                "Profile tool failed session_id=%s call_id=%s mode=%s",
                call.session_id,
                call.call_id,
                self.mode,
                exc_info=exc,
            )
            return ToolResult(
                ok=False,
                name=call.name,
                call_id=call.call_id,
                payload={
                    "session_id": call.session_id,
                    "profile": {},
                    "missing_fields": list(allowed_profile_fields()),
                },
                error_code="PROFILE_TOOL_FAILED",
                error_message="Profile tool failed",
            )

        profile = {
            field_name: profile_payload[field_name]
            for field_name in allowed_profile_fields()
            if field_name in profile_payload
        }
        present_fields = set(profile.keys())
        metadata = profile_payload.get(PROFILE_METADATA_KEY)
        if not isinstance(metadata, dict):
            metadata = {}

        payload = {
            "session_id": call.session_id,
            "profile": profile,
            "missing_fields": [
                field_name
                for field_name in allowed_profile_fields()
                if field_name not in present_fields
            ],
            "metadata": metadata,
        }
        if self.mode == "complete":
            missing_required_fields = [
                field_name
                for field_name in ONBOARDING_REQUIRED_FIELDS
                if field_name not in present_fields
            ]
            payload["ready"] = not missing_required_fields
            payload["missing_required_fields"] = missing_required_fields

        return ToolResult(
            ok=True,
            name=call.name,
            call_id=call.call_id,
            payload=payload,
        )

    def _update_profile(self, arguments: dict[str, Any]) -> dict[str, object]:
        current = self.storage.read_user_profile()
        merged = dict(current)

        for field_name in allowed_profile_fields():
            if field_name in arguments:
                merged[field_name] = arguments[field_name]

        return self.storage.write_user_profile(
            payload=merged,
            source="tool_update_user_profile",
        )
