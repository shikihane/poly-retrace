#!/usr/bin/env python3
"""Oh My Pi (OMP) platform paths and session helpers."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Iterable, Optional

from platforms.common import RetracePlatform, platform_home


class OmpPlatform(RetracePlatform):
    def iter_session_files(self) -> Iterable[Path]:
        for root in self.session_roots:
            if root.exists():
                yield from (
                    path for path in root.rglob("*.jsonl") if is_session_file(path)
                )


_PROFILE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def _active_profile() -> str:
    raw = (
        os.environ.get("OMP_PROFILE", "")
        if "OMP_PROFILE" in os.environ
        else os.environ.get("PI_PROFILE", "")
    ).strip()
    if not raw or raw == "default" or not _PROFILE_NAME_RE.fullmatch(raw):
        return ""
    return raw


def _agent_home() -> Path:
    """Mirror OMP's default/profile agent-directory selection on Windows."""
    profile = _active_profile()
    if not profile:
        return platform_home("PI_CODING_AGENT_DIR", ".omp/agent")
    config_name = os.environ.get("PI_CONFIG_DIR", ".omp")
    config_root = Path(config_name).expanduser()
    if not config_root.is_absolute():
        config_root = Path.home() / config_root
    return config_root / "profiles" / profile / "agent"


def _timestamp_to_iso(value) -> str:
    if isinstance(value, str):
        return value
    try:
        timestamp = float(value) / 1000
    except (TypeError, ValueError):
        return ""
    return (
        datetime.fromtimestamp(timestamp, timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def content_text(content) -> str:
    """Extract visible text while excluding thinking and image payloads."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(filter(None, (content_text(item) for item in content)))
    if not isinstance(content, dict):
        return ""
    if content.get("type") in {"text", "input_text", "output_text"}:
        return str(content.get("text", ""))
    return ""


def read_session_header(session_file: Path, max_records: int = 32) -> dict:
    """Return the OMP session header, skipping the optional title slot."""
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            checked = 0
            for line in f:
                if checked >= max_records:
                    break
                line = line.strip()
                if not line:
                    continue
                checked += 1
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("type") == "session" and record.get("id"):
                    return record
    except OSError:
        pass
    return {}


def is_session_file(session_file: Path) -> bool:
    return bool(read_session_header(session_file))


def session_id_for_file(session_file: Path) -> str:
    header = read_session_header(session_file)
    if header.get("id"):
        return str(header["id"])
    stem = Path(session_file).stem
    return stem.split("_", 1)[1] if "_" in stem else stem


def session_cwd(session_file: Path) -> str:
    return str(read_session_header(session_file).get("cwd", ""))


def parent_session_file(session_file: Path, max_depth: int = 8) -> Optional[Path]:
    """Return the parent JSONL whose artifact directory contains this file."""
    current = Path(session_file).resolve().parent
    for _ in range(max_depth):
        candidate = Path(f"{current}.jsonl")
        if candidate.is_file() and is_session_file(candidate):
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def is_root_session_file(session_file: Path) -> bool:
    """Whether a JSONL is an interactive/root session rather than an artifact."""
    return parent_session_file(session_file) is None


def root_session_file(session_file: Path) -> Path:
    """Walk an artifact transcript back to its interactive root JSONL."""
    current = Path(session_file).resolve()
    for _ in range(8):
        parent = parent_session_file(current)
        if parent is None:
            break
        current = parent
    return current


def project_cwd(session_file: Path) -> str:
    """Return the cwd recorded by this physical OMP session."""
    return session_cwd(session_file)


def agent_id_for_file(session_file: Path) -> str:
    """Return a stable unique task-run id, or ``main`` for a root session."""
    session_file = Path(session_file)
    if is_root_session_file(session_file):
        return "main"
    # OMP task agents persist to an artifact sidecar named `<run-id>.jsonl`.
    return session_file.stem or session_id_for_file(session_file) or "main"


def session_family_files(session_file: Path) -> list[Path]:
    """Return one session JSONL plus all nested task/advisor transcripts."""
    session_file = Path(session_file)
    files = [session_file]
    artifacts_dir = session_file.with_suffix("")
    if artifacts_dir.is_dir():
        files.extend(
            path
            for path in artifacts_dir.rglob("*.jsonl")
            if path.is_file() and is_session_file(path)
        )
    return sorted(
        set(files),
        key=lambda path: (
            0 if path == session_file else 1,
            len(path.parts),
            str(path),
        ),
    )


def matching_session_groups(
    session_id: str,
    session_files: Iterable[Path],
) -> dict[str, list[Path]]:
    """Match a full/partial physical session id without expanding families."""
    requested = session_id.strip().casefold()
    if not requested:
        return {}
    candidates = [Path(path) for path in session_files if is_session_file(Path(path))]

    def group(paths: Iterable[Path], key_for_path) -> dict[str, list[Path]]:
        grouped: dict[str, list[Path]] = {}
        for path in paths:
            key = str(key_for_path(path))
            grouped.setdefault(key.casefold(), []).append(path)
        return grouped

    exact_header = [
        path
        for path in candidates
        if session_id_for_file(path).casefold() == requested
    ]
    if exact_header:
        return group(exact_header, session_id_for_file)

    prefix_header = [
        path
        for path in candidates
        if session_id_for_file(path).casefold().startswith(requested)
    ]
    if prefix_header:
        # Interactive session prefixes are resolved against roots first. UUIDv7
        # task sessions created moments later commonly share a long prefix with
        # their parent and must not make the parent look ambiguous.
        root_matches = [path for path in prefix_header if is_root_session_file(path)]
        if root_matches:
            prefix_header = root_matches
        return group(prefix_header, session_id_for_file)
    return {}


def _base_record(data: dict, context: dict, msg_type: str, role: str) -> dict:
    return {
        "uuid": str(data.get("id", "")),
        "parent_uuid": str(data.get("parentId") or ""),
        "session_id": str(context.get("session_id", "")),
        "timestamp": _timestamp_to_iso(data.get("timestamp")),
        "msg_type": msg_type,
        "role": role,
        "tool_name": "",
        "agent_id": str(context.get("agent_id", "main")),
        "content_preview": "",
        "search_text": "",
    }


def _with_text(record: dict, text: str) -> dict:
    record["content_preview"] = text[:300]
    record["search_text"] = text
    return record


def normalize_record(data: dict, context: Optional[dict] = None) -> list[dict]:
    """Expand one OMP JSONL entry into normalized retrace messages."""
    if not isinstance(data, dict):
        return []
    context = context if context is not None else {}
    record_type = data.get("type", "")

    if record_type == "title":
        context["title"] = str(data.get("title", ""))
        return []

    if record_type == "session":
        session_id = str(data.get("id", ""))
        if not session_id:
            return []
        context["session_id"] = session_id
        context.setdefault("agent_id", "main")
        # OMP folds the mutable fixed-width title slot over the immutable
        # session header.  Presence matters here: an intentionally cleared
        # slot must also override a stale header title.
        title = (
            str(context.get("title") or "")
            if "title" in context
            else str(data.get("title") or "")
        )
        cwd = str(data.get("cwd", ""))
        text = f"title={title} cwd={cwd}".strip()
        record = _base_record(data, context, "session_meta", "")
        record["uuid"] = session_id
        return [_with_text(record, text)]

    if record_type == "session_init":
        context["agent_name"] = str(data.get("agent") or "")
        # Task agents persist the same task again as their first attributed
        # user message.  Keep session_init as context only to avoid indexing
        # every subagent task twice.
        return []

    if record_type == "custom_message":
        text = content_text(data.get("content"))
        if not text:
            return []
        role = "user" if data.get("attribution") == "user" else "assistant"
        record = _base_record(data, context, role, role)
        return [_with_text(record, text)]

    if record_type != "message":
        return []

    message = data.get("message", {})
    if not isinstance(message, dict):
        return []
    role = message.get("role", "")
    message_timestamp = _timestamp_to_iso(message.get("timestamp"))

    if role in {"user", "developer"}:
        text = content_text(message.get("content"))
        if not text:
            return []
        record = _base_record(data, context, "user", "user")
        record["timestamp"] = record["timestamp"] or message_timestamp
        return [_with_text(record, text)]

    if role == "toolResult":
        text = content_text(message.get("content"))
        if not text and message.get("isError"):
            text = "Tool execution failed"
        record = _base_record(data, context, "tool_result", "tool")
        record["timestamp"] = record["timestamp"] or message_timestamp
        record["uuid"] = str(message.get("toolCallId") or data.get("id", ""))
        record["tool_call_id"] = str(message.get("toolCallId", ""))
        record["tool_name"] = str(message.get("toolName", ""))
        return [_with_text(record, text)]

    if role != "assistant":
        return []

    normalized: list[dict] = []
    content = message.get("content", [])
    text = content_text(content)
    error_message = str(message.get("errorMessage") or "")
    if error_message:
        text = "\n".join(filter(None, (text, error_message)))
    if text:
        record = _base_record(data, context, "assistant", "assistant")
        record["timestamp"] = record["timestamp"] or message_timestamp
        normalized.append(_with_text(record, text))

    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "toolCall":
                continue
            tool_name = str(item.get("name", ""))
            arguments = item.get("arguments", {})
            if isinstance(arguments, str):
                argument_text = arguments
            else:
                argument_text = json.dumps(arguments, ensure_ascii=False)
            record = _base_record(data, context, "tool_use", "assistant")
            record["timestamp"] = record["timestamp"] or message_timestamp
            record["uuid"] = str(item.get("id") or data.get("id", ""))
            record["tool_call_id"] = str(item.get("id", ""))
            record["tool_name"] = tool_name
            normalized.append(_with_text(record, argument_text))

    return normalized


def normalize_session_meta(session_file: Path, max_records: int = 32) -> Optional[dict]:
    """Read the current title slot and header as one normalized session row."""
    context: dict = {
        "session_id": "",
        "agent_id": agent_id_for_file(session_file),
    }
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            checked = 0
            for line in f:
                if checked >= max_records:
                    break
                line = line.strip()
                if not line:
                    continue
                checked += 1
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for normalized in normalize_record(data, context):
                    if normalized.get("msg_type") == "session_meta":
                        return normalized
    except OSError:
        pass
    return None


def create_platform() -> RetracePlatform:
    home = _agent_home()
    session_override = os.environ.get("PI_CODING_AGENT_SESSION_DIR")
    sessions = Path(session_override).expanduser() if session_override else home / "sessions"
    return OmpPlatform(
        name="omp",
        home_dir=home,
        projects_dir=home / "projects",
        session_roots=(sessions,),
        command_names=("omp", "omp.exe", "omp.cmd", "omp.ps1"),
    )
