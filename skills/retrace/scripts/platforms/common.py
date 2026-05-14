#!/usr/bin/env python3
"""Common platform primitives."""

from dataclasses import dataclass
import os
import shutil
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class RetracePlatform:
    name: str
    home_dir: Path
    projects_dir: Path
    session_roots: tuple[Path, ...]
    command_names: tuple[str, ...]

    def iter_session_files(self) -> Iterable[Path]:
        raise NotImplementedError

    def find_command(self) -> Optional[str]:
        for name in self.command_names:
            found = shutil.which(name)
            if found:
                return found
        return None


def platform_home(env_name: str, default_name: str) -> Path:
    override = os.environ.get(env_name)
    if override:
        return Path(override).expanduser()
    return Path.home() / default_name
