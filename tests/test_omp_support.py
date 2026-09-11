import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "retrace" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OmpSupportTests(unittest.TestCase):
    session_id = "01a00641-fd66-7000-996b-2e29d8d6287d"
    cwd = r"X:\Work\omp-project"

    @staticmethod
    def write_jsonl(path: Path, records: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
            encoding="utf-8",
        )

    @staticmethod
    def fixed_title_line(title: str) -> str:
        record = {
            "type": "title",
            "v": 1,
            "title": title,
            "updatedAt": "2026-08-15T16:29:43.100Z",
            "pad": "",
        }
        serialized = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        padding = 256 - len((serialized + "\n").encode("utf-8"))
        if padding < 0:
            raise ValueError("title fixture exceeds OMP's fixed-width slot")
        record["pad"] = " " * padding
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        if len(line.encode("utf-8")) != 256:
            raise AssertionError("invalid OMP title slot fixture")
        return line

    def make_session(self, root: Path) -> Path:
        session = (
            root
            / "sessions"
            / "opaque-omp-bucket"
            / f"2026-08-15T16-29-43-142Z_{self.session_id}.jsonl"
        )
        records = [
            {
                "type": "title",
                "v": 1,
                "title": "OMP tool support",
                "updatedAt": "2026-08-15T16:29:43.100Z",
                "pad": "",
            },
            {
                "type": "session",
                "version": 3,
                "id": self.session_id,
                "timestamp": "2026-08-15T16:29:43.142Z",
                "cwd": self.cwd,
                "title": "stale header title",
            },
            {
                "type": "session_init",
                "id": "init0001",
                "parentId": None,
                "timestamp": "2026-08-15T16:29:44.000Z",
                "task": "Inspect the OMP transcript",
                "tools": ["read", "bash"],
                "agent": "scout",
            },
            {
                "type": "message",
                "id": "user0001",
                "parentId": "init0001",
                "timestamp": "2026-08-15T16:29:45.000Z",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "Inspect the OMP transcript"}],
                    "timestamp": 1_755_276_585_000,
                },
            },
            {
                "type": "message",
                "id": "asst0001",
                "parentId": "user0001",
                "timestamp": "2026-08-15T16:29:46.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "private chain of thought"},
                        {"type": "text", "text": "I will inspect both files."},
                        {
                            "type": "toolCall",
                            "id": "call-read",
                            "name": "read",
                            "arguments": {"path": "README.md"},
                        },
                        {
                            "type": "toolCall",
                            "id": "call-bash",
                            "name": "bash",
                            "arguments": {"command": "git status --short"},
                        },
                    ],
                    "timestamp": 1_755_276_586_000,
                },
            },
            {
                "type": "message",
                "id": "result001",
                "parentId": "asst0001",
                "timestamp": "2026-08-15T16:29:47.000Z",
                "message": {
                    "role": "toolResult",
                    "toolCallId": "call-read",
                    "toolName": "read",
                    "content": [{"type": "text", "text": "README contents"}],
                    "isError": False,
                    "timestamp": 1_755_276_587_000,
                },
            },
            {
                "type": "message",
                "id": "result002",
                "parentId": "result001",
                "timestamp": "2026-08-15T16:29:48.000Z",
                "message": {
                    "role": "toolResult",
                    "toolCallId": "call-bash",
                    "toolName": "bash",
                    "content": [{"type": "text", "text": "working tree clean"}],
                    "isError": False,
                    "timestamp": 1_755_276_588_000,
                },
            },
        ]
        self.write_jsonl(session, records)
        return session

    def make_task_sidecar(self, parent: Path) -> tuple[Path, str, str]:
        run_id = "task-run-0001"
        child_session_id = "01a00641-fd66-7000-aaaa-111111111111"
        task = "Inspect the OMP transcript"
        sidecar = parent.with_suffix("") / f"{run_id}.jsonl"
        records = [
            {
                "type": "title",
                "v": 1,
                "title": "OMP task agent",
                "updatedAt": "2026-08-15T16:30:00.000Z",
                "pad": "",
            },
            {
                "type": "session",
                "version": 3,
                "id": child_session_id,
                "timestamp": "2026-08-15T16:30:00.000Z",
                "cwd": r"X:\Temp\omp-isolated-worktree",
            },
            {
                "type": "session_init",
                "id": "init-task",
                "parentId": None,
                "timestamp": "2026-08-15T16:30:01.000Z",
                "task": task,
                "tools": ["grep"],
                "agent": "scout",
            },
            {
                "type": "message",
                "id": "user-task",
                "parentId": "init-task",
                "timestamp": "2026-08-15T16:30:02.000Z",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": task}],
                },
            },
            {
                "type": "message",
                "id": "assistant-task",
                "parentId": "user-task",
                "timestamp": "2026-08-15T16:30:03.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Task agent finding"},
                        {
                            "type": "toolCall",
                            "id": "call-grep",
                            "name": "grep",
                            "arguments": {"pattern": "toolCall"},
                        },
                    ],
                },
            },
            {
                "type": "message",
                "id": "result-task",
                "parentId": "assistant-task",
                "timestamp": "2026-08-15T16:30:04.000Z",
                "message": {
                    "role": "toolResult",
                    "toolCallId": "call-grep",
                    "toolName": "grep",
                    "content": [{"type": "text", "text": "one match"}],
                    "isError": False,
                },
            },
        ]
        self.write_jsonl(sidecar, records)
        return sidecar, run_id, child_session_id

    def omp_environment(self, root: Path):
        return mock.patch.dict(
            os.environ,
            {
                "PI_CODING_AGENT_DIR": str(root / "agent"),
                "PI_CODING_AGENT_SESSION_DIR": str(root / "sessions"),
                "OMP_PROFILE": "",
            },
        )

    def test_omp_platform_paths_honor_official_overrides(self):
        from retrace_paths import get_platform

        with tempfile.TemporaryDirectory() as tmp, self.omp_environment(Path(tmp)):
            platform = get_platform("omp")

            self.assertEqual(platform.name, "omp")
            self.assertEqual(platform.home_dir, Path(tmp) / "agent")
            self.assertEqual(platform.projects_dir, Path(tmp) / "agent" / "projects")
            self.assertEqual(platform.session_roots, (Path(tmp) / "sessions",))
            self.assertIn("omp", platform.command_names)

    def test_omp_named_profile_uses_profile_agent_home(self):
        from retrace_paths import get_platform

        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ,
            {
                "OMP_PROFILE": "work",
                "PI_PROFILE": "ignored",
                "PI_CONFIG_DIR": str(Path(tmp) / ".omp"),
                "PI_CODING_AGENT_DIR": str(Path(tmp) / "default-agent"),
                "PI_CODING_AGENT_SESSION_DIR": "",
            },
        ):
            platform = get_platform("omp")

            expected = Path(tmp) / ".omp" / "profiles" / "work" / "agent"
            self.assertEqual(platform.home_dir, expected)
            self.assertEqual(platform.session_roots, (expected / "sessions",))

    def test_header_lookup_skips_mutable_title_slot(self):
        from platforms import omp

        with tempfile.TemporaryDirectory() as tmp:
            session = self.make_session(Path(tmp))

            header = omp.read_session_header(session)

            self.assertEqual(header["id"], self.session_id)
            self.assertEqual(omp.session_id_for_file(session), self.session_id)
            self.assertEqual(omp.session_cwd(session), self.cwd)

    def test_omp_normalization_splits_text_and_parallel_tool_calls(self):
        from platforms import omp

        context = {}
        omp.normalize_record({"type": "title", "title": "A title"}, context)
        meta = omp.normalize_record(
            {
                "type": "session",
                "id": self.session_id,
                "timestamp": "2026-08-15T00:00:00.000Z",
                "cwd": self.cwd,
            },
            context,
        )
        records = omp.normalize_record(
            {
                "type": "message",
                "id": "entry-1",
                "parentId": None,
                "timestamp": "2026-08-15T00:00:01.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "do not index"},
                        {"type": "text", "text": "visible answer"},
                        {
                            "type": "toolCall",
                            "id": "call-1",
                            "name": "read",
                            "arguments": {"path": "a.txt"},
                        },
                        {
                            "type": "toolCall",
                            "id": "call-2",
                            "name": "bash",
                            "arguments": {"command": "pwd"},
                        },
                    ],
                },
            },
            context,
        )

        self.assertEqual(meta[0]["msg_type"], "session_meta")
        self.assertIn("A title", meta[0]["search_text"])
        self.assertEqual([item["msg_type"] for item in records], ["assistant", "tool_use", "tool_use"])
        self.assertEqual([item["tool_name"] for item in records[1:]], ["read", "bash"])
        self.assertTrue(all(item["session_id"] == self.session_id for item in records))
        self.assertFalse(any("do not index" in item["search_text"] for item in records))

    def test_omp_task_sidecar_uses_unique_run_id_without_duplicate_task(self):
        from platforms import omp

        task = "Inspect the OMP transcript"
        with tempfile.TemporaryDirectory() as tmp:
            parent = self.make_session(Path(tmp))
            sidecar, run_id, _ = self.make_task_sidecar(parent)

            self.assertEqual(omp.agent_id_for_file(sidecar), run_id)
            context = {"session_id": "", "agent_id": omp.agent_id_for_file(sidecar)}
            normalized = []
            for line in sidecar.read_text(encoding="utf-8").splitlines():
                normalized.extend(omp.normalize_record(json.loads(line), context))

            users = [item for item in normalized if item["msg_type"] == "user"]
            self.assertEqual(len(users), 1)
            self.assertEqual(users[0]["search_text"], task)
            self.assertEqual(users[0]["agent_id"], run_id)
            self.assertNotEqual(users[0]["agent_id"], "scout")

    def test_omp_index_supports_multiple_parts_and_incremental_append(self):
        retrace_index = load_script("retrace-index")
        retrace_search = load_script("retrace-search")

        with tempfile.TemporaryDirectory() as tmp:
            session = self.make_session(Path(tmp))
            conn = retrace_index.create_index_db(str(Path(tmp) / "index.db"))
            try:
                count, session_ids = retrace_index.index_session_file(
                    conn, str(session), incremental=False, platform_name="omp"
                )

                self.assertEqual(count, 7)
                self.assertEqual(session_ids, {self.session_id})
                initial_meta = conn.execute(
                    "SELECT search_text FROM messages WHERE msg_type = 'session_meta'"
                ).fetchone()[0]
                self.assertIn("OMP tool support", initial_meta)
                self.assertNotIn("stale header title", initial_meta)
                parts = conn.execute(
                    "SELECT msg_type, tool_name, part_index, search_text "
                    "FROM messages WHERE line_no = 5 ORDER BY part_index"
                ).fetchall()
                self.assertEqual(
                    [(row[0], row[1], row[2]) for row in parts],
                    [("assistant", "", 0), ("tool_use", "read", 1), ("tool_use", "bash", 2)],
                )
                self.assertNotIn("private chain of thought", " ".join(row[3] for row in parts))

                target_id = conn.execute(
                    "SELECT id FROM messages WHERE line_no = 5 AND part_index = 1"
                ).fetchone()[0]
                context = retrace_search.get_context(conn, target_id, before=0, after=0)
                self.assertEqual(
                    [item["type"] for item in context],
                    ["assistant", "tool_use", "tool_use"],
                )
                self.assertEqual(
                    [item["id"] for item in context if item["is_target"]],
                    [target_id],
                )

                lines = session.read_text(encoding="utf-8").splitlines()
                title = json.loads(lines[0])
                title["title"] = "OMP code support"
                replacement = json.dumps(title, ensure_ascii=False)
                self.assertEqual(len(replacement.encode()), len(lines[0].encode()))
                lines[0] = replacement
                session.write_text("\n".join(lines) + "\n", encoding="utf-8")

                refreshed, refreshed_ids = retrace_index.index_session_file(
                    conn, str(session), incremental=True, platform_name="omp"
                )
                self.assertEqual(refreshed, 0)
                self.assertEqual(refreshed_ids, set())
                meta_id, meta_text = conn.execute(
                    "SELECT id, search_text FROM messages WHERE msg_type = 'session_meta'"
                ).fetchone()
                self.assertIn("OMP code support", meta_text)
                self.assertEqual(
                    conn.execute(
                        "SELECT search_text FROM messages_fts WHERE rowid = ?", (meta_id,)
                    ).fetchone()[0],
                    meta_text,
                )
                with mock.patch.object(
                    retrace_index,
                    "_hash_file_region",
                    wraps=retrace_index._hash_file_region,
                ) as hash_region:
                    unchanged, unchanged_ids = retrace_index.index_session_file(
                        conn, str(session), incremental=True, platform_name="omp"
                    )
                self.assertEqual((unchanged, unchanged_ids), (0, set()))
                hash_region.assert_not_called()

                with session.open("a", encoding="utf-8") as f:
                    f.write(
                        json.dumps(
                            {
                                "type": "custom_message",
                                "id": "custom01",
                                "parentId": "result002",
                                "timestamp": "2026-08-15T16:29:49.000Z",
                                "customType": "notice",
                                "content": "incremental OMP context",
                                "display": True,
                                "attribution": "agent",
                            }
                        )
                        + "\n"
                    )

                added, incremental_ids = retrace_index.index_session_file(
                    conn, str(session), incremental=True, platform_name="omp"
                )
                self.assertEqual(added, 1)
                self.assertEqual(incremental_ids, {self.session_id})
                row = conn.execute(
                    "SELECT msg_type, role, session_id FROM messages "
                    "WHERE search_text = 'incremental OMP context'"
                ).fetchone()
                self.assertEqual(row, ("assistant", "assistant", self.session_id))
            finally:
                conn.close()

    def test_omp_incremental_index_rebuilds_after_atomic_session_rewrite(self):
        retrace_index = load_script("retrace-index")

        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / f"legacy_{self.session_id}.jsonl"
            header = {
                "type": "session",
                "version": 3,
                "id": self.session_id,
                "timestamp": "2026-08-15T16:29:43.142Z",
                "cwd": self.cwd,
                "title": "stale legacy title",
            }
            self.write_jsonl(
                session,
                [
                    header,
                    {
                        "type": "message",
                        "id": "old-user",
                        "timestamp": "2026-08-15T16:29:44.000Z",
                        "message": {"role": "user", "content": "old prompt"},
                    },
                    {
                        "type": "message",
                        "id": "old-assistant",
                        "timestamp": "2026-08-15T16:29:45.000Z",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {"type": "text", "text": "obsolete " + "x" * 5000}
                            ],
                        },
                    },
                ],
            )
            original_size = session.stat().st_size
            conn = retrace_index.create_index_db(str(Path(tmp) / "rewrite.db"))
            try:
                count, _ = retrace_index.index_session_file(
                    conn, str(session), incremental=False, platform_name="omp"
                )
                self.assertEqual(count, 3)

                new_user = {
                    "type": "message",
                    "id": "new-user",
                    "timestamp": "2026-08-15T16:30:00.000Z",
                    "message": {"role": "user", "content": "new prompt after rewrite"},
                }
                rewritten = self.fixed_title_line("current title")
                rewritten += json.dumps(header, ensure_ascii=False) + "\n"
                rewritten += json.dumps(new_user, ensure_ascii=False) + "\n"
                session.write_bytes(rewritten.encode("utf-8"))
                self.assertLess(session.stat().st_size, original_size)

                rebuilt, session_ids = retrace_index.index_session_file(
                    conn, str(session), incremental=True, platform_name="omp"
                )

                self.assertEqual(rebuilt, 2)
                self.assertEqual(session_ids, {self.session_id})
                rows = conn.execute(
                    "SELECT msg_type, search_text, byte_offset FROM messages "
                    "ORDER BY line_no, part_index"
                ).fetchall()
                self.assertEqual([row[0] for row in rows], ["session_meta", "user"])
                self.assertIn("current title", rows[0][1])
                self.assertEqual(rows[0][2], 256)
                self.assertEqual(rows[1][1], "new prompt after rewrite")
                self.assertFalse(any("obsolete" in row[1] for row in rows))
                self.assertEqual(
                    int(
                        conn.execute(
                            "SELECT value FROM meta WHERE key = ?",
                            (f"offset:{session}",),
                        ).fetchone()[0]
                    ),
                    session.stat().st_size,
                )
            finally:
                conn.close()

    def test_existing_index_schema_migrates_to_part_index(self):
        retrace_index = load_script("retrace-index")

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"
            legacy = sqlite3.connect(db_path)
            legacy.execute(
                """
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_file TEXT NOT NULL,
                    line_no INTEGER NOT NULL,
                    byte_offset INTEGER NOT NULL,
                    byte_length INTEGER NOT NULL,
                    uuid TEXT, parent_uuid TEXT, session_id TEXT, timestamp TEXT,
                    msg_type TEXT, role TEXT, tool_name TEXT, content_preview TEXT,
                    content_hash TEXT, UNIQUE(session_file, byte_offset)
                )
                """
            )
            legacy.execute(
                "INSERT INTO messages "
                "(session_file, line_no, byte_offset, byte_length, msg_type, content_preview) "
                "VALUES ('session.jsonl', 1, 0, 20, 'assistant', 'old row')"
            )
            legacy.execute(
                "CREATE VIRTUAL TABLE messages_fts USING fts5("
                "search_text, msg_type, role, tool_name)"
            )
            legacy.execute(
                "INSERT INTO messages_fts(rowid, search_text, msg_type, role, tool_name) "
                "VALUES (1, 'old row', 'assistant', 'assistant', '')"
            )
            legacy.commit()
            legacy.close()

            conn = retrace_index.create_index_db(str(db_path))
            try:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
                self.assertIn("part_index", columns)
                conn.execute(
                    "INSERT INTO messages "
                    "(session_file, line_no, byte_offset, byte_length, part_index, msg_type) "
                    "VALUES ('session.jsonl', 1, 0, 20, 1, 'tool_use')"
                )
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 2
                )
                self.assertEqual(
                    conn.execute(
                        "SELECT rowid FROM messages_fts "
                        "WHERE messages_fts MATCH 'old'"
                    ).fetchone()[0],
                    1,
                )
            finally:
                conn.close()

    def test_part_index_migration_is_atomic_and_recovers_interrupted_schema(self):
        retrace_index = load_script("retrace-index")

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "migration.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_file TEXT NOT NULL,
                    line_no INTEGER NOT NULL,
                    byte_offset INTEGER NOT NULL,
                    byte_length INTEGER NOT NULL,
                    uuid TEXT, parent_uuid TEXT, session_id TEXT, timestamp TEXT,
                    msg_type TEXT, role TEXT, tool_name TEXT, content_preview TEXT,
                    content_hash TEXT, UNIQUE(session_file, byte_offset)
                );
                INSERT INTO messages
                    (session_file, line_no, byte_offset, byte_length, msg_type,
                     content_preview)
                VALUES ('session.jsonl', 1, 0, 20, 'assistant', 'old row');
                CREATE VIRTUAL TABLE messages_fts USING fts5(
                    search_text, msg_type, role, tool_name
                );
                """
            )

            def deny_migration_insert(action, arg1, _arg2, _db, _trigger):
                if action == sqlite3.SQLITE_INSERT and arg1 == "messages":
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK

            conn.set_authorizer(deny_migration_insert)
            with self.assertRaises(sqlite3.DatabaseError):
                retrace_index.ensure_index_schema(conn)
            conn.set_authorizer(None)

            columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
            self.assertNotIn("part_index", columns)
            self.assertFalse(
                conn.execute(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'messages_legacy'"
                ).fetchone()
            )
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 1)

            # Simulate the exact half-migrated layout produced by older builds.
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
                    uuid TEXT, parent_uuid TEXT, session_id TEXT, timestamp TEXT,
                    msg_type TEXT, role TEXT, tool_name TEXT, agent_id TEXT DEFAULT '',
                    content_preview TEXT, search_text TEXT, content_hash TEXT,
                    UNIQUE(session_file, byte_offset, part_index)
                )
                """
            )
            conn.commit()

            conn.close()
            conn = retrace_index.create_index_db(str(db_path))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 1)
            self.assertFalse(
                conn.execute(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'messages_legacy'"
                ).fetchone()
            )
            self.assertIn(
                "part_index",
                {row[1] for row in conn.execute("PRAGMA table_info(messages)")},
            )
            conn.close()

    def test_context_query_remains_compatible_with_legacy_indexes(self):
        retrace_search = load_script("retrace-search")
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY,
                    session_file TEXT NOT NULL,
                    line_no INTEGER NOT NULL,
                    timestamp TEXT,
                    msg_type TEXT,
                    role TEXT,
                    tool_name TEXT,
                    content_preview TEXT
                );
                INSERT INTO messages VALUES
                    (1, 'old.jsonl', 1, '', 'user', 'user', '', 'one'),
                    (2, 'old.jsonl', 2, '', 'assistant', 'assistant', '', 'two');
                """
            )

            context = retrace_search.get_context(conn, 2, before=1, after=0)

            self.assertEqual([item["id"] for item in context], [1, 2])
            self.assertEqual(
                [item["id"] for item in context if item["is_target"]], [2]
            )
        finally:
            conn.close()

    def test_omp_project_discovery_locate_listing_and_chronicle(self):
        from platforms import omp
        import retrace_paths

        retrace_index = load_script("retrace-index")
        retrace_locate = load_script("retrace-locate")
        retrace_chronicle = load_script("retrace-chronicle")

        with tempfile.TemporaryDirectory() as tmp, self.omp_environment(Path(tmp)):
            session = self.make_session(Path(tmp))
            sidecar, run_id, _ = self.make_task_sidecar(session)
            platform = retrace_paths.get_platform("omp")
            grouped = retrace_index.discover_project_files(platform, "omp-project")

            self.assertEqual(list(grouped.values()), [[session]])
            project_dir = next(iter(grouped))
            self.assertEqual(project_dir.name, retrace_paths.encode_path(self.cwd))
            self.assertNotEqual(project_dir.name, session.parent.name)
            all_grouped = retrace_index.discover_project_files(platform)
            isolated_dir = platform.projects_dir / retrace_paths.encode_path(
                r"X:\Temp\omp-isolated-worktree"
            )
            self.assertEqual(all_grouped[project_dir], [session])
            self.assertEqual(all_grouped[isolated_dir], [sidecar])

            matches = retrace_paths.find_session_files(self.session_id[:12].upper(), "omp")
            self.assertEqual(matches, [session, sidecar])
            located = retrace_locate.locate_session(
                session_id=self.session_id[:12].upper(), platform="omp"
            )
            self.assertEqual(located["session_id"], self.session_id)
            self.assertEqual(located["session_file"], str(session))
            self.assertEqual(located["session_files"], [str(session), str(sidecar)])
            self.assertEqual(located["project_path"], self.cwd)
            child_id = omp.session_id_for_file(sidecar)
            child_located = retrace_locate.locate_session(
                session_id=child_id, platform="omp"
            )
            self.assertEqual(
                child_located["project_path"], r"X:\Temp\omp-isolated-worktree"
            )

            by_cwd = retrace_locate.locate_session(cwd=self.cwd, platform="omp")
            self.assertEqual(by_cwd["session_id"], self.session_id)
            by_cwd_case = retrace_locate.locate_session(
                cwd=self.cwd.lower(), platform="omp"
            )
            self.assertEqual(by_cwd_case["session_id"], self.session_id)
            projects = retrace_locate.list_projects("omp")
            self.assertEqual([item["path"] for item in projects], [self.cwd])
            self.assertEqual(projects[0]["session_count"], 1)
            isolated_dir.mkdir(parents=True, exist_ok=True)
            sqlite3.connect(isolated_dir / "retrace-index.db").close()
            projects_after_child_index = retrace_locate.list_projects("omp")
            self.assertEqual(
                [item["path"] for item in projects_after_child_index], [self.cwd]
            )
            self.assertEqual(
                retrace_locate.list_sessions("omp-isolated-worktree", "omp"), []
            )
            sessions = retrace_locate.list_sessions("omp-project", "omp")
            self.assertEqual(sessions[0]["session_id"], self.session_id)
            self.assertEqual(sessions[0]["files"], [str(session), str(sidecar)])

            found = retrace_chronicle.find_session_file(
                self.session_id, "omp-project", "omp"
            )
            self.assertEqual(found, session)
            self.assertIsNone(
                retrace_chronicle.find_session_file(
                    self.session_id, "omp-isolated-worktree", "omp"
                )
            )
            self.assertIsNone(
                retrace_chronicle.find_session_file(
                    child_id, "omp-project", "omp"
                )
            )
            self.assertEqual(
                retrace_chronicle.find_session_file(
                    child_id, "omp-isolated-worktree", "omp"
                ),
                sidecar,
            )
            chronicle = retrace_chronicle.read_session_files(matches)
            types = [item["type"] for item in chronicle]
            self.assertEqual(types.count("tool_use"), 3)
            self.assertEqual(types.count("tool_result"), 3)
            self.assertEqual(types.count("user"), 2)
            self.assertIn("session_meta", types)
            self.assertFalse(any("private chain of thought" in item["content"] for item in chronicle))
            self.assertTrue(any(item.get("agent") == "main" for item in chronicle))
            self.assertTrue(any(item.get("agent") == run_id for item in chronicle))
            self.assertEqual(
                [item["tool"] for item in chronicle if item["type"] == "tool_use"],
                ["read", "bash", "grep"],
            )
            self.assertEqual(
                retrace_index.choose_canonical_session_file(
                    self.session_id, str(sidecar), str(session)
                ),
                str(session),
            )

    def test_omp_ambiguous_session_prefix_is_rejected(self):
        retrace_locate = load_script("retrace-locate")
        retrace_chronicle = load_script("retrace-chronicle")

        with tempfile.TemporaryDirectory() as tmp, self.omp_environment(Path(tmp)):
            first = self.make_session(Path(tmp))
            other_id = self.session_id[:12] + "-ffff-7000-8888-111111111111"
            records = [json.loads(line) for line in first.read_text(encoding="utf-8").splitlines()]
            for record in records:
                if record.get("type") == "session":
                    record["id"] = other_id
            second = first.with_name(f"2026-08-15T17-00-00-000Z_{other_id}.jsonl")
            self.write_jsonl(second, records)

            prefix = self.session_id[:12]
            located = retrace_locate.locate_session(session_id=prefix, platform="omp")

            self.assertIn("不唯一", located["error"])
            self.assertIsNone(
                retrace_chronicle.find_session_file(prefix, "omp-project", "omp")
            )
            exact = retrace_locate.locate_session(
                session_id=self.session_id, platform="omp"
            )
            self.assertEqual(exact["session_file"], str(first))

    def test_platform_clis_offer_omp(self):
        scripts = [
            "retrace-index.py",
            "retrace-search.py",
            "retrace-analyze.py",
            "retrace-locate.py",
            "retrace-chronicle.py",
            "clean-index.py",
            "list-session.py",
        ]
        for name in scripts:
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / name), "--help"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(result.returncode, 0, (name, result.stderr))
            self.assertIn("omp", result.stdout.lower(), name)

    def test_omp_documentation_stays_consistent(self):
        docs = [
            ROOT / "AGENTS.md",
            ROOT / "README.md",
            ROOT / "README_CN.md",
            ROOT / "skills" / "retrace" / "SKILL.md",
            ROOT / "skills" / "retrace" / "references" / "architecture.md",
        ]
        for path in docs:
            content = path.read_text(encoding="utf-8")
            self.assertIn("--platform omp", content, path.name)
            self.assertIn("PI_CODING_AGENT_DIR", content, path.name)
            self.assertIn("toolCall", content, path.name)

        validators = [
            SCRIPTS / "validate-skill.py",
            SCRIPTS / "validate-skill.ps1",
        ]
        for path in validators:
            self.assertIn("omp.py", path.read_text(encoding="utf-8"), path.name)


if __name__ == "__main__":
    unittest.main()
