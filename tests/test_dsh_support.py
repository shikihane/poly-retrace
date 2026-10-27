import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "retrace" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from platforms import dsh
from retrace_paths import decode_path, encode_path, find_session_files, get_platform

try:
    from compression import zstd
except ImportError:
    try:
        import zstandard
    except ImportError:
        compress = None
    else:
        compress = zstandard.ZstdCompressor().compress
else:
    compress = zstd.compress


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CWD = r"X:\Work\dsh-project"
SESSION = "session-root"
TIME = 1_790_000_000_000


def event(kind, seq, data):
    return {"type": kind, "seq": seq, "time": TIME + seq, "data": data}


def records(session_id=SESSION, cwd=CWD, **meta):
    return [
        {"type": "session", "version": 4, "id": session_id, "createdAt": TIME,
         "cwd": cwd, "isSeeded": False, **meta},
        event("user/message", 0, {"role": "user", "content": [
            {"type": "text", "text": "录音确认超时 req_id"},
            {"type": "image", "data": "private image"},
        ]}),
        event("assistant/message", 1, {"message": {"content": [
            {"type": "reasoning", "text": "private reasoning"},
            {"type": "text", "text": "检查设备状态"},
            {"type": "tool-call", "name": "pwsh", "arguments": "duplicate embedded call"},
        ]}, "stream": ["duplicate stream"]}),
        event("tool/call", 2, {"callId": "call-1", "name": "pwsh", "arguments": '{"command":"Get-Date"}'}),
        event("tool/result", 3, {"message": {"role": "tool", "toolCallId": "call-1", "content": [
            {"type": "text", "text": "command finished " + "完整结果" * 120},
        ]}}),
        event("session/title", 4, {"title": "Recorder timeout"}),
        event("turn/end", 5, {"reason": {"kind": "completed"}}),
    ]


def encode(rows):
    return b"".join((json.dumps(row, ensure_ascii=False) + "\n").encode() for row in rows)


def write_session(home, rows=None, compressed=False, directory=None):
    rows = records() if rows is None else rows
    path = home / "sessions" / "untrusted-lossy-project-name" / (directory or rows[0]["id"])
    path.mkdir(parents=True, exist_ok=True)
    path /= "session.v4.jsonl" + (".zstd" if compressed else "")
    raw = encode(rows)
    path.write_bytes(compress(raw) if compressed else raw)
    return path


class DshSupportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        env = patch.dict(os.environ, {"DSH_HOME": str(self.home)})
        env.start()
        self.addCleanup(env.stop)
        self.index = load_script("retrace-index")
        self.search = load_script("retrace-search")
        self.locate = load_script("retrace-locate")
        self.chronicle = load_script("retrace-chronicle")

    def connection(self):
        conn = self.index.create_index_db(str(self.home / "index.db"))
        self.addCleanup(conn.close)
        return conn

    def test_plain_pipeline_uses_header_cwd_and_selective_events(self):
        path = write_session(self.home)
        self.assertEqual(list(get_platform("dsh").iter_session_files()), [path])
        self.assertEqual(get_platform("dsh").projects_dir, self.home / "projects")
        self.assertEqual(decode_path(encode_path(CWD), "dsh"), CWD)
        total = self.index.index_all_projects("dsh-project", generate_summaries=False, platform_name="dsh")
        self.assertEqual(total, 6)
        db = self.home / "projects" / encode_path(CWD) / "retrace-index.db"
        conn = self.index.sqlite3.connect(db)
        self.addCleanup(conn.close)
        rows = conn.execute("SELECT msg_type, tool_name, search_text FROM messages").fetchall()
        self.assertEqual(sum(row[0] == "tool_use" for row in rows), 1)
        self.assertEqual({row[1] for row in rows if row[0] in {"tool_use", "tool_result"}}, {"pwsh"})
        text = " ".join(row[2] for row in rows)
        for skipped in ("private reasoning", "private image", "duplicate embedded call", "duplicate stream"):
            self.assertNotIn(skipped, text)
        hits = self.search.hybrid_search_list(conn, "录音确认超时 req_id", limit=10)
        self.assertEqual(hits[0]["session_id"], SESSION)
        msg_id = conn.execute("SELECT id FROM messages WHERE msg_type = 'tool_result'").fetchone()[0]
        full = self.search.get_full_content(conn, msg_id)
        self.assertNotIn("error", full)
        self.assertGreater(len(full["content"]), 300)
        self.assertEqual(full["raw"]["type"], "tool/result")
        self.assertTrue(any(row["is_target"] for row in self.search.get_context(conn, msg_id)))
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "retrace-search.py"), "command finished", "--platform", "dsh",
             "--project", "dsh-project", "--type", "tool_result", "--tool", "pwsh", "--session", SESSION, "--json"],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0]["tool"], "pwsh")

    @unittest.skipUnless(compress, "Zstandard decoder not installed")
    def test_compressed_frames_append_keep_offsets_tool_names_and_full_content(self):
        rows = records()
        path = write_session(self.home, rows[:4], compressed=True)
        conn = self.connection()
        self.assertEqual(self.index.index_session_file(conn, str(path), platform_name="dsh")[0], 4)
        with path.open("ab") as stream:
            stream.write(compress(encode(rows[4:])))
        self.assertEqual(self.index.index_session_file(conn, str(path), platform_name="dsh")[0], 2)
        self.assertEqual(self.index.index_session_file(conn, str(path), platform_name="dsh")[0], 0)
        msg_id, tool = conn.execute("SELECT id, tool_name FROM messages WHERE msg_type = 'tool_result'").fetchone()
        self.assertEqual(tool, "pwsh")
        full = self.search.get_full_content(conn, msg_id)
        self.assertNotIn("error", full)
        self.assertEqual(full["content"], rows[4]["data"]["message"]["content"][0]["text"])
        messages = self.chronicle.read_session_file(path)
        self.assertEqual([item["type"] for item in messages], ["user", "assistant", "tool_use", "tool_result"])
        self.assertEqual(messages[-1]["tool"], "pwsh")

    def test_rewrite_removes_stale_fts_rows_and_incomplete_line_is_retried(self):
        path = write_session(self.home)
        conn = self.connection()
        self.index.index_session_file(conn, str(path), platform_name="dsh")
        changed = records()
        changed[1]["data"]["content"] = "replacement prompt"
        raw = encode(changed)
        path.write_bytes(raw)
        self.index.index_session_file(conn, str(path), platform_name="dsh")
        self.assertFalse(self.search.hybrid_search_list(conn, "录音确认超时 req_id", limit=10))
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 6)
        extra = encode([event("user/message", 6, {"content": "late prompt"})])
        with path.open("ab") as stream:
            stream.write(extra[:-1])
        self.assertEqual(self.index.index_session_file(conn, str(path), platform_name="dsh")[0], 0)
        with path.open("ab") as stream:
            stream.write(b"\n")
        self.assertEqual(self.index.index_session_file(conn, str(path), platform_name="dsh")[0], 1)

    def test_family_locate_list_and_chronicle_keep_native_session_ids(self):
        root = write_session(self.home)
        child = write_session(self.home, records("child", parentSession=SESSION, origin="subagent"))
        grandchild = write_session(self.home, records("grandchild", cwd=r"X:\Work\isolated-worktree", parentSession="child", origin="subagent"))
        fork = write_session(self.home, records("fork", parentSession=SESSION))
        self.assertEqual(set(find_session_files(SESSION, "dsh")), {root, child, grandchild})
        self.assertEqual(set(find_session_files("child", "dsh")), {child, grandchild})
        self.assertEqual(find_session_files("session-r", "dsh"), [])
        located = self.locate.locate_session(session_id=SESSION, platform="dsh")
        self.assertEqual(located["project_path"], CWD)
        self.assertEqual(set(located["session_files"]), {str(root), str(child), str(grandchild)})
        self.assertNotIn("error", self.locate.locate_session(cwd=CWD, platform="dsh"))
        self.assertEqual(len(self.locate.list_sessions("dsh-project", "dsh")), 2)
        projects = self.locate.list_projects("dsh")
        self.assertEqual(projects[0]["session_count"], 2)
        self.assertEqual(projects[0]["total_size"], sum(p.stat().st_size for p in (root, child, grandchild, fork)))
        self.assertEqual(self.chronicle.find_session_file(SESSION, "dsh-project", "dsh"), root)
        self.assertIsNone(self.chronicle.find_session_file(SESSION, "different-project", "dsh"))
        self.assertIsNone(self.chronicle.find_session_file(SESSION, "isolated-worktree", "dsh"))
        self.assertEqual(self.chronicle.find_session_file("grandchild", "isolated-worktree", "dsh"), grandchild)
        messages = self.chronicle.read_session_files(find_session_files(SESSION, "dsh"))
        self.assertEqual({item["agent"] for item in messages}, {"main", "child", "grandchild"})
        conn = self.connection()
        for path in (root, child, grandchild):
            self.index.index_session_file(conn, str(path), platform_name="dsh")
        self.assertEqual({row[0] for row in conn.execute("SELECT DISTINCT session_id FROM messages")}, {SESSION, "child", "grandchild"})

    def test_missing_cwd_is_unattributed_and_unsupported_generations_refuse(self):
        rows = records()
        del rows[0]["cwd"]
        path = write_session(self.home, rows)
        self.assertIsNone(self.index.detect_session_project(path, get_platform("dsh")))
        located = self.locate.locate_session(session_id=SESSION, platform="dsh")
        self.assertIsNone(located["project_dir"])
        old = path.with_name("session.v3.jsonl")
        old.write_bytes(encode([{**rows[0], "version": 3}]))
        self.assertEqual(list(get_platform("dsh").iter_session_files()), [path])
        future = path.with_name("session.v5.jsonl")
        future.write_bytes(encode([{**rows[0], "version": 5}]))
        with self.assertRaisesRegex(ValueError, "Unsupported DSH session format"):
            list(get_platform("dsh").iter_session_files())
        with self.assertRaisesRegex(ValueError, "Unsupported DSH session format"):
            self.chronicle.read_session_file(old)

    @unittest.skipUnless(compress, "Zstandard decoder not installed")
    def test_encoding_switch_replaces_old_source_and_fallback_decoder_reads_frames(self):
        path = write_session(self.home)
        conn = self.connection()
        self.index.index_session_file(conn, str(path), platform_name="dsh")
        compressed = path.with_name(path.name + ".zstd")
        compressed.write_bytes(compress(encode(records()[:3])) + compress(encode(records()[3:])))
        path.unlink()
        self.index.index_session_file(conn, str(compressed), platform_name="dsh")
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 6)
        self.assertEqual({row[0] for row in conn.execute("SELECT DISTINCT session_file FROM messages")}, {str(compressed)})
        if importlib.util.find_spec("zstandard"):
            with patch.dict(sys.modules, {"compression": None}):
                with dsh.open_binary(compressed) as stream:
                    stream.seek(len(encode(records()[:3])))
                    self.assertEqual(json.loads(stream.readline())["type"], "tool/call")
        with patch.dict(sys.modules, {"compression": None, "zstandard": None}):
            with self.assertRaisesRegex(RuntimeError, "pip install zstandard"):
                with dsh.open_binary(compressed):
                    pass

    def test_invalid_event_rolls_back_and_duplicate_encodings_are_rejected(self):
        path = write_session(self.home)
        conn = self.connection()
        self.index.index_session_file(conn, str(path), platform_name="dsh")
        original = conn.execute("SELECT id, search_text FROM messages").fetchall()
        changed = records()
        changed[1]["data"]["content"] = "must roll back"
        changed.append({"type": "assistant/message", "data": {"message": {"content": "missing time"}}})
        path.write_bytes(encode(changed))
        with self.assertRaises(KeyError):
            self.index.index_session_file(conn, str(path), platform_name="dsh")
        self.assertEqual(conn.execute("SELECT id, search_text FROM messages").fetchall(), original)
        path.with_name(path.name + ".zstd").write_bytes(b"duplicate")
        with self.assertRaisesRegex(ValueError, "Ambiguous DSH session encodings"):
            list(get_platform("dsh").iter_session_files())

    def test_all_platform_commands_offer_dsh(self):
        for name in ("retrace-index", "retrace-search", "retrace-analyze", "retrace-locate", "retrace-chronicle", "clean-index", "list-session"):
            result = subprocess.run([sys.executable, str(SCRIPTS / f"{name}.py"), "--help"], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("dsh", result.stdout)


if __name__ == "__main__":
    unittest.main()
