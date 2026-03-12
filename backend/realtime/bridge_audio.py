from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
from typing import Any

from backend.realtime.client import RealtimeClientError
from backend.ws.contracts import now_ms
from backend.ws.frame_codec import SERVER_AUDIO_FRAME_TYPE

logger = logging.getLogger(__name__)


class BridgeAudioMixin:
    _client_audio_sender_task: asyncio.Task[None] | None
    _client_audio_queue: asyncio.Queue[bytes | None]
    _client_audio_dropped_oldest_count: int
    _client_audio_drop_log_step: int
    _client_audio_sent_count: int
    _current_response_id: str | None
    _cancelled_response_ids: set[str]
    _started_response_ids: set[str]
    _last_stopped_response_id: str | None
    _send_binary_frame: Any
    _session_id: str
    _upstream_client: Any
    _dump_input_audio_enabled: bool
    _audio_dump: Any

    def _ensure_client_audio_sender_task(self) -> None:
        task = self._client_audio_sender_task
        if task is not None and not task.done():
            return

        self._client_audio_sender_task = asyncio.create_task(
            self._run_client_audio_sender_loop(),
            name=f"client_audio_sender:{self._session_id}",
        )

    def _enqueue_client_audio(self, payload_bytes: bytes) -> None:
        while True:
            try:
                self._client_audio_queue.put_nowait(payload_bytes)
                return
            except asyncio.QueueFull:
                try:
                    self._client_audio_queue.get_nowait()
                except asyncio.QueueEmpty:
                    logger.debug(
                        "Client audio queue unexpectedly empty during overflow handling session=%s",
                        self._session_id,
                    )
                    continue
                else:
                    self._client_audio_queue.task_done()

                self._client_audio_dropped_oldest_count += 1
                drop_count = self._client_audio_dropped_oldest_count
                if (
                    drop_count == 1
                    or drop_count % self._client_audio_drop_log_step == 0
                ):
                    logger.warning(
                        "Client audio queue overflow session=%s policy=drop_oldest dropped=%s queue_max=%s",
                        self._session_id,
                        drop_count,
                        self._client_audio_queue.maxsize,
                    )

    async def _run_client_audio_sender_loop(self) -> None:
        try:
            while True:
                payload_bytes = await self._client_audio_queue.get()
                try:
                    if payload_bytes is None:
                        return
                    await self._upstream_client.send_json(
                        {
                            "type": "input_audio_buffer.append",
                            "audio": base64.b64encode(payload_bytes).decode("ascii"),
                        }
                    )
                    self._client_audio_sent_count += 1
                finally:
                    self._client_audio_queue.task_done()
        except asyncio.CancelledError:
            raise
        except RealtimeClientError as exc:
            logger.warning(
                "Client audio sender closed for %s: %s",
                self._session_id,
                exc,
            )
        except Exception:
            logger.exception(
                "Unexpected client audio sender failure for %s",
                self._session_id,
            )

    async def _shutdown_client_audio_sender(self) -> None:
        task = self._client_audio_sender_task
        self._client_audio_sender_task = None
        if task is None:
            return

        if not task.done():
            enqueued_stop = False
            while not enqueued_stop:
                try:
                    self._client_audio_queue.put_nowait(None)
                    enqueued_stop = True
                except asyncio.QueueFull:
                    try:
                        self._client_audio_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    else:
                        self._client_audio_queue.task_done()
                        self._client_audio_dropped_oldest_count += 1
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except asyncio.TimeoutError:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        else:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _on_audio_delta(self, event: dict[str, Any]) -> None:
        delta_b64 = event.get("delta")
        if not isinstance(delta_b64, str) or not delta_b64:
            return

        response_id = self._resolve_response_id(event)
        if response_id in self._cancelled_response_ids:
            logger.warning(
                "Ignoring late audio delta for cancelled response session=%s response_id=%s",
                self._session_id,
                response_id,
            )
            return
        if response_id not in self._started_response_ids:
            self._started_response_ids.add(response_id)
            if self._last_stopped_response_id == response_id:
                self._last_stopped_response_id = None
            await self._send_envelope(
                "assistant.playback.control",
                {"command": "start_response", "response_id": response_id},
            )

        self._current_response_id = response_id

        try:
            pcm_bytes = base64.b64decode(delta_b64, validate=True)
        except (ValueError, TypeError):
            logger.warning(
                "Invalid base64 audio delta for session=%s", self._session_id
            )
            return

        await self._send_binary_frame(SERVER_AUDIO_FRAME_TYPE, now_ms(), pcm_bytes)

    async def _wait_for_client_audio_queue_drain(self) -> None:
        task = self._client_audio_sender_task
        if task is None or task.done():
            return

        try:
            await asyncio.wait_for(self._client_audio_queue.join(), timeout=1.5)
        except asyncio.TimeoutError:
            logger.warning(
                "Timed out draining client audio queue session=%s pending=%s",
                self._session_id,
                self._client_audio_queue.qsize(),
            )

    def _resolve_response_id(self, event: dict[str, Any]) -> str:
        resolved = self._extract_response_id(event)
        if resolved is not None:
            return resolved
        if self._current_response_id is not None:
            return self._current_response_id
        fallback = f"response_{now_ms()}"
        self._current_response_id = fallback
        return fallback

    @staticmethod
    def _extract_response_id(event: dict[str, Any]) -> str | None:
        direct = event.get("response_id")
        if isinstance(direct, str) and direct:
            return direct

        response = event.get("response")
        if isinstance(response, dict):
            rid = response.get("id")
            if isinstance(rid, str) and rid:
                return rid

        return None

    def _append_input_audio_dump(self, payload_bytes: bytes) -> None:
        if not self._dump_input_audio_enabled:
            return
        self._audio_dump.append(payload_bytes)
