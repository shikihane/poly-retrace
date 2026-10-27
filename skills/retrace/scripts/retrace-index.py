#!/usr/bin/env python3
"""
retrace-index.py - Claude Code 会话日志索引器
版本: 2.3.0

功能：
- 按项目建立独立索引
- 流式解析 JSONL 会话文件（不加载到内存）
- 建立 SQLite FTS5 全文索引
- 支持增量索引
- 会话摘要生成（Haiku）
- 去重和幂等性保证

用法：
    python retrace-index.py --auto             # 索引当前项目
    python retrace-index.py --auto --project X # 索引指定项目
    python retrace-index.py --stats            # 显示统计
"""

import json
import sqlite3
import hashlib
import shutil
import subprocess
import os
import sys
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

from retrace_paths import (
    RetracePlatform,
    SUPPORTED_PLATFORMS,
    configure_utf8_stdio,
    encode_path,
    find_platform_command,
    get_platform,
    get_platforms,
)
from platforms import kimi as kimi_platform
from platforms import grok as grok_platform
from platforms import dsh as dsh_platform
from platforms import omp as omp_platform

configure_utf8_stdio()

VERSION = "2.3.0"
PREVIEW_LIMIT = 300
SEARCH_TEXT_LIMIT = 8192
TRIGRAM_TOOL_RESULT_LIMIT = 4096
TRIGRAM_OTHER_LIMIT = 8192
TRIGRAM_MESSAGE_TYPES = {"user", "assistant", "tool_use", "tool_result"}

# 并行配置
MAX_WORKERS = 4  # 项目级并行数
MAX_SUMMARY_WORKERS = 20  # 摘要生成并行数（LLM调用）

# 线程本地存储（每个线程自己的数据库连接）
_thread_local = threading.local()

def _get_thread_conn(project_dir: Path) -> sqlite3.Connection:
    """获取当前线程的数据库连接（线程安全，自动初始化）"""
    if not hasattr(_thread_local, 'conn'):
        db_path = get_project_db_path(project_dir)
        # 先创建数据库（包含表结构），再返回连接
        _thread_local.conn = create_index_db(str(db_path))
    return _thread_local.conn

# 会话摘要配置
SUMMARY_HEAD_LINES = 100  # 读取前 N 行生成摘要
ALLOW_UNSANDBOXED_AI = os.environ.get("RETRACE_ALLOW_UNSANDBOXED_AI") == "1"


def get_claude_dir() -> Path:
    """兼容旧名称：返回 Codex 主目录。"""
    return get_platform("codex").home_dir


def get_projects_dir(platform: str = "codex") -> Path:
    return get_platform(platform).projects_dir


def get_project_db_path(project_dir: Path) -> Path:
    """按项目返回索引路径"""
    return project_dir / "retrace-index.db"


def reset_index_db(project_dir: Path) -> None:
    """Remove index database files for a clean rebuild."""
    db_path = get_project_db_path(project_dir)
    for path in (db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")):
        try:
            if path.exists():
                path.unlink()
        except OSError as e:
            print(f"⚠️  无法删除索引文件 {path}: {e}", file=sys.stderr)


def find_analysis_command() -> Optional[str]:
    """查找用于摘要生成的命令。"""
    return find_platform_command("codex")


def create_index_db(db_path: str) -> sqlite3.Connection:
    """创建或打开索引数据库"""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # 检查 FTS5 支持
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_test USING fts5(c)")
        conn.execute("DROP TABLE _fts_test")
        fts = "fts5"
        tokenize = ", tokenize='unicode61 remove_diacritics 2'"
    except:
        fts = "fts4"
        tokenize = ""
        print("⚠️  FTS5 不可用，降级到 FTS4", file=sys.stderr)

    conn.executescript(f'''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_file TEXT NOT NULL,
            line_no INTEGER NOT NULL,
            byte_offset INTEGER NOT NULL,
            byte_length INTEGER NOT NULL,
            part_index INTEGER NOT NULL DEFAULT 0,
            uuid TEXT,
            parent_uuid TEXT,
            session_id TEXT,
            timestamp TEXT,
            msg_type TEXT,
            role TEXT,
            tool_name TEXT,
            agent_id TEXT DEFAULT '',
            content_preview TEXT,
            search_text TEXT,
            content_hash TEXT,
            UNIQUE(session_file, byte_offset, part_index)
        );

        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            session_file TEXT,
            start_time TEXT,
            end_time TEXT,
            message_count INTEGER DEFAULT 0,
            summary TEXT,
            summarized_at TEXT
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING {fts}(
            search_text, msg_type, role, tool_name {tokenize}
        );

        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_timestamp ON messages(timestamp);
        CREATE INDEX IF NOT EXISTS idx_type ON messages(msg_type);
        CREATE INDEX IF NOT EXISTS idx_role ON messages(role);
        CREATE INDEX IF NOT EXISTS idx_tool ON messages(tool_name);
        CREATE INDEX IF NOT EXISTS idx_session ON messages(session_id);
    ''')

    ensure_index_schema(conn)

    return conn


def ensure_index_schema(conn: sqlite3.Connection) -> None:
    """Apply lightweight schema upgrades for existing index databases."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
    if "search_text" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN search_text TEXT")
        conn.execute("UPDATE messages SET search_text = content_preview WHERE search_text IS NULL")
    if "agent_id" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN agent_id TEXT DEFAULT ''")

    legacy_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'messages_legacy'"
    ).fetchone()
    if "part_index" not in columns or legacy_exists:
        # A savepoint keeps the table rename/copy/drop sequence atomic.  It also
        # lets a database left by the pre-2.3 migration (new empty `messages`
        # plus populated `messages_legacy`) recover on its next open.
        conn.execute("SAVEPOINT migrate_messages_part_index")
        try:
            if legacy_exists:
                legacy_columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(messages_legacy)")
                }
                if "part_index" in legacy_columns:
                    raise sqlite3.DatabaseError(
                        "cannot recover unexpected messages_legacy schema"
                    )
                conn.execute("DROP TABLE messages")
                conn.execute("ALTER TABLE messages_legacy RENAME TO messages")

            conn.execute("ALTER TABLE messages RENAME TO messages_legacy")
            conn.execute(
                """
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_file TEXT NOT NULL,
                    line_no INTEGER NOT NULL,
                    byte_offset INTEGER NOT NULL,
                    byte_length INTEGER NOT NULL,
                    part_index INTEGER NOT NULL DEFAULT 0,
                    uuid TEXT,
                    parent_uuid TEXT,
                    session_id TEXT,
                    timestamp TEXT,
                    msg_type TEXT,
                    role TEXT,
                    tool_name TEXT,
                    agent_id TEXT DEFAULT '',
                    content_preview TEXT,
                    search_text TEXT,
                    content_hash TEXT,
                    UNIQUE(session_file, byte_offset, part_index)
                )
                """
            )
            conn.execute(
                """
                INSERT INTO messages
                (id, session_file, line_no, byte_offset, byte_length, part_index,
                 uuid, parent_uuid, session_id, timestamp, msg_type, role,
                 tool_name, agent_id, content_preview, search_text, content_hash)
                SELECT id, session_file, line_no, byte_offset, byte_length, 0,
                       uuid, parent_uuid, session_id, timestamp, msg_type, role,
                       tool_name, agent_id, content_preview, search_text, content_hash
                FROM messages_legacy
                """
            )
            conn.execute("DROP TABLE messages_legacy")
            for index_name, column in (
                ("idx_timestamp", "timestamp"),
                ("idx_type", "msg_type"),
                ("idx_role", "role"),
                ("idx_tool", "tool_name"),
                ("idx_session", "session_id"),
            ):
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS {index_name} ON messages({column})"
                )
        except BaseException:
            conn.execute("ROLLBACK TO SAVEPOINT migrate_messages_part_index")
            conn.execute("RELEASE SAVEPOINT migrate_messages_part_index")
            raise
        else:
            conn.execute("RELEASE SAVEPOINT migrate_messages_part_index")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}

    fts_columns = {row[1] for row in conn.execute("PRAGMA table_info(messages_fts)")}
    if "search_text" not in fts_columns:
        conn.execute("DROP TABLE IF EXISTS messages_fts")
        conn.execute(
            """
            CREATE VIRTUAL TABLE messages_fts USING fts5(
                search_text, msg_type, role, tool_name,
                tokenize='unicode61 remove_diacritics 2'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO messages_fts(rowid, search_text, msg_type, role, tool_name)
            SELECT id, COALESCE(search_text, content_preview, ''), msg_type, role, COALESCE(tool_name, '')
            FROM messages
            """
        )

    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_trigram_fts USING fts5(
                search_text, msg_type, role, tool_name,
                tokenize='trigram'
            )
            """
        )
    except sqlite3.OperationalError:
        conn.commit()
        return
    trigram_count = conn.execute("SELECT COUNT(*) FROM messages_trigram_fts").fetchone()[0]
    message_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    if message_count and trigram_count == 0:
        placeholders = ",".join("?" * len(TRIGRAM_MESSAGE_TYPES))
        params = list(TRIGRAM_MESSAGE_TYPES)
        conn.execute(
            f"""
            INSERT INTO messages_trigram_fts(rowid, search_text, msg_type, role, tool_name)
            SELECT id,
                   CASE
                       WHEN msg_type = 'tool_result'
                       THEN SUBSTR(COALESCE(search_text, content_preview, ''), 1, ?)
                       ELSE SUBSTR(COALESCE(search_text, content_preview, ''), 1, ?)
                   END,
                   msg_type,
                   role,
                   COALESCE(tool_name, '')
            FROM messages
            WHERE msg_type IN ({placeholders})
              AND LENGTH(TRIM(COALESCE(search_text, content_preview, ''))) >= 3
            """,
            [TRIGRAM_TOOL_RESULT_LIMIT, TRIGRAM_OTHER_LIMIT] + params,
        )
    conn.commit()


