#!/usr/bin/env python3
"""Kimi Code platform paths and Wire helpers."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Optional

from platforms.common import RetracePlatform, platform_home


class KimiPlatform(RetracePlatform):
    def iter_session_files(self) -> Iterable[Path]:
        for root in self.session_roots:
            if not root.exists():
                continue
            yield from root.glob("*/session_*/agents/*/wire.jsonl")


def epoch_ms_to_iso(value) -> str:
    """Convert a Kimi Wire epoch-millisecond timestamp to UTC ISO 8601."""
    try:
        timestamp = float(value) / 1000
    except (TypeError, ValueError):
        return str(value or "")
    return (
        datetime.fromtimestamp(timestamp, timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def content_text(content) -> str:
    """Extract text from Kimi message content without indexing thinking parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(filter(None, (content_text(item) for item in content)))
    if not isinstance(content, dict):
        return "" if content is None else str(content)
    if content.get("type") == "text":
        return str(content.get("text", ""))
    return ""


def session_dir_for_wire(wire_file: Path) -> Optional[Path]:
    """Return the session directory for a canonical Kimi Wire path."""
    wire_file = Path(wire_file)
    if wire_file.name != "wire.jsonl" or len(wire_file.parents) < 3:
        return None
    session_dir = wire_file.parents[2]
    if wire_file.parent.parent.name != "agents" or not session_dir.name.startswith("session_"):
        return None
    return session_dir


def read_session_state(wire_file: Path) -> dict:
    session_dir = session_dir_for_wire(wire_file)
    if not session_dir:
        return {}
    try:
        state = json.loads((session_dir / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return state if isinstance(state, dict) else {}


def session_id_for_wire(wire_file: Path) -> str:
    session_dir = session_dir_for_wire(wire_file)
    return session_dir.name.removeprefix("session_") if session_dir else ""


def agent_id_for_wire(wire_file: Path) -> str:
    return Path(wire_file).parent.name if session_dir_for_wire(wire_file) else ""


def normalize_session_meta(wire_file: Path) -> Optional[dict]:
    """Synthesize one indexable session record from Kimi state.json."""
    state = read_session_state(wire_file)
    session_id = session_id_for_wire(wire_file)
    if not state or not session_id:
        return None
    created_at = state.get("createdAt", "")
    if isinstance(created_at, (int, float)):
        created_at = epoch_ms_to_iso(created_at)
    work_dir = state.get("workDir", "")
    title = state.get("title", "")
    text = f"title={title} cwd={work_dir}".strip()
    return {
        "uuid": session_id,
        "parent_uuid": "",
        "session_id": session_id,
        "timestamp": str(created_at),
        "msg_type": "session_meta",
        "role": "",
        "tool_name": "",
        "agent_id": "main",
        "content_preview": text[:300],
        "search_text": text,
    }


def _result_text(result) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict) and isinstance(result.get("output"), str):
        return result["output"]
    return json.dumps(result, ensure_ascii=False) if result is not None else ""


def normalize_wire_record(
    data: dict,
    session_id: str = "",
    agent_id: str = "",
    tool_names: Optional[dict[str, str]] = None,
) -> Optional[dict]:
    """Normalize one Kimi Wire protocol event into retrace index fields."""
    record_type = data.get("type", "")
    timestamp = epoch_ms_to_iso(data.get("time"))

    if record_type == "context.append_message":
        message = data.get("message", {})
        if message.get("role") != "user":
            return None
        text = content_text(message.get("content"))
        if not text:
            return None
        return {
            "uuid": "",
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

    if record_type != "context.append_loop_event":
        return None

    event = data.get("event", {})
    event_type = event.get("type", "")
    if event_type == "content.part":
        part = event.get("part", {})
        if part.get("type") != "text":
            return None
        text = content_text(part)
        if not text:
            return None
        return {
            "uuid": event.get("uuid", ""),
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

    if event_type == "tool.call":
        arguments = json.dumps(event.get("args", {}), ensure_ascii=False)
        return {
            "uuid": event.get("uuid") or event.get("toolCallId", ""),
            "parent_uuid": "",
            "session_id": session_id,
            "timestamp": timestamp,
            "msg_type": "tool_use",
            "role": "assistant",
            "tool_name": event.get("name", ""),
            "agent_id": agent_id,
            "content_preview": arguments[:300],
            "search_text": arguments,
            "tool_call_id": event.get("toolCallId", ""),
        }

    if event_type == "tool.result":
        tool_call_id = event.get("toolCallId", "")
        text = _result_text(event.get("result"))
        return {
            "uuid": "",
            "parent_uuid": event.get("parentUuid", ""),
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
    home = platform_home("KIMI_CODE_HOME", ".kimi-code")
    return KimiPlatform(
        name="kimi",
        home_dir=home,
        projects_dir=home / "projects",
        session_roots=(home / "sessions",),
        command_names=("kimi", "kimi.cmd", "kimi.ps1"),
    )
