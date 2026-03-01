from __future__ import annotations

import re
from typing import Any


def echo_context(context: dict[str, Any]) -> dict[str, Any]:
    """Lightweight echo: returns char-counts only.

    The full transcript and video_summary are already present as labelled
    sections in the main LLM user message, so we must NOT repeat them here
    or the LLM context will contain duplicates.
    """
    transcript = str(context.get("transcript") or "")
    video_summary = str(context.get("video_summary") or "")
    return {
        "transcript_chars": len(transcript),
        "video_summary_chars": len(video_summary),
        "has_transcript": bool(transcript.strip()),
        "has_video": bool(video_summary.strip()),
    }


def detect_intent(context: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(
        [
            str(context.get("prompt") or ""),
            str(context.get("transcript") or ""),
            str(context.get("video_summary") or ""),
        ]
    ).lower()

    def _match_any(words: list[str]) -> bool:
        return any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in words)

    intents = {
        "question": _match_any(["quoi", "comment", "pourquoi", "what", "how", "why", "when", "who"]) or "?" in text,
        "navigation": _match_any(["où", "ou", "where", "direction", "route", "navigate", "aller", "go to"]),
        "urgency": _match_any(["urgent", "help", "danger", "aide", "emergency", "secours"]),
    }
    return {"detected": intents}
