from __future__ import annotations

from typing import Any


def echo_context(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt": str(context.get("prompt") or ""),
        "transcript": str(context.get("transcript") or ""),
        "video_summary": str(context.get("video_summary") or ""),
    }


def detect_intent(context: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(
        [
            str(context.get("prompt") or ""),
            str(context.get("transcript") or ""),
            str(context.get("video_summary") or ""),
        ]
    ).lower()

    intents = {
        "question": any(word in text for word in ["quoi", "comment", "pourquoi", "?", "what", "how"]),
        "navigation": any(word in text for word in ["ou", "where", "direction", "route"]),
        "urgency": any(word in text for word in ["urgent", "help", "danger", "aide"]),
    }
    return {"detected": intents}