def extract_content_preview(message: dict, max_len: int = PREVIEW_LIMIT) -> str:
    """从消息中提取内容预览"""
    content = message.get("content", "")
    if isinstance(content, str):
        return content[:max_len]
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    texts.append(item.get("text", ""))
                elif item.get("type") == "tool_use":
                    texts.append(f"[Tool: {item.get('name', 'unknown')}]")
                elif item.get("type") == "tool_result":
                    result = item.get("content", "")
                    if isinstance(result, str):
                        texts.append(result[:100])
            elif isinstance(item, str):
                texts.append(item)
        return " ".join(texts)[:max_len]
    return str(content)[:max_len]


def _content_text(content, max_len: int = 300) -> str:
    """Extract readable text from Codex message content arrays."""
    if isinstance(content, str):
        return content[:max_len]
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict):
                if item.get("type") in ("input_text", "output_text", "text"):
                    texts.append(item.get("text", ""))
                elif item.get("type") == "tool_result":
                    texts.append(str(item.get("content", ""))[:100])
        return " ".join(t for t in texts if t)[:max_len]
    if content is None:
        return ""
    return str(content)[:max_len]


def extract_search_text(message: dict, max_len: int = SEARCH_TEXT_LIMIT) -> str:
    """Extract longer text for search indexing without changing list previews."""
    content = message.get("content", "")
    if isinstance(content, str):
        return content[:max_len]
    if isinstance(content, list):
        texts = []
        remaining = max_len
        for item in content:
            if remaining <= 0:
                break
            text = ""
            if isinstance(item, str):
                text = item
            elif isinstance(item, dict):
                if item.get("type") in ("text", "input_text", "output_text"):
                    text = item.get("text", "")
                elif item.get("type") == "tool_use":
                    text = f"[Tool: {item.get('name', 'unknown')}] {item.get('input', '')}"
                elif item.get("type") == "tool_result":
                    text = str(item.get("content", ""))
            if text:
                texts.append(text[:remaining])
                remaining -= len(text)
        return " ".join(texts)[:max_len]
    if content is None:
        return ""
    return str(content)[:max_len]


def extract_response_search_text(payload: dict, max_len: int = SEARCH_TEXT_LIMIT) -> str:
    payload_type = payload.get("type", "")
    if payload_type == "message":
        return _content_text(payload.get("content", []), max_len)
    if payload_type == "function_call":
        return payload.get("arguments", "")[:max_len]
    if payload_type == "function_call_output":
        return str(payload.get("output", ""))[:max_len]
    return ""


def extract_codex_project_name(record: dict) -> Optional[str]:
    """Return the retrace project bucket from a Codex session_meta record."""
    if record.get("type") != "session_meta":
        return None
    cwd = record.get("payload", {}).get("cwd")
    return encode_path(cwd) if cwd else None


