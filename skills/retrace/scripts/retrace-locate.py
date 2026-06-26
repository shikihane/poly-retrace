#!/usr/bin/env python3
"""
retrace-locate.py - 定位 Claude Code 会话文件
版本: 1.1.0

功能：
- 定位当前会话的 JSONL 文件
- 根据工作目录推断项目目录
- 从 history.jsonl 获取最近会话
- 列出指定项目的所有会话
- 显示项目索引状态

用法：
    python retrace-locate.py                    # 定位当前会话
    python retrace-locate.py --cwd /path        # 指定项目目录
    python retrace-locate.py --session-id UUID  # 指定会话 ID
    python retrace-locate.py --list             # 列出所有项目
    python retrace-locate.py --list --project X # 列出项目会话
"""

import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

from retrace_paths import (
    configure_utf8_stdio,
    decode_path,
    encode_path,
    extract_session_id,
    find_session_files,
    get_platform,
    get_platforms,
    iter_session_files,
    read_first_json_record,
)

configure_utf8_stdio()

VERSION = "1.2.0"


def get_claude_dir() -> Path:
    """兼容旧名称：返回 Codex 主目录。"""
    return get_platform("codex").home_dir


def get_projects_dir(platform: str = "codex") -> Path:
    return get_platform(platform).projects_dir


