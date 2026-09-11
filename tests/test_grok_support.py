import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "retrace" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SESSION_ID = "01a08e22-79ea-71e2-959a-94b37e5c0c0f"
WORK_DIR = r"X:\Work\grok-project"
GROUP_DIR = "X%3A%5CWork%5Cgrok-project"
TIMESTAMP_S = 1_700_000_000


def grok_update(update: dict, seq: int, method: str = "session/update") -> dict:
    return {
        "timestamp": TIMESTAMP_S + seq,
        "method": method,
        "params": {
            "sessionId": SESSION_ID,
            "update": update,
            "_meta": {
                "eventId": f"{SESSION_ID}-{seq}",
                "agentTimestampMs": (TIMESTAMP_S + seq) * 1000,
            },
        },
    }


def sample_records() -> list[dict]:
    return [
        grok_update(
            {"sessionUpdate": "hook_execution", "event_name": "session_start", "runs": []},
            1,
            method="_x.ai/session/update",
        ),
        grok_update(
            {
                "sessionUpdate": "user_message_chunk",
                "content": {"type": "text", "text": "录音确认超时 req_id"},
            },
            2,
        ),
        grok_update(
            {
                "sessionUpdate": "agent_thought_chunk",
                "content": {"type": "text", "text": "private reasoning"},
            },
            3,
        ),
        grok_update(
            {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "检查设备状态"},
            },
            4,
        ),
        grok_update(
            {
                "sessionUpdate": "tool_call",
                "toolCallId": "call-1",
                "title": "run_terminal_command",
                "rawInput": {"command": "pwsh -NoLogo"},
                "_meta": {"x.ai/tool": {"name": "run_terminal_command"}},
            },
            5,
        ),
        grok_update(
            {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "call-1",
                "rawInput": {"command": "pwsh -NoLogo"},
            },
            6,
        ),
        grok_update(
            {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "call-1",
                "status": "completed",
                "content": [
                    {"type": "content", "content": {"type": "text", "text": "command finished"}}
                ],
            },
            7,
        ),
        grok_update(
            {"sessionUpdate": "turn_completed", "stop_reason": "end_turn"},
            8,
            method="_x.ai/session/update",
        ),
    ]