def normalize_record(data: dict, kimi_context: Optional[dict] = None) -> Optional[dict]:
    """Normalize Claude-style and Codex-style JSONL records into index fields."""
    record_type = data.get("type", "")

    if record_type in {"context.append_message", "context.append_loop_event"}:
        context = kimi_context or {}
        return kimi_platform.normalize_wire_record(
            data,
            session_id=context.get("session_id", ""),
            agent_id=context.get("agent_id", ""),
            tool_names=context.get("tool_names"),
        )

    if record_type in {"user", "assistant", "tool_result"}:
        message = data.get("message", {})
        content_preview = extract_content_preview(message)
        search_text = extract_search_text(message)
        role = message.get("role", "")
        tool_name = None
        content = message.get("content", [])
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_use":
                    tool_name = item.get("name")
                    break
        return {
            "uuid": data.get("uuid", ""),
            "parent_uuid": data.get("parentUuid", ""),
            "session_id": data.get("sessionId", ""),
            "timestamp": data.get("timestamp", ""),
            "msg_type": record_type,
            "role": role,
            "tool_name": tool_name,
            "content_preview": content_preview,
            "search_text": search_text,
        }

    if record_type == "session_meta":
        payload = data.get("payload", {})
        return {
            "uuid": payload.get("id", ""),
            "parent_uuid": "",
            "session_id": payload.get("id", ""),
            "timestamp": data.get("timestamp", payload.get("timestamp", "")),
            "msg_type": "session_meta",
            "role": "",
            "tool_name": "",
            "content_preview": f"cwd={payload.get('cwd', '')} originator={payload.get('originator', '')}",
            "search_text": f"cwd={payload.get('cwd', '')} originator={payload.get('originator', '')}",
        }

    if record_type in {"response_item", "turn_context"}:
        payload = data.get("payload", {})
        payload_type = payload.get("type", "")
        session_id = payload.get("id") or data.get("session_id", "")
        timestamp = data.get("timestamp", "")

        if payload_type == "message":
            role = payload.get("role", "")
            msg_type = "assistant" if role == "assistant" else role or "message"
            return {
                "uuid": payload.get("id", ""),
                "parent_uuid": "",
                "session_id": session_id,
                "timestamp": timestamp,
                "msg_type": msg_type,
                "role": role,
                "tool_name": "",
                "content_preview": _content_text(payload.get("content", [])),
                "search_text": extract_response_search_text(payload),
            }

        if payload_type == "function_call":
            name = payload.get("name", "")
            args = payload.get("arguments", "")
            return {
                "uuid": payload.get("call_id", ""),
                "parent_uuid": "",
                "session_id": session_id,
                "timestamp": timestamp,
                "msg_type": "tool_use",
                "role": "assistant",
                "tool_name": name,
                "content_preview": args[:300],
                "search_text": args[:SEARCH_TEXT_LIMIT],
            }

        if payload_type == "function_call_output":
            return {
                "uuid": payload.get("call_id", ""),
                "parent_uuid": "",
                "session_id": session_id,
                "timestamp": timestamp,
                "msg_type": "tool_result",
                "role": "tool",
                "tool_name": "",
                "content_preview": str(payload.get("output", ""))[:300],
                "search_text": str(payload.get("output", ""))[:SEARCH_TEXT_LIMIT],
            }

        if record_type == "turn_context":
            return {
                "uuid": payload.get("turn_id", ""),
                "parent_uuid": "",
                "session_id": "",
                "timestamp": timestamp,
                "msg_type": "turn_context",
                "role": "",
                "tool_name": "",
                "content_preview": f"cwd={payload.get('cwd', '')}",
                "search_text": f"cwd={payload.get('cwd', '')}",
            }

    return None


def should_trigram_index(msg_type: str, search_text: str) -> bool:
    if msg_type not in TRIGRAM_MESSAGE_TYPES:
        return False
    return bool(search_text and len(search_text.strip()) >= 3)


def trigram_search_text(search_text: str, msg_type: str) -> str:
    limit = TRIGRAM_TOOL_RESULT_LIMIT if msg_type == "tool_result" else TRIGRAM_OTHER_LIMIT
    return search_text[:limit]


def insert_trigram_if_selective(conn: sqlite3.Connection, rowid: int, search_text: str,
                                msg_type: str, role: str, tool_name: str) -> None:
    if not should_trigram_index(msg_type, search_text):
        return
    conn.execute(
        """
        INSERT INTO messages_trigram_fts (rowid, search_text, msg_type, role, tool_name)
        VALUES (?, ?, ?, ?, ?)
        """,
        (rowid, trigram_search_text(search_text, msg_type), msg_type, role, tool_name or ""),
    )


def insert_normalized_message(
    conn: sqlite3.Connection,
    cursor: sqlite3.Cursor,
    source_file: str,
    line_no: int,
    byte_offset: int,
    byte_length: int,
    normalized: dict,
    part_index: int = 0,
) -> bool:
    """Insert one normalized record and its FTS rows."""
    content_preview = normalized.get("content_preview", "")
    search_text = normalized.get("search_text", content_preview)
    content_hash = hashlib.md5(content_preview.encode()).hexdigest()[:16]
    values = (
        source_file,
        line_no,
        byte_offset,
        byte_length,
        part_index,
        normalized.get("uuid", ""),
        normalized.get("parent_uuid", ""),
        normalized.get("session_id", ""),
        normalized.get("timestamp", ""),
        normalized.get("msg_type", ""),
        normalized.get("role", ""),
        normalized.get("tool_name") or "",
        normalized.get("agent_id", ""),
        content_preview,
        search_text,
        content_hash,
    )
    try:
        cursor.execute(
            """
            INSERT OR IGNORE INTO messages
            (session_file, line_no, byte_offset, byte_length, part_index,
             uuid, parent_uuid, session_id, timestamp, msg_type, role,
             tool_name, agent_id, content_preview, search_text, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
    except sqlite3.IntegrityError:
        return False
    if cursor.rowcount <= 0:
        return False

    msg_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO messages_fts (rowid, search_text, msg_type, role, tool_name)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            msg_id,
            search_text,
            normalized.get("msg_type", ""),
            normalized.get("role", ""),
            normalized.get("tool_name") or "",
        ),
    )
    insert_trigram_if_selective(
        conn,
        msg_id,
        search_text,
        normalized.get("msg_type", ""),
        normalized.get("role", ""),
        normalized.get("tool_name") or "",
    )
    return True


def refresh_normalized_message(
    conn: sqlite3.Connection,
    cursor: sqlite3.Cursor,
    source_file: str,
    normalized: dict,
) -> bool:
    """Refresh mutable normalized fields without changing source offsets."""
    row = cursor.execute(
        """
        SELECT id, content_preview, search_text, uuid, parent_uuid, session_id,
               timestamp, role, tool_name, agent_id
        FROM messages
        WHERE session_file = ? AND msg_type = ?
        ORDER BY part_index, id
        LIMIT 1
        """,
        (source_file, normalized.get("msg_type", "")),
    ).fetchone()
    if not row:
        return False

    content_preview = normalized.get("content_preview", "")
    search_text = normalized.get("search_text", content_preview)
    refreshed = (
        content_preview,
        search_text,
        normalized.get("uuid", ""),
        normalized.get("parent_uuid", ""),
        normalized.get("session_id", ""),
        normalized.get("timestamp", ""),
        normalized.get("role", ""),
        normalized.get("tool_name") or "",
        normalized.get("agent_id", ""),
    )
    if refreshed == row[1:]:
        return False

    msg_id = row[0]
    content_hash = hashlib.md5(content_preview.encode()).hexdigest()[:16]
    cursor.execute(
        """
        UPDATE messages
        SET content_preview = ?, search_text = ?, uuid = ?, parent_uuid = ?,
            session_id = ?, timestamp = ?, role = ?, tool_name = ?, agent_id = ?,
            content_hash = ?
        WHERE id = ?
        """,
        (*refreshed, content_hash, msg_id),
    )
    cursor.execute("DELETE FROM messages_fts WHERE rowid = ?", (msg_id,))
    cursor.execute(
        """
        INSERT INTO messages_fts (rowid, search_text, msg_type, role, tool_name)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            msg_id,
            search_text,
            normalized.get("msg_type", ""),
            normalized.get("role", ""),
            normalized.get("tool_name") or "",
        ),
    )
    try:
        cursor.execute("DELETE FROM messages_trigram_fts WHERE rowid = ?", (msg_id,))
    except sqlite3.OperationalError:
        pass
    insert_trigram_if_selective(
        conn,
        msg_id,
        search_text,
        normalized.get("msg_type", ""),
        normalized.get("role", ""),
        normalized.get("tool_name") or "",
    )
    return True


