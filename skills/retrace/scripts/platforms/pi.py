#!/usr/bin/env python3
"""Pi platform paths."""

from pathlib import Path
from typing import Iterable

from platforms.common import RetracePlatform, platform_home


class PiPlatform(RetracePlatform):
    def iter_session_files(self) -> Iterable[Path]:
        for root in self.session_roots:
            if root.exists():
                yield from root.rglob("*.jsonl")


def create_platform() -> RetracePlatform:
    home = platform_home("PI_AGENT_HOME", ".pi/agent")
    return PiPlatform(
        name="pi",
        home_dir=home,
        projects_dir=home / "projects",
        session_roots=(home / "sessions",),
        command_names=("pi", "pi.cmd", "pi.ps1"),
    )
