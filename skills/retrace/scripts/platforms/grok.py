#!/usr/bin/env python3
"""Grok CLI platform paths and ACP session update helpers."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import unquote

from platforms.common import RetracePlatform, platform_home


class GrokPlatform(RetracePlatform):
    def iter_session_files(self) -> Iterable[Path]:
        for root in self.session_roots:
            if not root.exists():
                continue
            yield from root.glob("*/*/updates.jsonl")


def _ms_to_iso(value) -> str:
    try:
        timestamp = float(value) / 1000
    except (TypeError, ValueError):
        return str(value or "")
    return (
        datetime.fromtimestamp(timestamp, timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def record_timestamp(data: dict) -> str:
    """Prefer the agent-side millisecond timestamp, fall back to the top-level seconds."""
    meta = data.get("params", {}).get("_meta", {})
    if isinstance(meta, dict) and meta.get("agentTimestampMs"):
        return _ms_to_iso(meta.get("agentTimestampMs"))
    try:
        timestamp = float(data.get("timestamp"))
    except (TypeError, ValueError):
        return str(data.get("timestamp") or "")
    return (
        datetime.fromtimestamp(timestamp, timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def session_dir_for_updates(updates_file: Path) -> Optional[Path]:
    """Return the session directory for a canonical Grok updates.jsonl path."""
    updates_file = Path(updates_file)
    if updates_file.name != "updates.jsonl" or len(updates_file.parents) < 2:
        return None
    session_dir = updates_file.parent
    if session_dir.parent.parent.name != "sessions":
        return None
    return session_dir


def session_id_for_file(updates_file: Path) -> str:
    session_dir = session_dir_for_updates(updates_file)
    return session_dir.name if session_dir else ""


def read_session_summary(updates_file: Path) -> dict:
    session_dir = session_dir_for_updates(updates_file)
    if not session_dir:
        return {}
    try:
        summary = json.loads((session_dir / "summary.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return summary if isinstance(summary, dict) else {}


def project_cwd(updates_file: Path) -> str:
    """Resolve the working directory for a Grok session file.

    Prefer summary.json info.cwd, then URL-decode the group directory name,
    then the group .cwd file written for over-long slug+hash names.
    """
    session_dir = session_dir_for_updates(updates_file)
    if not session_dir:
        return ""
    info = read_session_summary(updates_file).get("info", {})
    if isinstance(info, dict):
        cwd = info.get("cwd", "")
        if cwd:
            return str(cwd)
    group_dir = session_dir.parent
    decoded = unquote(group_dir.name)
    if decoded != group_dir.name and (":" in decoded or decoded.startswith("/")):
        return decoded
    try:
        cwd = (group_dir / ".cwd").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return cwd


def normalize_session_meta(updates_file: Path) -> Optional[dict]:
    """Synthesize one indexable session record from Grok summary.json."""
    summary = read_session_summary(updates_file)
    session_id = session_id_for_file(updates_file)
    if not summary or not session_id:
        return None
    info = summary.get("info", {})
    cwd = info.get("cwd", "") if isinstance(info, dict) else ""
    title = summary.get("generated_title") or summary.get("session_summary") or ""
    text = f"title={title} cwd={cwd}".strip()
    return {
        "uuid": session_id,
        "parent_uuid": str(summary.get("parent_session_id") or ""),
        "session_id": session_id,
        "timestamp": str(summary.get("created_at", "")),
        "msg_type": "session_meta",
        "role": "",
        "tool_name": "",
        "agent_id": "main",
        "content_preview": text[:300],
        "search_text": text,
    }


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(filter(None, (_content_text(item) for item in content)))
    if not isinstance(content, dict):
        return "" if content is None else str(content)
    if content.get("type") == "text":
        return str(content.get("text", ""))
    if content.get("type") == "content":
        return _content_text(content.get("content"))
    return ""


def _tool_name(update: dict) -> str:
    meta = update.get("_meta", {})
    if isinstance(meta, dict):
        tool_meta = meta.get("x.ai/tool", {})
        if isinstance(tool_meta, dict) and tool_meta.get("name"):
            return str(tool_meta["name"])
    return str(update.get("title") or "")


def _result_text(update: dict) -> str:
    text = _content_text(update.get("content"))
    if text:
        return text
    raw_output = update.get("rawOutput")
    if isinstance(raw_output, dict):
        for key in ("output_for_prompt", "output"):
            value = raw_output.get(key)
            if isinstance(value, str) and value:
                return value
    return json.dumps(raw_output, ensure_ascii=False) if raw_output else ""


def normalize_record(
    data: dict,
    session_id: str = "",
    agent_id: str = "",
    tool_names: Optional[dict[str, str]] = None,
) -> Optional[dict]:
    """Normalize one Grok ACP session update into retrace index fields."""
    if data.get("method") != "session/update":
        return None
    params = data.get("params", {})
    if not isinstance(params, dict):
        return None
    update = params.get("update", {})
    if not isinstance(update, dict):
        return None
    update_type = update.get("sessionUpdate", "")
    timestamp = record_timestamp(data)
    event_id = str(params.get("_meta", {}).get("eventId", ""))

    if update_type == "user_message_chunk":
        text = _content_text(update.get("content"))
        if not text:
            return None
        return {
            "uuid": event_id,
            "parent_uuid": "",
            "session_id": session_id,
            "timestamp": timestamp,
            "msg_type": "user",
            "role": "user",
            "tool_name": "",
            "agent_id": agent_id,
            "content_preview": text[:300],
            "search_text": text,
        }

    if update_type == "agent_message_chunk":
        text = _content_text(update.get("content"))
        if not text:
            return None
        return {
            "uuid": event_id,
            "parent_uuid": "",
            "session_id": session_id,
            "timestamp": timestamp,
            "msg_type": "assistant",
            "role": "assistant",
            "tool_name": "",
            "agent_id": agent_id,
            "content_preview": text[:300],
            "search_text": text,
        }

    if update_type == "tool_call":
        arguments = json.dumps(update.get("rawInput", {}), ensure_ascii=False)
        return {
            "uuid": event_id or update.get("toolCallId", ""),
            "parent_uuid": "",
            "session_id": session_id,
            "timestamp": timestamp,
            "msg_type": "tool_use",
            "role": "assistant",
            "tool_name": _tool_name(update),
            "agent_id": agent_id,
            "content_preview": arguments[:300],
            "search_text": arguments,
            "tool_call_id": update.get("toolCallId", ""),
        }

    if update_type == "tool_call_update":
        if not update.get("status"):
            return None
        tool_call_id = update.get("toolCallId", "")
        text = _result_text(update)
        if not text:
            return None
        return {
            "uuid": event_id,
            "parent_uuid": "",
            "session_id": session_id,
            "timestamp": timestamp,
            "msg_type": "tool_result",
            "role": "tool",
            "tool_name": (tool_names or {}).get(tool_call_id, ""),
            "agent_id": agent_id,
            "content_preview": text[:300],
            "search_text": text,
            "tool_call_id": tool_call_id,
        }

    return None


def create_platform() -> RetracePlatform:
    home = platform_home("GROK_HOME", ".grok")
    return GrokPlatform(
        name="grok",
        home_dir=home,
        projects_dir=home / "projects",
        session_roots=(home / "sessions",),
        command_names=("grok", "grok.cmd", "grok.exe"),
    )