def remember_tool_name(normalized: Optional[dict], tool_names: dict) -> None:
    """Remember a Kimi tool call so a later result retains its native name."""
    if not normalized or normalized.get("msg_type") != "tool_use":
        return
    tool_call_id = normalized.get("tool_call_id", "")
    if tool_call_id:
        tool_names[tool_call_id] = normalized.get("tool_name", "")


def normalize_records(
    data: dict,
    kimi_context: Optional[dict] = None,
    omp_context: Optional[dict] = None,
    grok_context: Optional[dict] = None,
) -> list[dict]:
    """Normalize a source entry, allowing platforms to expand one line."""
    if omp_context is not None:
        return omp_platform.normalize_record(data, omp_context)
    if grok_context is not None:
        normalized = grok_platform.normalize_record(
            data,
            session_id=grok_context.get("session_id", ""),
            agent_id=grok_context.get("agent_id", ""),
            tool_names=grok_context.get("tool_names"),
        )
        return [normalized] if normalized else []
    normalized = normalize_record(data, kimi_context)
    return [normalized] if normalized else []


def _omp_stable_region(session_file: Path, indexed_offset: int) -> tuple[bool, int, int]:
    """Describe bytes that must stay immutable for append-only OMP indexing."""
    stable_start = 0
    has_title_slot = False
    try:
        with open(session_file, "rb") as source:
            first_line = source.readline()
        first_record = json.loads(first_line.decode("utf-8"))
        if isinstance(first_record, dict) and first_record.get("type") == "title":
            has_title_slot = True
            stable_start = len(first_line)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    return has_title_slot, stable_start, max(0, indexed_offset - stable_start)


def _hash_file_region(session_file: Path, start: int, length: int) -> str:
    digest = hashlib.sha256()
    remaining = length
    with open(session_file, "rb") as source:
        source.seek(start)
        while remaining > 0:
            chunk = source.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            digest.update(chunk)
            remaining -= len(chunk)
    if remaining:
        return ""
    return digest.hexdigest()


def _omp_source_fingerprint(session_file: Path, indexed_offset: int) -> dict:
    has_title, stable_start, stable_length = _omp_stable_region(
        session_file, indexed_offset
    )
    stat = session_file.stat()
    return {
        "has_title": has_title,
        "stable_start": stable_start,
        "stable_length": stable_length,
        "stable_hash": _hash_file_region(session_file, stable_start, stable_length),
        "indexed_offset": indexed_offset,
        "file_size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _store_omp_fingerprint(
    cursor: sqlite3.Cursor,
    session_file: Path,
    indexed_offset: int,
) -> None:
    cursor.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        (
            f"fingerprint:{session_file}",
            json.dumps(
                _omp_source_fingerprint(session_file, indexed_offset),
                separators=(",", ":"),
                sort_keys=True,
            ),
        ),
    )


def _refresh_omp_fingerprint_stat(
    cursor: sqlite3.Cursor,
    session_file: Path,
    serialized_fingerprint: str,
) -> None:
    """Refresh file metadata after the stored stable hash was verified."""
    fingerprint = json.loads(serialized_fingerprint)
    stat = session_file.stat()
    fingerprint["file_size"] = stat.st_size
    fingerprint["mtime_ns"] = stat.st_mtime_ns
    cursor.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        (
            f"fingerprint:{session_file}",
            json.dumps(fingerprint, separators=(",", ":"), sort_keys=True),
        ),
    )


