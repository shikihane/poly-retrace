#!/usr/bin/env python3
"""Claude Code platform paths."""

from pathlib import Path
from typing import Iterable

from platforms.common import RetracePlatform, platform_home


class ClaudePlatform(RetracePlatform):
    def iter_session_files(self) -> Iterable[Path]:
        for root in self.session_roots:
            if not root.exists():
                continue
            for project_dir in root.iterdir():
                if project_dir.is_dir():
                    yield from project_dir.glob("*.jsonl")


def create_platform() -> RetracePlatform:
    home = platform_home("CLAUDE_HOME", ".claude")
    return ClaudePlatform(
        name="claude",
        home_dir=home,
        projects_dir=home / "projects",
        session_roots=(home / "projects",),
        command_names=("claude", "claude.cmd", "claude.ps1"),
    )
