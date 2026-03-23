from __future__ import annotations

import re
from typing import Any


def parse_csv_list(raw_value: str) -> list[str]:
    values: list[str] = []
    for item in re.split(r"[;,]", raw_value):
        candidate = item.strip()
        if candidate:
            values.append(candidate)
    return values


def split_semicolon_list(raw_value: str) -> list[str]:
    values: list[str] = []
    for item in raw_value.split(";"):
        candidate = item.strip()
        if candidate:
            values.append(candidate)
    return values


def read_section_text(markdown: str, section_name: str) -> str:
    header = f"## {section_name}"
    lines = markdown.splitlines()
    in_section = False
    collected: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_section:
                break
            in_section = stripped == header
            continue
        if in_section:
            collected.append(line.rstrip())
    return "\n".join(part for part in collected if part).strip()


def canonical_memory_key(raw_key: str, *, is_short_term_memory: bool = False) -> str:
    alias_map = {
        "current_scene": "current_scene_summary",
        "session_goal": "current_task_guess",
        "current_task": "current_task_guess",
        "last_updated": "updated_at_ms",
        "timestamp": "window_end_ts_ms" if is_short_term_memory else "updated_at_ms",
        "visible_text": "recent_visible_text",
        "documents_seen": "recent_documents",
        "source_frames": "source_frame_ids",
        "bootstrap_frame": "bootstrap_frame_id",
        "next_retry": "next_retry_at_ms",
        "last_attempt": "last_attempt_at_ms",
    }
    return alias_map.get(raw_key, raw_key)


def parse_managed_memory_markdown_payload(markdown: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    is_short_term_memory = "## Current View" in markdown

    current_view = read_section_text(markdown, "Current View")
    if current_view and current_view.lower() != "none":
        payload["current_scene_summary"] = current_view

    current_task = read_section_text(markdown, "Current Task Guess") or read_section_text(
        markdown,
        "Session Goal",
    )
    if current_task and current_task.lower() != "none":
        payload["current_task_guess"] = current_task

    summary_text = read_section_text(markdown, "What Happened")
    if summary_text and summary_text.lower() != "none":
        payload["summary_text"] = summary_text

    pending_follow_ups = read_section_text(markdown, "Pending Follow-Ups")
    if pending_follow_ups and pending_follow_ups.lower() != "none":
        payload["open_uncertainties"] = split_semicolon_list(pending_follow_ups)

    timestamp_text = read_section_text(markdown, "Timestamp")
    if timestamp_text and re.fullmatch(r"-?\d+", timestamp_text):
        payload["window_end_ts_ms"] = int(timestamp_text)

    updated_text = read_section_text(markdown, "Last Updated")
    if updated_text and re.fullmatch(r"-?\d+", updated_text):
        payload["updated_at_ms"] = int(updated_text)

    lines = [line.strip() for line in markdown.splitlines() if line.strip()]
    for line in lines:
        if not line.startswith("- ") or ":" not in line:
            continue
        key_raw, value_raw = line.removeprefix("- ").split(":", 1)
        key = key_raw.strip().lower().replace(" ", "_")
        value = value_raw.strip()
        if not value or value.lower() == "none":
            continue

        canonical_key = canonical_memory_key(
            key,
            is_short_term_memory=is_short_term_memory,
        )
        if canonical_key == "notable_transitions":
            payload[canonical_key] = split_semicolon_list(value)
            continue
        if key in {
            "source_frames",
            "recent_entities",
            "recent_actions",
            "visible_text",
            "documents_seen",
            "recurring_entities",
            "notable_transitions",
            "open_uncertainties",
        }:
            payload[canonical_key] = parse_csv_list(value)
            continue
        if re.fullmatch(r"-?\d+", value):
            payload[canonical_key] = int(value)
            continue
        payload[canonical_key] = value

    return payload