def _omp_is_append_only(
    session_file: Path,
    start_offset: int,
    serialized_fingerprint: Optional[str],
) -> bool:
    if not serialized_fingerprint:
        return False
    try:
        previous = json.loads(serialized_fingerprint)
        if int(previous.get("indexed_offset", -1)) != start_offset:
            return False
        stat = session_file.stat()
        if stat.st_size < start_offset:
            return False
        has_title, stable_start, stable_length = _omp_stable_region(
            session_file, start_offset
        )
        if (
            bool(previous.get("has_title")) != has_title
            or int(previous.get("stable_start", -1)) != stable_start
            or int(previous.get("stable_length", -1)) != stable_length
        ):
            return False
        if (
            stat.st_size == int(previous.get("file_size", -1))
            and stat.st_mtime_ns == int(previous.get("mtime_ns", -1))
        ):
            return True
        return _hash_file_region(session_file, stable_start, stable_length) == str(
            previous.get("stable_hash", "")
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _drop_indexed_source(
    conn: sqlite3.Connection,
    cursor: sqlite3.Cursor,
    session_file: str,
) -> None:
    """Remove one rewritten source and every derived search/index row."""
    rows = cursor.execute(
        "SELECT id, session_id FROM messages WHERE session_file = ?",
        (session_file,),
    ).fetchall()
    for msg_id, _ in rows:
        cursor.execute("DELETE FROM messages_fts WHERE rowid = ?", (msg_id,))
        try:
            cursor.execute("DELETE FROM messages_trigram_fts WHERE rowid = ?", (msg_id,))
        except sqlite3.OperationalError:
            pass
    cursor.execute("DELETE FROM messages WHERE session_file = ?", (session_file,))
    for session_id in {row[1] for row in rows if row[1]}:
        cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM meta WHERE key = ?", (f"offset:{session_file}",))
    cursor.execute("DELETE FROM meta WHERE key = ?", (f"fingerprint:{session_file}",))


def index_dsh_file(conn: sqlite3.Connection, session_file: str, incremental: bool) -> tuple:
    """Index complete V4 rows using decompressed offsets and a verified prefix."""
    path = Path(session_file)
    header = dsh_platform.read_header(path)
    stat = path.stat()
    revision = [stat.st_size, stat.st_mtime_ns]
    key = f"fingerprint:{session_file}"
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    previous = json.loads(row[0]) if row and incremental else {}
    if previous.get("revision") == revision:
        return 0, set()
    # shortcut: changed compressed files are decoded from the start; add frame checkpoints
    # if large live sessions make verified prefix scans too costly.
    with dsh_platform.open_binary(path) as stream:
        raw = stream.read()
    after = path.stat()
    if [after.st_size, after.st_mtime_ns] != revision:
        raise RuntimeError(f"DSH session changed while reading; retry indexing: {path}")
    if json.loads(raw.split(b"\n", 1)[0]) != header:
        raise RuntimeError(f"DSH session header changed while reading; retry indexing: {path}")
    end = raw.rfind(b"\n") + 1
    start = previous.get("offset", 0)
    append_only = bool(previous) and start <= end and hashlib.sha256(
        raw[:start]
    ).hexdigest() == previous.get("prefix")
    count = 0
    tool_names = {}
    with conn:
        cursor = conn.cursor()
        if not append_only:
            _drop_indexed_source(conn, cursor, session_file)
            start = 0
        # A generation/encoding change must not leave an older source indexed too.
        old_sources = cursor.execute(
            "SELECT DISTINCT session_file FROM messages WHERE session_id = ? AND session_file != ?",
            (header["id"], session_file),
        ).fetchall()
        for (source,) in old_sources:
            _drop_indexed_source(conn, cursor, source)
        offset = 0
        for line_no, line in enumerate(raw[:end].splitlines(keepends=True), 1):
            record = json.loads(line)
            normalized = dsh_platform.normalize_record(record, header, tool_names)
            if offset >= start and normalized:
                if insert_normalized_message(
                    conn, cursor, session_file, line_no, offset, len(line), normalized
                ):
                    count += 1
            offset += len(line)
        fingerprint = {
            "revision": revision, "offset": end,
            "prefix": hashlib.sha256(raw[:end]).hexdigest(),
        }
        cursor.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (key, json.dumps(fingerprint)),
        )
    return count, {header["id"]}


def index_session_file(conn: sqlite3.Connection, session_file: str,
                       incremental: bool = True, platform_name: str = None) -> tuple:
    """索引单个会话文件，返回 (新索引消息数, 会话ID集合)"""
    if platform_name == "dsh" or dsh_platform.is_session_file(Path(session_file)):
        return index_dsh_file(conn, session_file, incremental)
    cursor = conn.cursor()

    # 获取上次索引位置
    cursor.execute("SELECT value FROM meta WHERE key = ?", (f"offset:{session_file}",))
    row = cursor.fetchone()
    start_offset = int(row[0]) if row and incremental else 0

    indexed_count = 0
    line_no = 0
    session_ids = set()
    current_session_id = ""
    session_path = Path(session_file)
    is_kimi = platform_name == "kimi" or kimi_platform.session_dir_for_wire(session_path) is not None
    is_omp = platform_name == "omp"
    is_grok = platform_name == "grok" or grok_platform.session_dir_for_updates(session_path) is not None
    tool_names = {}
    kimi_context = None
    omp_context = None
    grok_context = None
    if is_kimi:
        current_session_id = kimi_platform.session_id_for_wire(session_path)
        kimi_context = {
            "session_id": current_session_id,
            "agent_id": kimi_platform.agent_id_for_wire(session_path),
            "tool_names": tool_names,
        }
    if is_omp:
        omp_context = {
            "session_id": "",
            "agent_id": omp_platform.agent_id_for_file(session_path),
        }
    if is_grok:
        current_session_id = grok_platform.session_id_for_file(session_path)
        grok_context = {
            "session_id": current_session_id,
            "agent_id": "main",
            "tool_names": tool_names,
        }

    file_size = os.path.getsize(session_file)
    omp_fingerprint_value = ""
    if is_omp and start_offset > 0:
        fingerprint_row = cursor.execute(
            "SELECT value FROM meta WHERE key = ?",
            (f"fingerprint:{session_file}",),
        ).fetchone()
        omp_fingerprint_value = fingerprint_row[0] if fingerprint_row else ""
        if not _omp_is_append_only(
            session_path,
            start_offset,
            omp_fingerprint_value,
        ):
            _drop_indexed_source(conn, cursor, session_file)
            start_offset = 0
            omp_context = {
                "session_id": "",
                "agent_id": omp_platform.agent_id_for_file(session_path),
            }

    should_add_kimi_meta = (
        is_kimi
        and start_offset == 0
        and kimi_context["agent_id"] == "main"
        and kimi_platform.normalize_session_meta(session_path) is not None
    )
    should_add_grok_meta = (
        is_grok
        and start_offset == 0
        and grok_platform.normalize_session_meta(session_path) is not None
    )
    if is_omp and start_offset > 0:
        session_meta = omp_platform.normalize_session_meta(session_path)
        if session_meta and refresh_normalized_message(
            conn, cursor, session_file, session_meta
        ):
            conn.commit()
    if start_offset >= file_size and not should_add_kimi_meta and not should_add_grok_meta:
        if is_omp:
            # A title-slot-only update changes mtime but not the stable region.
            # Remember the new stat values so future no-op scans stay O(1).
            _refresh_omp_fingerprint_stat(
                cursor, session_path, omp_fingerprint_value
            )
            conn.commit()
        return 0, set()

    if should_add_kimi_meta:
        state_path = kimi_platform.session_dir_for_wire(session_path) / "state.json"
        session_meta = kimi_platform.normalize_session_meta(session_path)
        if insert_normalized_message(
            conn,
            cursor,
            str(state_path),
            1,
            0,
            state_path.stat().st_size,
            session_meta,
        ):
            indexed_count += 1
        if current_session_id:
            session_ids.add(current_session_id)

    if should_add_grok_meta:
        summary_path = grok_platform.session_dir_for_updates(session_path) / "summary.json"
        session_meta = grok_platform.normalize_session_meta(session_path)
        if insert_normalized_message(
            conn,
            cursor,
            str(summary_path),
            1,
            0,
            summary_path.stat().st_size,
            session_meta,
        ):
            indexed_count += 1
        if current_session_id:
            session_ids.add(current_session_id)

    if start_offset > 0:
        with open(session_file, 'rb') as f:
            while f.tell() < start_offset:
                line = f.readline()
                line_no += 1
                try:
                    record = json.loads(line.decode("utf-8"))
                    for normalized in normalize_records(record, kimi_context, omp_context, grok_context):
                        if normalized.get("msg_type") == "session_meta":
                            current_session_id = normalized.get("session_id", "")
                        remember_tool_name(normalized, tool_names)
                except Exception:
                    pass

    with open(session_file, 'rb') as f:
        f.seek(start_offset)
        byte_offset = start_offset

        for line in f:
            line_no += 1
            line_length = len(line)

            try:
                data = json.loads(line.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                byte_offset += line_length
                continue

            normalized_items = normalize_records(data, kimi_context, omp_context, grok_context)
            if not normalized_items:
                byte_offset += line_length
                continue

            for part_index, normalized in enumerate(normalized_items):
                remember_tool_name(normalized, tool_names)

                if normalized.get("msg_type") == "session_meta":
                    current_session_id = normalized.get("session_id", "")
                elif current_session_id and not normalized.get("session_id"):
                    normalized["session_id"] = current_session_id

                session_id = normalized.get("session_id", "")

                if session_id:
                    session_ids.add(session_id)

                if insert_normalized_message(
                    conn,
                    cursor,
                    session_file,
                    line_no,
                    byte_offset,
                    line_length,
                    normalized,
                    part_index,
                ):
                    indexed_count += 1

            byte_offset += line_length

        cursor.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (f"offset:{session_file}", str(byte_offset))
        )
        if is_omp:
            _store_omp_fingerprint(cursor, session_path, byte_offset)

    conn.commit()
    return indexed_count, session_ids


