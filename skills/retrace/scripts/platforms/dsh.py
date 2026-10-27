#!/usr/bin/env python3
"""DeepSeek Harness V4 session discovery, decoding, and event normalization."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import ntpath
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Iterable

from platforms.common import RetracePlatform


LOG_NAME = re.compile(r"session(?:\.v([1-9][0-9]*))?\.jsonl(?:\.zstd)?\Z")


def is_session_file(path: Path) -> bool:
    match = LOG_NAME.fullmatch(Path(path).name)
    # Unversioned plaintext session.jsonl is also a common non-DSH filename.
    return bool(match and (match.group(1) is not None or Path(path).suffix == ".zstd"))


@contextmanager
def open_binary(path: Path):
    """Read source bytes; offsets always refer to the uncompressed JSONL stream."""
    path = Path(path)
    if path.suffix != ".zstd":
        with path.open("rb") as stream:
            yield stream
        return
    try:
        from compression import zstd
    except ImportError:
        try:
            import zstandard
        except ImportError as exc:
            raise RuntimeError(
                "DSH Zstandard logs require Python 3.14+ or: python -m pip install zstandard"
            ) from exc
        with path.open("rb") as source:
            with zstandard.ZstdDecompressor().stream_reader(
                source, read_across_frames=True
            ) as reader:
                # The fallback reader cannot seek or read lines; spool large logs to disk.
                with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as stream:
                    shutil.copyfileobj(reader, stream)
                    stream.seek(0)
                    yield stream
    else:
        with zstd.open(path, "rb") as stream:
            yield stream


def read_header(path: Path) -> dict:
    with open_binary(path) as stream:
        line = stream.readline()
    if not line.endswith(b"\n"):
        raise ValueError(f"Incomplete DSH session header: {path}")
    header = json.loads(line)
    if not isinstance(header, dict) or header.get("type") != "session":
        raise ValueError(f"Invalid DSH session header: {path}")
    version = header.get("version")
    if type(version) is not int or version != 4:
        raise ValueError(f"Unsupported DSH session format {version!r}; only V4 is supported: {path}")
    match = LOG_NAME.fullmatch(Path(path).name)
    if not match or int(match.group(1) or 0) != version:
        raise ValueError(f"DSH session filename/header version mismatch: {path}")
    if not isinstance(header.get("id"), str) or not header["id"]:
        raise ValueError(f"Missing DSH session id: {path}")
    cwd = header.get("cwd")
    if cwd is not None and (not isinstance(cwd, str) or not ntpath.isabs(cwd)):
        raise ValueError(f"Invalid DSH session cwd: {path}")
    return header


class DshPlatform(RetracePlatform):
    def iter_session_files(self) -> Iterable[Path]:
        for root in self.session_roots:
            if not root.exists():
                continue
            for directory in sorted(root.glob("*/*")):
                if not directory.is_dir():
                    continue
                generations = {}
                for path in directory.iterdir():
                    match = LOG_NAME.fullmatch(path.name)
                    if path.is_file() and match:
                        generations.setdefault(int(match.group(1) or 0), []).append(path)
                if not generations:
                    continue
                # Migration retains predecessor files; index only the latest generation.
                candidates = generations[max(generations)]
                if len(candidates) != 1:
                    raise ValueError(f"Ambiguous DSH session encodings: {directory}")
                read_header(candidates[0])
                yield candidates[0]


def project_cwd(path: Path) -> str:
    return read_header(path).get("cwd", "")


def session_id_for_file(path: Path) -> str:
    return read_header(path)["id"]


def agent_id(header: dict) -> str:
    return header["id"] if header.get("origin") == "subagent" else "main"


def session_family_files(session_id: str, files: Iterable[Path]) -> list[Path]:
    """Resolve an exact ID, then its subagent descendants (ordinary forks stay separate)."""
    headers = [(path, read_header(path)) for path in files]
    anchors = [path for path, header in headers if header["id"] == session_id]
    if len(anchors) > 1:
        raise ValueError(f"Ambiguous DSH session id: {session_id}")
    if not anchors:
        return []
    result = anchors[:]
    selected = {session_id}
    while True:
        children = [
            (path, header) for path, header in headers
            if header.get("origin") == "subagent"
            and header.get("parentSession") in selected
            and header["id"] not in selected
        ]
        if not children:
            return result
        result.extend(path for path, _ in children)
        selected.update(header["id"] for _, header in children)


def _timestamp(value) -> str:
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def content_text(content) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        block["text"] for block in content
        if isinstance(block, dict) and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    )


def normalize_record(record: dict, header: dict, tool_names: dict) -> dict | None:
    kind = record.get("type")
    data = record.get("data", {})
    tool_name = call_id = role = ""
    if kind == "session":
        msg_type = "session_meta"
        text = f"cwd={header.get('cwd', '')} parent={header.get('parentSession', '')}"
    elif kind == "session/title":
        msg_type = "session_meta"
        text = data.get("title", "")
    elif kind == "user/message":
        msg_type = role = "user"
        text = content_text(data.get("content"))
    elif kind == "assistant/message":
        msg_type = role = "assistant"
        # Standalone tool/call is canonical; do not index embedded calls or streams twice.
        text = content_text(data.get("message", {}).get("content"))
    elif kind == "tool/call":
        msg_type, role = "tool_use", "assistant"
        call_id, tool_name = data.get("callId", ""), data.get("name", "")
        text = data.get("arguments", "")
        if call_id:
            tool_names[call_id] = tool_name
    elif kind == "tool/result":
        msg_type, role = "tool_result", "tool"
        message = data.get("message", {})
        call_id = message.get("toolCallId", "")
        tool_name = tool_names.get(call_id, "")
        text = content_text(message.get("content"))
    else:
        return None
    if not isinstance(text, str) or (not text and msg_type in {"user", "assistant"}):
        return None
    session_id = header["id"]
    return {
        "uuid": f"{session_id}:{record.get('seq', 'header')}",
        "parent_uuid": header.get("parentSession", ""),
        "session_id": session_id,
        "timestamp": _timestamp(header["createdAt"] if kind == "session" else record["time"]),
        "msg_type": msg_type,
        "role": role,
        "tool_name": tool_name,
        "tool_call_id": call_id,
        "agent_id": agent_id(header),
        "content_preview": text[:300],
        "search_text": text,
    }


def create_platform() -> RetracePlatform:
    override = os.environ.get("DSH_HOME", "").strip()
    home = Path(override).expanduser() if override else Path.home() / ".dsh"
    return DshPlatform(
        name="dsh", home_dir=home, projects_dir=home / "projects",
        session_roots=(home / "sessions",), command_names=("dsh", "dsh.cmd", "dsh.exe"),
    )