class GrokSupportTests(unittest.TestCase):
    @staticmethod
    def write_jsonl(path: Path, records: list[dict]):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
            encoding="utf-8",
        )

    @staticmethod
    def make_session(home: Path, group: str = GROUP_DIR, session_id: str = SESSION_ID,
                     summary: dict = None) -> Path:
        session = home / "sessions" / group / session_id
        session.mkdir(parents=True, exist_ok=True)
        if summary is None:
            summary = {
                "info": {"id": session_id, "cwd": WORK_DIR},
                "generated_title": "Recorder timeout",
                "created_at": "2026-07-29T01:00:00Z",
                "updated_at": "2026-07-29T02:00:00Z",
            }
        (session / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False), encoding="utf-8"
        )
        return session / "updates.jsonl"

    def test_grok_platform_has_its_own_home_and_finds_updates_files(self):
        from retrace_paths import get_platform

        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("GROK_HOME")
            os.environ["GROK_HOME"] = tmp
            try:
                home = Path(tmp)
                updates = self.make_session(home)
                updates.write_text("", encoding="utf-8")
                other = self.make_session(home, session_id="01a08e33-0000-7000-8000-000000000000")
                other.write_text("", encoding="utf-8")

                grok = get_platform("grok")

                self.assertEqual(grok.name, "grok")
                self.assertEqual(grok.home_dir, home)
                self.assertEqual(grok.projects_dir, home / "projects")
                self.assertEqual(set(grok.iter_session_files()), {updates, other})
                self.assertNotEqual(grok.home_dir, get_platform("codex").home_dir)
                self.assertNotEqual(grok.home_dir, get_platform("claude").home_dir)
            finally:
                if previous is None:
                    os.environ.pop("GROK_HOME", None)
                else:
                    os.environ["GROK_HOME"] = previous

    def test_grok_updates_normalize_messages_and_skip_protocol_noise(self):
        from platforms import grok as grok_platform

        records = sample_records()
        tool_names = {}
        normalized = []
        for record in records:
            item = grok_platform.normalize_record(
                record, session_id=SESSION_ID, agent_id="main", tool_names=tool_names
            )
            if item and item.get("msg_type") == "tool_use":
                tool_names[item["tool_call_id"]] = item["tool_name"]
            normalized.append(item)

        kinds = [item["msg_type"] if item else None for item in normalized]
        self.assertEqual(
            kinds,
            [None, "user", None, "assistant", "tool_use", None, "tool_result", None],
        )
        self.assertEqual(normalized[1]["role"], "user")
        self.assertEqual(normalized[1]["search_text"], "录音确认超时 req_id")
        self.assertEqual(normalized[1]["timestamp"], "2023-11-14T22:13:22.000Z")
        self.assertEqual(normalized[3]["search_text"], "检查设备状态")
        self.assertEqual(normalized[4]["tool_name"], "run_terminal_command")
        self.assertEqual(
            json.loads(normalized[4]["search_text"]), {"command": "pwsh -NoLogo"}
        )
        self.assertEqual(normalized[6]["tool_name"], "run_terminal_command")
        self.assertEqual(normalized[6]["role"], "tool")
        self.assertEqual(normalized[6]["search_text"], "command finished")

    def test_grok_project_cwd_falls_back_to_url_decoding_and_dot_cwd(self):
        from platforms import grok as grok_platform

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            updates = self.make_session(home)
            self.assertEqual(grok_platform.project_cwd(updates), WORK_DIR)

            no_info = self.make_session(
                home,
                session_id="01a08e33-0000-7000-8000-000000000000",
                summary={"info": {"id": "01a08e33-0000-7000-8000-000000000000"}},
            )
            self.assertEqual(grok_platform.project_cwd(no_info), WORK_DIR)

            slug = home / "sessions" / "some-long-slug-a43fa8-20dca7119e6a70f1"
            session = slug / "01a08e44-0000-7000-8000-000000000000"
            session.mkdir(parents=True)
            (session / "summary.json").write_text("{}", encoding="utf-8")
            (slug / ".cwd").write_text(r"E:\bit\learn\很长的路径", encoding="utf-8")
            slug_updates = session / "updates.jsonl"
            slug_updates.write_text("", encoding="utf-8")
            self.assertEqual(grok_platform.project_cwd(slug_updates), r"E:\bit\learn\很长的路径")

    def test_grok_decode_path_uses_summary_cwd(self):
        from retrace_paths import decode_path, encode_path

        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("GROK_HOME")
            os.environ["GROK_HOME"] = tmp
            try:
                updates = self.make_session(Path(tmp))
                updates.write_text("", encoding="utf-8")
                self.assertEqual(decode_path(encode_path(WORK_DIR), "grok"), WORK_DIR)
            finally:
                if previous is None:
                    os.environ.pop("GROK_HOME", None)
                else:
                    os.environ["GROK_HOME"] = previous

    def test_grok_index_and_search_use_summary_project_and_clean_updates(self):
        retrace_index = load_script("retrace-index")
        retrace_search = load_script("retrace-search")
        from retrace_paths import encode_path, get_platform

        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("GROK_HOME")
            os.environ["GROK_HOME"] = tmp
            try:
                home = Path(tmp)
                updates = self.make_session(home)
                self.write_jsonl(updates, sample_records())

                total = retrace_index.index_all_projects(
                    "grok-project",
                    incremental=False,
                    generate_summaries=False,
                    platform_name="grok",
                )

                project_bucket = encode_path(WORK_DIR)
                self.assertEqual(project_bucket, "X--Work-grok-project")
                db_path = get_platform("grok").projects_dir / project_bucket / "retrace-index.db"
                self.assertTrue(db_path.is_file())
                self.assertEqual(total, 5)

                conn = retrace_index.sqlite3.connect(str(db_path))
                try:
                    rows = conn.execute(
                        "SELECT msg_type, tool_name, search_text, session_id "
                        "FROM messages ORDER BY timestamp, line_no"
                    ).fetchall()
                    self.assertEqual([row[0] for row in rows].count("user"), 1)
                    self.assertEqual([row[0] for row in rows].count("session_meta"), 1)
                    self.assertFalse(any("private reasoning" in row[2] for row in rows))
                    self.assertEqual({row[3] for row in rows}, {SESSION_ID})
                    self.assertIn(
                        ("tool_use", "run_terminal_command"),
                        {(row[0], row[1]) for row in rows},
                    )
                    self.assertIn(
                        ("tool_result", "run_terminal_command"),
                        {(row[0], row[1]) for row in rows},
                    )

                    results = retrace_search.hybrid_search_list(
                        conn, "录音确认超时 req_id", limit=10
                    )
                    self.assertEqual(results[0]["preview"], "录音确认超时 req_id")
                finally:
                    conn.close()

                completed = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPTS / "retrace-search.py"),
                        "command finished",
                        "--platform",
                        "grok",
                        "--project",
                        "grok-project",
                        "--type",
                        "tool_result",
                        "--tool",
                        "run_terminal_command",
                        "--session",
                        SESSION_ID,
                        "--json",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    env=os.environ.copy(),
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                cli_results = json.loads(completed.stdout)
                self.assertEqual(cli_results[0]["type"], "tool_result")
                self.assertEqual(cli_results[0]["tool"], "run_terminal_command")
                self.assertEqual(cli_results[0]["session_id"], SESSION_ID)

                grouped = retrace_index.discover_project_files(get_platform("grok"))
                self.assertEqual(set(grouped), {db_path.parent})
                self.assertEqual(set(grouped[db_path.parent]), {updates})
            finally:
                if previous is None:
                    os.environ.pop("GROK_HOME", None)
                else:
                    os.environ["GROK_HOME"] = previous

    def test_grok_incremental_tool_result_keeps_name_from_earlier_call(self):
        retrace_index = load_script("retrace-index")

        with tempfile.TemporaryDirectory() as tmp:
            updates = self.make_session(Path(tmp))
            self.write_jsonl(updates, sample_records()[:5])
            conn = retrace_index.create_index_db(str(Path(tmp) / "index.db"))
            try:
                retrace_index.index_session_file(
                    conn, str(updates), incremental=True, platform_name="grok"
                )
                with updates.open("a", encoding="utf-8") as stream:
                    for record in sample_records()[5:]:
                        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                retrace_index.index_session_file(
                    conn, str(updates), incremental=True, platform_name="grok"
                )

                tool_name = conn.execute(
                    "SELECT tool_name FROM messages WHERE msg_type = 'tool_result'"
                ).fetchone()[0]
                self.assertEqual(tool_name, "run_terminal_command")
                duplicates = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE msg_type = 'user'"
                ).fetchone()[0]
                self.assertEqual(duplicates, 1)
            finally:
                conn.close()

    def test_grok_locate_and_list_return_session_with_summary_cwd(self):
        retrace_locate = load_script("retrace-locate")
        from retrace_paths import find_session_files

        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("GROK_HOME")
            os.environ["GROK_HOME"] = tmp
            try:
                updates = self.make_session(Path(tmp))
                self.write_jsonl(updates, sample_records())

                matches = find_session_files(SESSION_ID, "grok")
                self.assertEqual(matches, [updates])

                located = retrace_locate.locate_session(session_id=SESSION_ID, platform="grok")
                self.assertEqual(located["session_file"], str(updates))
                self.assertEqual(located["session_files"], [str(updates)])
                self.assertEqual(located["project_path"], WORK_DIR)

                sessions = retrace_locate.list_sessions("grok-project", "grok")
                self.assertEqual(len(sessions), 1)
                self.assertEqual(sessions[0]["session_id"], SESSION_ID)
                self.assertEqual(sessions[0]["files"], [str(updates)])

                projects = retrace_locate.list_projects("grok")
                self.assertEqual(len(projects), 1)
                self.assertEqual(projects[0]["session_count"], 1)
                self.assertEqual(projects[0]["path"], WORK_DIR)
            finally:
                if previous is None:
                    os.environ.pop("GROK_HOME", None)
                else:
                    os.environ["GROK_HOME"] = previous

    def test_grok_chronicle_reads_updates_without_thinking(self):
        retrace_chronicle = load_script("retrace-chronicle")

        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("GROK_HOME")
            os.environ["GROK_HOME"] = tmp
            try:
                updates = self.make_session(Path(tmp))
                self.write_jsonl(updates, sample_records())

                self.assertEqual(
                    retrace_chronicle.find_session_file(SESSION_ID, "grok-project", "grok"),
                    updates,
                )
                messages = retrace_chronicle.read_session_files([updates])

                self.assertEqual(
                    [message["type"] for message in messages],
                    ["user", "assistant", "tool_use", "tool_result"],
                )
                self.assertEqual(messages[2]["tool"], "run_terminal_command")
                self.assertEqual(messages[3]["tool"], "run_terminal_command")
                self.assertFalse(
                    any("private reasoning" in message["content"] for message in messages)
                )
            finally:
                if previous is None:
                    os.environ.pop("GROK_HOME", None)
                else:
                    os.environ["GROK_HOME"] = previous

    def test_platform_clis_offer_grok(self):
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
            self.assertIn("grok", result.stdout.lower(), name)

    def test_grok_documentation_stays_consistent(self):
        docs = [
            ROOT / "AGENTS.md",
            ROOT / "README.md",
            ROOT / "README_CN.md",
            ROOT / "skills" / "retrace" / "SKILL.md",
            ROOT / "skills" / "retrace" / "references" / "architecture.md",
        ]
        for path in docs:
            content = path.read_text(encoding="utf-8")
            self.assertIn("--platform grok", content, path.name)
            self.assertIn("GROK_HOME", content, path.name)
            self.assertIn("updates.jsonl", content, path.name)

        adr = (
            ROOT
            / "skills"
            / "retrace"
            / "references"
            / "adr-002-grok-project-attribution.md"
        ).read_text(encoding="utf-8")
        self.assertIn("summary.json", adr)
        self.assertIn("info.cwd", adr)
        self.assertIn(".cwd", adr)

        validators = [
            SCRIPTS / "validate-skill.py",
            SCRIPTS / "validate-skill.ps1",
        ]
        for path in validators:
            self.assertIn("grok.py", path.read_text(encoding="utf-8"), path.name)


if __name__ == "__main__":
    unittest.main()