def update_session_meta(conn: sqlite3.Connection, session_id: str, session_file: str):
    """更新会话元信息"""
    cursor = conn.cursor()

    # 获取会话的时间范围和消息数
    cursor.execute('''
        SELECT MIN(timestamp), MAX(timestamp), COUNT(*)
        FROM messages WHERE session_id = ?
    ''', (session_id,))
    row = cursor.fetchone()

    if row and row[2] > 0:
        cursor.execute("SELECT session_file FROM sessions WHERE session_id = ?", (session_id,))
        existing = cursor.fetchone()
        canonical_file = choose_canonical_session_file(
            session_id,
            existing[0] if existing else "",
            session_file,
        )
        cursor.execute('''
            INSERT OR REPLACE INTO sessions (session_id, session_file, start_time, end_time, message_count)
            VALUES (?, ?, ?, ?, ?)
        ''', (session_id, canonical_file, row[0], row[1], row[2]))
        conn.commit()


def choose_canonical_session_file(session_id: str, current_file: str, candidate_file: str) -> str:
    """Prefer the main session JSONL over subagent sidecar files."""
    if not current_file:
        return candidate_file

    def priority(path: str) -> tuple[int, str]:
        p = Path(path)
        if omp_platform.is_session_file(p):
            return (0 if omp_platform.is_root_session_file(p) else 2, path)
        if p.stem == session_id and "subagents" not in p.parts:
            return (0, path)
        if p.name == "wire.jsonl" and p.parent.name == "main" and p.parent.parent.name == "agents":
            return (0, path)
        if "subagents" in p.parts or (p.name == "wire.jsonl" and p.parent.parent.name == "agents"):
            return (2, path)
        return (1, path)

    return min((current_file, candidate_file), key=priority)


def generate_session_summary(conn: sqlite3.Connection, session_id: str) -> Optional[str]:
    """生成会话摘要（读取 head + Haiku）"""
    cursor = conn.cursor()

    # 检查是否已有摘要
    cursor.execute("SELECT summary FROM sessions WHERE session_id = ? AND summary IS NOT NULL", (session_id,))
    row = cursor.fetchone()
    if row:
        return row[0]

    # 读取前 N 条消息
    cursor.execute('''
        SELECT content_preview, msg_type, role, tool_name
        FROM messages WHERE session_id = ?
        ORDER BY timestamp LIMIT ?
    ''', (session_id, SUMMARY_HEAD_LINES))

    rows = cursor.fetchall()
    if not rows:
        return None

    # 构建输入数据
    messages = []
    for preview, msg_type, role, tool in rows:
        if preview:
            messages.append({"type": msg_type, "role": role, "tool": tool, "content": preview[:200]})

    if not messages:
        return None

    data_str = json.dumps(messages, ensure_ascii=False, separators=(',', ':'))

    analysis_cmd = find_analysis_command()
    if not analysis_cmd:
        return None

    system_prompt = "Summarize this session in 1-2 sentences. What was the main goal/topic? Output plain text only."
    user_prompt = f"Summarize this Claude Code session ({len(messages)} messages):"

    try:
        cmd = [
            analysis_cmd,
            "-p",
            user_prompt,
            "--system-prompt",
            system_prompt,
            "--model",
            "haiku",
            "--no-session-persistence",
            "--output-format",
            "json",
        ]
        if ALLOW_UNSANDBOXED_AI:
            cmd.append("--dangerously-skip-permissions")

        result = subprocess.run(
            cmd,
            input=data_str,
            capture_output=True, text=True, encoding="utf-8", timeout=60
        )

        if result.returncode == 0:
            out = json.loads(result.stdout)
            summary = out.get("result", "")

            # 保存摘要
            cursor.execute('''
                UPDATE sessions SET summary = ?, summarized_at = ?
                WHERE session_id = ?
            ''', (summary, datetime.now().isoformat(), session_id))
            conn.commit()

            return summary
    except Exception as e:
        print(f"  ⚠️ 摘要生成失败: {e}", file=sys.stderr)

    return None