def get_current_session_id() -> Optional[str]:
    """从 history.jsonl 获取最近会话的 session_id"""
    history_file = get_claude_dir() / "history.jsonl"
    if not history_file.exists():
        return None

    try:
        with open(history_file, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            pos = size - 1
            while pos > 0:
                f.seek(pos)
                if f.read(1) == b"\n":
                    break
                pos -= 1
            f.seek(pos + 1 if pos > 0 else 0)
            last_line = f.readline().decode("utf-8").strip()
            if last_line:
                return json.loads(last_line).get("sessionId")
    except Exception as e:
        print(f"⚠️  读取 history.jsonl 失败: {e}", file=sys.stderr)
    return None


def find_session_file(project_dir: Path, session_id: str) -> Optional[Path]:
    """在项目目录中查找指定会话的 JSONL 文件"""
    for session_file in find_project_session_files(project_dir):
        if session_id in session_file.stem:
            return session_file
    return None


def get_codex_session_meta(session_file: Path) -> Dict:
    """读取 Codex session_meta。"""
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("type") == "session_meta":
                    return record.get("payload", {})
    except OSError:
        pass
    return {}


def get_session_cwd(session_file: Path, platform: str = "codex") -> str:
    """Return the cwd recorded by a session file when available."""
    if platform in {"claude", "pi"}:
        first_record = read_first_json_record(session_file)
        return first_record.get("cwd", "")
    return get_codex_session_meta(session_file).get("cwd", "")


def find_project_session_files(project_dir: Path) -> List[Path]:
    """Return JSONL session files under a project directory, including subagents."""
    if not project_dir.exists():
        return []
    return sorted(project_dir.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)


def find_platform_session_file(session_id: str, platform: str = "codex") -> Optional[Path]:
    """扫描指定平台会话根目录查找 session 文件。"""
    matches = find_session_files(session_id, platform)
    if matches:
        return matches[0]
    return None


def find_latest_session(project_dir: Path) -> Optional[Path]:
    """找到项目目录中最近修改的 JSONL 文件"""
    if not project_dir.exists():
        return None
    jsonl_files = find_project_session_files(project_dir)
    if not jsonl_files:
        return None
    jsonl_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return jsonl_files[0]


def locate_session(cwd: str = None, session_id: str = None, platform: str = "codex") -> dict:
    """定位会话文件"""
    projects_dir = get_projects_dir(platform)
    projects_dir.mkdir(parents=True, exist_ok=True)

    # 方法 1: 指定了 session_id
    if session_id:
        for retrace_platform in get_platforms(platform):
            platform_file = find_platform_session_file(session_id, retrace_platform.name)
            if platform_file:
                cwd = get_session_cwd(platform_file, retrace_platform.name)
                if cwd:
                    project_name = encode_path(cwd)
                else:
                    project_name = platform_file.relative_to(retrace_platform.projects_dir).parts[0]
                result = _build_result(session_id, platform_file, retrace_platform.projects_dir / project_name)
                result["platform"] = retrace_platform.name
                return result
        for project_dir in projects_dir.iterdir():
            if project_dir.is_dir():
                session_file = find_session_file(project_dir, session_id)
                if session_file:
                    return _build_result(session_id, session_file, project_dir)
        return {"error": f"找不到会话: {session_id}"}

    # 方法 2: 从 history.jsonl 获取当前会话
    current_session_id = get_current_session_id()

    # 方法 3: 根据 CWD 推断项目目录
    if cwd is None:
        cwd = os.getcwd()
    encoded_cwd = encode_path(cwd)
    project_dir = projects_dir / encoded_cwd

    if project_dir.exists():
        if current_session_id:
            session_file = find_session_file(project_dir, current_session_id)
            if session_file:
                return _build_result(current_session_id, session_file, project_dir)
        latest = find_latest_session(project_dir)
        if latest:
            return _build_result(latest.stem, latest, project_dir)

    # 模糊匹配
    for pd in projects_dir.iterdir():
        if pd.is_dir() and encoded_cwd.lower() in pd.name.lower():
            if current_session_id:
                session_file = find_session_file(pd, current_session_id)
                if session_file:
                    return _build_result(current_session_id, session_file, pd)
            latest = find_latest_session(pd)
            if latest:
                return _build_result(latest.stem, latest, pd)

    return {"error": f"找不到项目目录: {encoded_cwd}"}


def _build_result(session_id: str, session_file: Path, project_dir: Path) -> dict:
    """构建返回结果"""
    stat = session_file.stat()
    return {
        "session_id": session_id,
        "session_file": str(session_file),
        "project_dir": project_dir.name,
        "project_path": decode_path(project_dir.name),
        "file_size": stat.st_size,
        "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
    }


def get_index_db_path(project_dir: Path) -> Path:
    """获取项目索引数据库路径"""
    return project_dir / "retrace-index.db"


def get_session_summaries(project_dir: Path) -> Dict[str, str]:
    """从索引数据库获取会话摘要"""
    import sqlite3
    db_path = get_index_db_path(project_dir)
    if not db_path.exists():
        return {}

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
        if not cursor.fetchone():
            conn.close()
            return {}

        cursor.execute("SELECT session_id, summary, message_count FROM sessions")
        summaries = {}
        for row in cursor.fetchall():
            summaries[row[0]] = {"summary": row[1], "message_count": row[2]}
        conn.close()
        return summaries
    except:
        return {}


def list_projects(platform: str = "codex") -> List[Dict]:
    """列出所有项目"""
    projects = []
    discovered = {}
    for retrace_platform in get_platforms(platform):
        projects_dir = retrace_platform.projects_dir
        projects_dir.mkdir(parents=True, exist_ok=True)

        for session_file in iter_session_files(retrace_platform.name):
            cwd = get_session_cwd(session_file, retrace_platform.name)
            if retrace_platform.name == "claude":
                try:
                    name = session_file.relative_to(projects_dir).parts[0]
                except ValueError:
                    name = session_file.parent.name
                cwd = cwd or decode_path(name, retrace_platform.name)
            elif cwd:
                name = encode_path(cwd)
            else:
                continue
            key = (retrace_platform.name, name)
            entry = discovered.setdefault(key, {
                "name": name,
                "path": cwd,
                "platform": retrace_platform.name,
                "session_count": 0,
                "total_size": 0,
                "latest_modified": None,
                "has_index": False,
                "index_size": 0,
            })
            stat = session_file.stat()
            entry["session_count"] += 1
            entry["total_size"] += stat.st_size
            modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
            if not entry["latest_modified"] or modified > entry["latest_modified"]:
                entry["latest_modified"] = modified

        for pd in sorted(projects_dir.iterdir()):
            if pd.is_dir():
                db_path = get_index_db_path(pd)
                key = (retrace_platform.name, pd.name)
                item = discovered.pop(key, {
                    "name": pd.name,
                    "path": decode_path(pd.name, retrace_platform.name),
                    "platform": retrace_platform.name,
                    "session_count": 0,
                    "total_size": 0,
                    "latest_modified": None,
                    "has_index": False,
                    "index_size": 0,
                })
                item.update({
                    "has_index": db_path.exists(),
                    "index_size": db_path.stat().st_size if db_path.exists() else 0
                })
                projects.append(item)

    projects.extend(discovered.values())
    return sorted(projects, key=lambda p: p.get("latest_modified") or "", reverse=True)


def list_sessions(project_name: str, platform: str = "codex") -> List[Dict]:
    """列出项目的所有会话（含摘要）"""
    projects_dir = get_projects_dir(platform)
    projects_dir.mkdir(parents=True, exist_ok=True)

    project_name_lower = project_name.lower()
    project_dirs = [pd for pd in projects_dir.iterdir()
                    if pd.is_dir() and project_name_lower in pd.name.lower()]
    summaries = {}
    for project_dir in project_dirs:
        summaries.update(get_session_summaries(project_dir))

    sessions = []
    for f in iter_session_files(platform):
        cwd = get_session_cwd(f, platform)
        if platform == "claude":
            try:
                encoded_name = f.relative_to(projects_dir).parts[0]
            except ValueError:
                encoded_name = encode_path(cwd) if cwd else f.parent.name
        else:
            encoded_name = encode_path(cwd) if cwd else ""

        haystack = " ".join(part for part in (encoded_name, cwd, str(f)) if part).lower()
        if project_name_lower not in haystack:
            continue

        stat = f.stat()
        first = read_first_json_record(f)
        session_id = extract_session_id(first) or f.stem
        info = summaries.get(session_id, {})
        sessions.append({
            "session_id": session_id,
            "file": str(f),
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "message_count": info.get("message_count"),
            "summary": info.get("summary")
        })

    sessions.sort(key=lambda item: item.get("modified", ""), reverse=True)
    return sessions


def main():
    parser = argparse.ArgumentParser(description="定位 Claude Code 会话文件")
    parser.add_argument("--cwd", help="指定工作目录")
    parser.add_argument("--session-id", help="指定会话 ID")
    parser.add_argument("--list", action="store_true", help="列出项目或会话")
    parser.add_argument("--project", help="指定项目名")
    parser.add_argument("--platform", choices=["codex", "claude", "pi"], required=True,
                        help="会话平台")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    args = parser.parse_args()

    if args.list:
        result = list_sessions(args.project, args.platform) if args.project else list_projects(args.platform)
    else:
        result = locate_session(cwd=args.cwd, session_id=args.session_id, platform=args.platform)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if isinstance(result, list):
            for item in result:
                if "session_id" in item:
                    # 会话列表
                    sid = item['session_id'][:8] + "..."
                    msg_count = item.get('message_count') or '?'
                    summary = item.get('summary', '')
                    print(f"[{sid}] {item['modified'][:16]} ({msg_count} msgs, {item['size']:,}B)")
                    if summary:
                        print(f"   📝 {summary[:80]}...")
                else:
                    # 项目列表
                    idx = "✓" if item.get('has_index') else "✗"
                    print(f"[{idx}] {item['name']}")
                    print(f"    {item['session_count']} sessions, {item['total_size']:,} bytes")
                    if item.get('has_index'):
                        print(f"    索引: {item['index_size']:,} bytes")
        elif "error" in result:
            print(f"❌ {result['error']}", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"📍 Session: {result['session_id']}")
            print(f"📁 File: {result['session_file']}")
            print(f"📂 Project: {result['project_path']}")
            print(f"📏 Size: {result['file_size']:,} bytes")
            print(f"🕐 Modified: {result['last_modified']}")


if __name__ == "__main__":
    main()
