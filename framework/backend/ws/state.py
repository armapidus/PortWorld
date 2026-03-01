"""In-memory session state for WebSocket connections.

This module provides a simple registry mapping session_id -> WebSocket connection.
The HTTP /v1/query endpoint uses this to find where to push audio back.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """State for a connected iOS session."""
    session_id: str
    websocket: "WebSocket"
    connected_at: float = field(default_factory=time.time)
    outbound_seq: int = 0

    def next_seq(self) -> int:
        """Get next outbound sequence number."""
        self.outbound_seq += 1
        return self.outbound_seq


# Global registry: session_id -> SessionState
_sessions: dict[str, SessionState] = {}
_lock = asyncio.Lock()


async def register_session(session_id: str, websocket: "WebSocket") -> SessionState:
    """Register a WebSocket connection for a session.
    
    If a session with this ID already exists, the old connection is replaced.
    """
    async with _lock:
        if session_id in _sessions:
            logger.info(f"Replacing existing session {session_id}")
        state = SessionState(session_id=session_id, websocket=websocket)
        _sessions[session_id] = state
        logger.info(f"Registered session {session_id}, total sessions: {len(_sessions)}")
        return state


async def unregister_session(session_id: str) -> None:
    """Unregister a session."""
    async with _lock:
        if session_id in _sessions:
            del _sessions[session_id]
            logger.info(f"Unregistered session {session_id}, total sessions: {len(_sessions)}")


def get_session(session_id: str) -> SessionState | None:
    """Get session state by ID (non-async for convenience)."""
    return _sessions.get(session_id)


def get_websocket(session_id: str) -> "WebSocket | None":
    """Get the WebSocket connection for a session."""
    state = _sessions.get(session_id)
    return state.websocket if state else None


def get_all_sessions() -> dict[str, SessionState]:
    """Get a shallow copy of all sessions (for debugging)."""
    return dict(_sessions)