def _generate_summary_worker(args):
    """摘要生成 worker（线程安全版本）"""
    import threading
    import time
    project_dir, session_id = args
    thread_id = threading.get_ident()
    overall_start = time.time()
    
    # 日志显示开始
    print(f"    [THREAD {thread_id}] >>> {session_id[:8]} (overall_start)")
    
    conn = _get_thread_conn(project_dir)

    cursor = conn.cursor()
    # DB 查询时间
    db_start = time.time()
    cursor.execute("SELECT summary FROM sessions WHERE session_id = ? AND summary IS NOT NULL", (session_id,))
    if cursor.fetchone():
        print(f"    [THREAD {thread_id}] <<< {session_id[:8]} SKIP cache={time.time()-overall_start:.2f}s")
        return session_id, None, "skipped"

    cursor.execute("""
        SELECT content_preview, msg_type, role, tool_name
        FROM messages WHERE session_id = ?
        ORDER BY timestamp LIMIT ?
    """, (session_id, SUMMARY_HEAD_LINES))
    rows = cursor.fetchall()
    db_time = time.time() - db_start

    if not rows:
        print(f"    [THREAD {thread_id}] <<< {session_id[:8]} EMPTY db={db_time:.2f}s")
        return session_id, None, "empty"

    messages = []
    for preview, msg_type, role, tool in rows:
        if preview:
            messages.append({"type": msg_type, "role": role, "tool": tool, "content": preview[:200]})

    if not messages:
        print(f"    [THREAD {thread_id}] <<< {session_id[:8]} NO_MSG db={db_time:.2f}s")
        return session_id, None, "empty"

    data_str = json.dumps(messages, ensure_ascii=False, separators=(',', ':'))
    analysis_cmd = find_analysis_command()
    if not analysis_cmd:
        print(f"    [THREAD {thread_id}] <<< {session_id[:8]} NO_CLAUDE")
        return session_id, None, "no_claude"

    system_prompt = "Summarize this session in 1-2 sentences. Output plain text only."
    user_prompt = f"Summarize this ({len(messages)} msgs):"

    # API 调用时间
    api_start = time.time()
    try:
        cmd = [
            analysis_cmd,
            "-p",
            user_prompt,
            "--system-prompt",
            system_prompt,
            "--model",
            "haiku",
            "--no-session-persistence",
            "--output-format",
            "json",
        ]
        if ALLOW_UNSANDBOXED_AI:
            cmd.append("--dangerously-skip-permissions")

        result = subprocess.run(
            cmd,
            input=data_str, capture_output=True, text=True, encoding="utf-8", timeout=60
        )
        api_time = time.time() - api_start
        
        if result.returncode == 0:
            out = json.loads(result.stdout)
            summary = out.get("result", "")
            save_start = time.time()
            cursor.execute("UPDATE sessions SET summary = ?, summarized_at = ? WHERE session_id = ?",
                          (summary, datetime.now().isoformat(), session_id))
            conn.commit()
            save_time = time.time() - save_start
            total_time = time.time() - overall_start
            print(f"    [THREAD {thread_id}] <<< {session_id[:8]} OK api={api_time:.1f}s db={db_time:.2f}s save={save_time:.2f}s total={total_time:.1f}s")
            return session_id, summary, "success"
        else:
            api_time = time.time() - api_start
            total_time = time.time() - overall_start
            print(f"    [THREAD {thread_id}] <<< {session_id[:8]} FAIL code={result.returncode} api={api_time:.1f}s total={total_time:.1f}s")
            return session_id, None, f"error: {result.returncode}"
    except Exception as e:
        total_time = time.time() - overall_start
        print(f"    [THREAD {thread_id}] <<< {session_id[:8]} EXC {e} total={total_time:.1f}s")
        return session_id, None, f"exception: {e}"


def index_single_project(project_dir: Path, incremental: bool = True,
                         generate_summaries: bool = True) -> int:
    """索引单个项目（独立数据库）"""
    import time
    start_time = time.time()

    db_path = get_project_db_path(project_dir)
    conn = create_index_db(str(db_path))

    total = 0
    all_session_ids = set()

    for session_file in project_dir.rglob("*.jsonl"):
        count, session_ids = index_session_file(conn, str(session_file), incremental)
        all_session_ids.update(session_ids)
        if count > 0:
            print(f"  📝 {session_file.name[:40]}... (+{count})")
            for sid in session_ids:
                update_session_meta(conn, sid, str(session_file))

        total += count

    # 生成会话摘要（并行）
    if generate_summaries and total > 0:
        cursor = conn.cursor()
        cursor.execute("SELECT session_id FROM sessions WHERE summary IS NULL")
        unsummarized = [r[0] for r in cursor.fetchall()]

        if unsummarized:
            summary_start = time.time()
            print(f"  📋 生成 {len(unsummarized)} 个会话摘要 (并行 {MAX_SUMMARY_WORKERS})...")

            # 使用线程池并行生成摘要
            with ThreadPoolExecutor(max_workers=MAX_SUMMARY_WORKERS) as executor:
                futures = {executor.submit(_generate_summary_worker, (project_dir, sid)): sid
                          for sid in unsummarized}

                completed = 0
                for future in as_completed(futures):
                    sid = futures[future]
                    completed += 1
                    try:
                        result_sid, summary, status = future.result()
                        if status == "success":
                            print(f"    [{completed}/{len(unsummarized)}] ✓ ({time.time() - summary_start:.1f}s)")
                        elif status == "skipped":
                            print(f"    [{completed}/{len(unsummarized)}] ⊘ 已存在 ({time.time() - summary_start:.1f}s)")
                        else:
                            print(f"    [{completed}/{len(unsummarized)}] ✗ {status} ({time.time() - summary_start:.1f}s)")
                    except Exception as e:
                        print(f"    [{completed}/{len(unsummarized)}] ✗ {e} ({time.time() - summary_start:.1f}s)")

    wall_time = time.time() - start_time
    conn.close()
    if total > 0:
        print(f"  ⏱ 索引完成: {total} 条消息, 耗时 {wall_time:.1f}s")
    return total


