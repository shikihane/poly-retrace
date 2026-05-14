#!/usr/bin/env python3
"""Codex platform paths."""

from pathlib import Path
from typing import Iterable

from platforms.common import RetracePlatform, platform_home


class CodexPlatform(RetracePlatform):
    def iter_session_files(self) -> Iterable[Path]:
        for root in self.session_roots:
            if root.exists():
                yield from root.rglob("*.jsonl")


def create_platform() -> RetracePlatform:
    home = platform_home("CODEX_HOME", ".codex")
    return CodexPlatform(
        name="codex",
        home_dir=home,
        projects_dir=home / "projects",
        session_roots=(home / "sessions", home / "archived_sessions"),
        command_names=("codex", "codex.cmd", "codex.ps1"),
    )
