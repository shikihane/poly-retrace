#!/usr/bin/env python3
"""
Compatibility facade for platform-specific retrace paths.
"""

import json
import shutil
import sys
from pathlib import Path
from typing import Iterable, Optional

from platforms import claude as claude_platform
from platforms import codex as codex_platform
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
    import os

    normalized = os.path.normpath(path)
    if sys.platform == "win32" or ":" in normalized:
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
            cwd = payload.get("cwd", "")
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


def find_codex() -> Optional[str]:
    return get_platform("codex").find_command()


def find_platform_command(platform: str = "codex") -> Optional[str]:
    return get_platform(platform).find_command()


def find_pwsh() -> Optional[str]:
    return shutil.which("pwsh") or shutil.which("pwsh.exe")


def default_python_command() -> str:
    return "python"