def detect_session_project(session_file: Path, platform: RetracePlatform) -> Optional[str]:
    """Read a session file and return its encoded project bucket."""
    if platform.name == "dsh":
        cwd = dsh_platform.project_cwd(session_file)
        return encode_path(cwd) if cwd else None
    if platform.name == "claude":
        try:
            return session_file.relative_to(platform.projects_dir).parts[0]
        except ValueError:
            return session_file.parent.name
    if platform.name == "kimi":
        work_dir = kimi_platform.read_session_state(session_file).get("workDir")
        return encode_path(work_dir) if work_dir else None
    if platform.name == "omp":
        cwd = omp_platform.project_cwd(session_file)
        return encode_path(cwd) if cwd else None
    if platform.name == "grok":
        cwd = grok_platform.project_cwd(session_file)
        return encode_path(cwd) if cwd else None

    try:
        with open(session_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                project_name = extract_codex_project_name(record)
                if project_name:
                    return project_name
    except OSError:
        return None
    return None


def discover_project_files(platform: RetracePlatform, project_filter: str = None) -> Dict[Path, List[Path]]:
    """Group session files by retrace project directory for one platform."""
    projects_dir = platform.projects_dir
    projects_dir.mkdir(parents=True, exist_ok=True)
    grouped: Dict[Path, List[Path]] = {}

    for session_file in platform.iter_session_files():
        project_name = detect_session_project(session_file, platform)
        if not project_name:
            continue
        if project_filter and project_filter.lower() not in project_name.lower():
            continue
        project_dir = projects_dir / project_name
        grouped.setdefault(project_dir, []).append(session_file)

    return grouped


def index_session_files_for_project(project_dir: Path, session_files: List[Path],
                                    incremental: bool = True,
                                    generate_summaries: bool = True,
                                    platform_name: str = None) -> int:
    """Index an explicit set of Codex session files into one project DB."""
    import time
    start_time = time.time()

    project_dir.mkdir(parents=True, exist_ok=True)
    if not incremental:
        reset_index_db(project_dir)
    db_path = get_project_db_path(project_dir)
    conn = create_index_db(str(db_path))

    total = 0
    all_session_ids = set()
    for session_file in sorted(session_files):
        count, session_ids = index_session_file(
            conn, str(session_file), incremental, platform_name
        )
        all_session_ids.update(session_ids)
        if count > 0:
            print(f"  📝 {session_file.name[:40]}... (+{count})")
            for sid in session_ids:
                update_session_meta(conn, sid, str(session_file))
        total += count

    if generate_summaries and total > 0:
        cursor = conn.cursor()
        cursor.execute("SELECT session_id FROM sessions WHERE summary IS NULL")
        unsummarized = [r[0] for r in cursor.fetchall()]
        if unsummarized:
            print("  📋 跳过摘要生成：Codex exec 调用成本较高，可用 --no-summary 保持纯索引")

    conn.close()
    wall_time = time.time() - start_time
    if total > 0:
        print(f"  ⏱ 索引完成: {total} 条消息, 耗时 {wall_time:.1f}s")
    return total


def index_all_projects(project_filter: str = None, incremental: bool = True,
                       generate_summaries: bool = True, platform_name: str = "codex") -> int:
    """索引所有项目（每个项目独立数据库）"""
    import time
    overall_start = time.time()

    total = 0
    platform_count = 0

    for platform in get_platforms(platform_name):
        grouped = discover_project_files(platform, project_filter)
        if not grouped:
            print(f"❌ 找不到 {platform.name} 会话: {platform.home_dir}", file=sys.stderr)
            continue

        platform_count += 1
        print(f"🧭 platform={platform.name}")
        for pd, session_files in sorted(grouped.items(), key=lambda item: item[0].name):
            print(f"📂 {pd.name}")
            count = index_session_files_for_project(
                pd, session_files, incremental, generate_summaries, platform.name
            )
            total += count

    if platform_count == 0:
        return 0

    overall_time = time.time() - overall_start
    if total > 0:
        print(f"\n✅ 索引完成，共 {total} 条新消息, 总耗时 {overall_time:.1f}s")
    return total


def get_project_stats(project_dir: Path) -> dict:
    """获取单个项目的索引统计"""
    db_path = get_project_db_path(project_dir)
    if not db_path.exists():
        return {"error": "索引数据库不存在", "project": project_dir.name}

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM messages")
    total_messages = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM sessions")
    total_sessions = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM sessions WHERE summary IS NOT NULL")
    summarized = cursor.fetchone()[0]

    cursor.execute("SELECT msg_type, COUNT(*) FROM messages GROUP BY msg_type ORDER BY COUNT(*) DESC")
    by_type = dict(cursor.fetchall())

    cursor.execute("SELECT tool_name, COUNT(*) FROM messages WHERE tool_name IS NOT NULL GROUP BY tool_name ORDER BY COUNT(*) DESC LIMIT 10")
    top_tools = dict(cursor.fetchall())

    conn.close()

    return {
        "project": project_dir.name,
        "total_messages": total_messages,
        "total_sessions": total_sessions,
        "summarized_sessions": summarized,
        "by_type": by_type,
        "top_tools": top_tools,
        "db_size": db_path.stat().st_size
    }


def get_all_stats(project_filter: str = None, platform_name: str = "codex") -> list:
    """获取所有项目的统计"""
    stats = []
    for platform in get_platforms(platform_name):
        projects_dir = platform.projects_dir
        if not projects_dir.exists():
            continue
        for pd in sorted(projects_dir.iterdir()):
            if not pd.is_dir():
                continue
            if project_filter and project_filter.lower() not in pd.name.lower():
                continue

            db_path = get_project_db_path(pd)
            if db_path.exists():
                item = get_project_stats(pd)
                item["platform"] = platform.name
                stats.append(item)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Claude Code 会话日志索引器 (按项目独立索引)")
    parser.add_argument("--auto", action="store_true", help="自动索引所有项目")
    parser.add_argument("--project", help="过滤项目名")
    parser.add_argument("--platform", choices=SUPPORTED_PLATFORMS, default="codex",
                        help="会话平台")
    parser.add_argument("--no-incremental", action="store_true", help="重建索引")
    parser.add_argument("--no-summary", action="store_true", help="不生成会话摘要")
    parser.add_argument("--stats", action="store_true", help="显示统计信息")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    args = parser.parse_args()

    incremental = not args.no_incremental
    generate_summaries = not args.no_summary

    if args.stats:
        stats = get_all_stats(args.project, args.platform)
        if args.json:
            print(json.dumps(stats, ensure_ascii=False, indent=2))
        else:
            if not stats:
                print("❌ 没有找到索引数据库")
            else:
                total_msg = sum(s.get("total_messages", 0) for s in stats)
                total_sess = sum(s.get("total_sessions", 0) for s in stats)
                total_size = sum(s.get("db_size", 0) for s in stats)
                print(f"📊 索引统计 ({len(stats)} 个项目)")
                print(f"   消息总数: {total_msg:,}")
                print(f"   会话总数: {total_sess:,}")
                print(f"   总大小: {total_size:,} bytes")
                print()
                for s in stats:
                    if "error" not in s:
                        summ = s.get('summarized_sessions', 0)
                        sess = s.get('total_sessions', 0)
                        print(f"   📂 {s['project']}: {s['total_messages']:,} 消息, {sess} 会话 ({summ} 已摘要)")
        return

    if args.auto:
        total = index_all_projects(args.project, incremental, generate_summaries, args.platform)
        print(f"\n✅ 索引完成，共 {total:,} 条新消息")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
