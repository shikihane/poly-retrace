#!/usr/bin/env python3
"""
Compatibility facade for platform-specific retrace paths.
"""

import json
import ntpath
import posixpath
import re
import shutil
import sys
from pathlib import Path
from typing import Iterable, Optional

from platforms import claude as claude_platform
from platforms import codex as codex_platform
from platforms import pi as pi_platform
from platforms.common import RetracePlatform


def configure_utf8_stdio() -> None:
    """Make script output robust on Windows consoles and captured shells."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def get_platform(platform: str = "codex") -> RetracePlatform:
    platform = (platform or "codex").lower()
    if platform == "codex":
        return codex_platform.create_platform()
    if platform == "claude":
        return claude_platform.create_platform()
    if platform == "pi":
        return pi_platform.create_platform()
    raise ValueError(f"unknown platform: {platform}")


def get_platforms(platform: str = "codex") -> list[RetracePlatform]:
    platform = (platform or "codex").lower()
    return [get_platform(platform)]


def get_codex_dir() -> Path:
    return get_platform("codex").home_dir


def get_projects_dir(platform: str = "codex") -> Path:
    return get_platform(platform).projects_dir


def get_session_roots(platform: str = "codex") -> list[Path]:
    return list(get_platform(platform).session_roots)


def encode_path(path: str) -> str:
    """Encode a filesystem path into a stable retrace project bucket name."""
    is_windows_path = sys.platform == "win32" or bool(re.match(r"^[A-Za-z]:[\\/]", path))
    normalized = ntpath.normpath(path) if is_windows_path else posixpath.normpath(path)
    if is_windows_path or ":" in normalized:
        encoded = (
            normalized.replace(":\\", "--")
            .replace(":", "--")
            .replace("\\", "-")
            .replace("/", "-")
        )
    else:
        encoded = normalized.replace("/", "-")
    return encoded.lstrip("-")


def decode_path(encoded: str, platform: str = "codex") -> str:
    """Best-effort decode for retrace project bucket names."""
    for session_file in iter_session_files(platform):
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                first = f.readline()
            if not first.strip():
                continue
            record = json.loads(first)
            payload = record.get("payload", {})
            cwd = record.get("cwd", "") or payload.get("cwd", "")
            if cwd and encode_path(cwd) == encoded:
                return cwd
        except Exception:
            continue

    if "--" in encoded:
        drive, rest = encoded.split("--", 1)
        if len(drive) == 1:
            decoded_rest = rest.replace("-", "\\")
            return f"{drive}:\\{decoded_rest}"
    return "/" + encoded.replace("-", "/")


def iter_session_files(platform: str = "codex") -> Iterable[Path]:
    """Yield session JSONL files for one platform or both platforms."""
    for retrace_platform in get_platforms(platform):
        yield from retrace_platform.iter_session_files()


def read_first_json_record(session_file: Path) -> dict:
    """Return the first non-empty JSON record from a JSONL session file."""
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                return json.loads(line)
    except Exception:
        pass
    return {}


def extract_session_id(record: dict) -> str:
    """Extract a session identifier from a JSONL record."""
    if not isinstance(record, dict):
        return ""
    if record.get("type") == "session":
        value = record.get("id")
        if value:
            return str(value)

    for key in ("sessionId", "session_id", "sessionID"):
        value = record.get(key)
        if value:
            return str(value)
    payload = record.get("payload")
    if isinstance(payload, dict):
        for key in ("id", "sessionId", "session_id"):
            value = payload.get(key)
            if value:
                return str(value)
    return ""


def extract_agent_id(record: dict) -> str:
    """Extract a Claude Code subagent identifier from a JSONL record."""
    if not isinstance(record, dict):
        return ""
    agent_id = record.get("agentId", "")
    return str(agent_id) if agent_id else ""


def session_file_session_id(session_file: Path, max_records: int = 5) -> str:
    """Best-effort session id lookup for a JSONL session file."""
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            checked = 0
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                session_id = extract_session_id(record)
                if session_id:
                    return session_id
                checked += 1
                if checked >= max_records:
                    break
    except Exception:
        pass
    return ""


def session_file_agent_id(session_file: Path, max_records: int = 5) -> str:
    """Best-effort Claude subagent id lookup for a JSONL session file."""
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            checked = 0
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                agent_id = extract_agent_id(record)
                if agent_id:
                    return agent_id
                checked += 1
                if checked >= max_records:
                    break
    except Exception:
        pass
    return ""


def find_session_files(session_id: str, platform: str = "codex") -> list[Path]:
    """Return all files that belong to a logical session id."""
    matches: list[Path] = []
    requested_agent_id = session_id.removeprefix("agent-")
    for session_file in iter_session_files(platform):
        if session_id in session_file.stem:
            matches.append(session_file)
            continue
        found_session_id = session_file_session_id(session_file)
        if found_session_id == session_id:
            matches.append(session_file)
            continue
        found_agent_id = session_file_agent_id(session_file)
        if found_agent_id and found_agent_id == requested_agent_id:
            matches.append(session_file)

    def sort_key(path: Path) -> tuple[int, int, str]:
        primary = 0 if path.stem == session_id or path.stem == f"agent-{requested_agent_id}" else 1
        sidecar = 1 if "subagents" in path.parts else 0
        return (primary, sidecar, str(path))

    return sorted(matches, key=sort_key)


def find_codex() -> Optional[str]:
    return get_platform("codex").find_command()


def find_platform_command(platform: str = "codex") -> Optional[str]:
    return get_platform(platform).find_command()


def find_pwsh() -> Optional[str]:
    return shutil.which("pwsh") or shutil.which("pwsh.exe")


def default_python_command() -> str:
    return "python" if sys.platform == "win32" else "python3"
