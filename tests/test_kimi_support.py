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


class KimiSupportTests(unittest.TestCase):
    @staticmethod
    def write_jsonl(path: Path, records: list[dict]):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
            encoding="utf-8",
        )

    def test_kimi_platform_has_its_own_home_and_finds_every_agent_wire(self):
        from retrace_paths import get_platform

        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("KIMI_CODE_HOME")
            os.environ["KIMI_CODE_HOME"] = tmp
            try:
                home = Path(tmp)
                session = home / "sessions" / "wd_opaque_hash" / "session_session-123"
                main = session / "agents" / "main" / "wire.jsonl"
                subagent = session / "agents" / "agent-0" / "wire.jsonl"
                main.parent.mkdir(parents=True)
                subagent.parent.mkdir(parents=True)
                main.write_text("", encoding="utf-8")
                subagent.write_text("", encoding="utf-8")

                kimi = get_platform("kimi")

                self.assertEqual(kimi.name, "kimi")
                self.assertEqual(kimi.home_dir, home)
                self.assertEqual(kimi.projects_dir, home / "projects")
                self.assertEqual(set(kimi.iter_session_files()), {main, subagent})
                self.assertNotEqual(kimi.home_dir, get_platform("codex").home_dir)
                self.assertNotEqual(kimi.home_dir, get_platform("claude").home_dir)
            finally:
                if previous is None:
                    os.environ.pop("KIMI_CODE_HOME", None)
                else:
                    os.environ["KIMI_CODE_HOME"] = previous

    def test_kimi_wire_events_normalize_messages_and_skip_protocol_noise(self):
        retrace_index = load_script("retrace-index")
        timestamp_ms = 1_700_000_000_000
        user = {
            "type": "context.append_message",
            "message": {
                "role": "user",
                "content": {"type": "text", "text": "录音确认超时 req_id"},
            },
            "time": timestamp_ms,
        }
        assistant = {
            "type": "context.append_loop_event",
            "event": {
                "type": "content.part",
                "uuid": "assistant-1",
                "part": {"type": "text", "text": "check the recorder"},
            },
            "time": timestamp_ms + 1,
        }
        tool_call = {
            "type": "context.append_loop_event",
            "event": {
                "type": "tool.call",
                "uuid": "tool-event-1",
                "toolCallId": "call-1",
                "name": "Bash",
                "args": {"command": "pwsh -NoLogo"},
            },
            "time": timestamp_ms + 2,
        }
        thinking = {
            "type": "context.append_loop_event",
            "event": {
                "type": "content.part",
                "part": {"type": "think", "think": "private reasoning"},
            },
            "time": timestamp_ms + 3,
        }

        normalized_user = retrace_index.normalize_record(user)
        normalized_assistant = retrace_index.normalize_record(assistant)
        normalized_tool = retrace_index.normalize_record(tool_call)

        self.assertEqual(normalized_user["msg_type"], "user")
        self.assertEqual(normalized_user["role"], "user")
        self.assertEqual(normalized_user["search_text"], "录音确认超时 req_id")
        self.assertEqual(normalized_user["timestamp"], "2023-11-14T22:13:20.000Z")
        self.assertEqual(normalized_assistant["msg_type"], "assistant")
        self.assertEqual(normalized_assistant["search_text"], "check the recorder")
        self.assertEqual(normalized_tool["msg_type"], "tool_use")
        self.assertEqual(normalized_tool["tool_name"], "Bash")
        self.assertEqual(json.loads(normalized_tool["search_text"]), {"command": "pwsh -NoLogo"})
        self.assertIsNone(retrace_index.normalize_record(thinking))
        self.assertIsNone(retrace_index.normalize_record({"type": "turn.prompt", "time": timestamp_ms}))
        self.assertIsNone(retrace_index.normalize_record({"type": "usage.record", "time": timestamp_ms}))

    def test_kimi_decode_path_uses_state_work_dir_instead_of_wd_bucket(self):
        from retrace_paths import decode_path, encode_path

        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("KIMI_CODE_HOME")
            os.environ["KIMI_CODE_HOME"] = tmp
            try:
                work_dir = r"X:\Work\voice-project"
                session = Path(tmp) / "sessions" / "wd_ambiguous_hash" / "session_s1"
                wire = session / "agents" / "main" / "wire.jsonl"
                self.write_jsonl(wire, [])
                (session / "state.json").write_text(
                    json.dumps({"workDir": work_dir}), encoding="utf-8"
                )

                self.assertEqual(decode_path(encode_path(work_dir), "kimi"), work_dir)
            finally:
                if previous is None:
                    os.environ.pop("KIMI_CODE_HOME", None)
                else:
                    os.environ["KIMI_CODE_HOME"] = previous

    def test_kimi_index_and_hybrid_search_use_state_project_and_clean_wire_events(self):
        retrace_index = load_script("retrace-index")
        retrace_search = load_script("retrace-search")
        from retrace_paths import encode_path, get_platform

        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("KIMI_CODE_HOME")
            os.environ["KIMI_CODE_HOME"] = tmp
            try:
                home = Path(tmp)
                session = home / "sessions" / "wd_wrong_bucket_hash" / "session_session-123"
                state = {
                    "createdAt": "2026-07-29T01:00:00Z",
                    "title": "Recorder timeout",
                    "workDir": r"X:\Work\voice-project",
                }
                session.mkdir(parents=True)
                (session / "state.json").write_text(
                    json.dumps(state, ensure_ascii=False), encoding="utf-8"
                )
                timestamp_ms = 1_775_000_000_000
                main_records = [
                    {
                        "type": "context.append_message",
                        "message": {
                            "role": "user",
                            "content": {"type": "text", "text": "录音确认超时 req_id"},
                        },
                        "time": timestamp_ms,
                    },
                    {"type": "turn.prompt", "input": "录音确认超时 req_id", "time": timestamp_ms},
                    {
                        "type": "context.append_loop_event",
                        "event": {
                            "type": "content.part",
                            "uuid": "think-1",
                            "part": {"type": "think", "think": "never index private reasoning"},
                        },
                        "time": timestamp_ms + 1,
                    },
                    {
                        "type": "context.append_loop_event",
                        "event": {
                            "type": "content.part",
                            "uuid": "answer-1",
                            "part": {"type": "text", "text": "检查设备状态"},
                        },
                        "time": timestamp_ms + 2,
                    },
                    {
                        "type": "context.append_loop_event",
                        "event": {
                            "type": "tool.call",
                            "uuid": "tool-event-1",
                            "toolCallId": "call-1",
                            "name": "Bash",
                            "args": {"command": "pwsh -NoLogo"},
                        },
                        "time": timestamp_ms + 3,
                    },
                    {
                        "type": "context.append_loop_event",
                        "event": {
                            "type": "tool.result",
                            "parentUuid": "tool-event-1",
                            "toolCallId": "call-1",
                            "result": {"output": "command finished"},
                        },
                        "time": timestamp_ms + 4,
                    },
                    {"type": "usage.record", "usage": {"inputTokens": 10}, "time": timestamp_ms + 5},
                ]
                subagent_records = [
                    {
                        "type": "context.append_loop_event",
                        "event": {
                            "type": "content.part",
                            "uuid": "sub-answer-1",
                            "part": {"type": "text", "text": "subagent diagnosis complete"},
                        },
                        "time": timestamp_ms + 6,
                    }
                ]
                main_wire = session / "agents" / "main" / "wire.jsonl"
                sub_wire = session / "agents" / "agent-0" / "wire.jsonl"
                self.write_jsonl(main_wire, main_records)
                self.write_jsonl(sub_wire, subagent_records)

                orphan = home / "sessions" / "wd_must_not_decode" / "session_orphan"
                self.write_jsonl(orphan / "agents" / "main" / "wire.jsonl", main_records[:1])

                total = retrace_index.index_all_projects(
                    "voice-project",
                    incremental=False,
                    generate_summaries=False,
                    platform_name="kimi",
                )

                project_bucket = encode_path(state["workDir"])
                self.assertEqual(project_bucket, "X--Work-voice-project")
                db_path = get_platform("kimi").projects_dir / project_bucket / "retrace-index.db"
                self.assertTrue(db_path.is_file())
                self.assertEqual(total, 6)

                conn = retrace_index.sqlite3.connect(str(db_path))
                try:
                    rows = conn.execute(
                        "SELECT msg_type, tool_name, search_text, session_id, agent_id "
                        "FROM messages ORDER BY timestamp, line_no"
                    ).fetchall()
                    self.assertEqual([row[0] for row in rows].count("user"), 1)
                    self.assertFalse(any("private reasoning" in row[2] for row in rows))
                    self.assertEqual({row[3] for row in rows}, {"session-123"})
                    self.assertIn(("tool_use", "Bash"), {(row[0], row[1]) for row in rows})
                    self.assertIn(("tool_result", "Bash"), {(row[0], row[1]) for row in rows})
                    self.assertIn("agent-0", {row[4] for row in rows})
                    canonical = conn.execute(
                        "SELECT session_file FROM sessions WHERE session_id = ?",
                        ("session-123",),
                    ).fetchone()[0]
                    self.assertEqual(canonical, str(main_wire))

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
                        "kimi",
                        "--hybrid",
                        "--project",
                        "voice-project",
                        "--type",
                        "tool_result",
                        "--tool",
                        "Bash",
                        "--session",
                        "session-123",
                        "--since",
                        "2020-01-01",
                        "--until",
                        "2030-01-01",
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
                self.assertEqual(cli_results[0]["tool"], "Bash")
                self.assertEqual(cli_results[0]["session_id"], "session-123")

                grouped = retrace_index.discover_project_files(get_platform("kimi"))
                self.assertEqual(set(grouped), {db_path.parent})
                self.assertEqual(set(grouped[db_path.parent]), {main_wire, sub_wire})
            finally:
                if previous is None:
                    os.environ.pop("KIMI_CODE_HOME", None)
                else:
                    os.environ["KIMI_CODE_HOME"] = previous

    def test_kimi_incremental_tool_result_keeps_name_from_earlier_call(self):
        retrace_index = load_script("retrace-index")

        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "sessions" / "wd_x" / "session_s1"
            session.mkdir(parents=True)
            (session / "state.json").write_text(
                json.dumps({"workDir": r"X:\Work\voice-project"}), encoding="utf-8"
            )
            wire = session / "agents" / "main" / "wire.jsonl"
            self.write_jsonl(
                wire,
                [
                    {"type": "metadata", "protocol_version": "1.4"},
                    {
                        "type": "context.append_loop_event",
                        "event": {
                            "type": "tool.call",
                            "toolCallId": "call-1",
                            "name": "Bash",
                            "args": {"command": "pwsh"},
                        },
                        "time": 1_700_000_000_000,
                    },
                ],
            )
            conn = retrace_index.create_index_db(str(Path(tmp) / "index.db"))
            try:
                retrace_index.index_session_file(
                    conn, str(wire), incremental=True, platform_name="kimi"
                )
                with wire.open("a", encoding="utf-8") as stream:
                    stream.write(
                        json.dumps(
                            {
                                "type": "context.append_loop_event",
                                "event": {
                                    "type": "tool.result",
                                    "toolCallId": "call-1",
                                    "result": {"output": "done"},
                                },
                                "time": 1_700_000_000_001,
                            }
                        )
                        + "\n"
                    )
                retrace_index.index_session_file(
                    conn, str(wire), incremental=True, platform_name="kimi"
                )

                tool_name = conn.execute(
                    "SELECT tool_name FROM messages WHERE msg_type = 'tool_result'"
                ).fetchone()[0]
                self.assertEqual(tool_name, "Bash")
            finally:
                conn.close()

    def test_kimi_full_content_is_not_limited_to_the_list_preview(self):
        retrace_index = load_script("retrace-index")
        retrace_search = load_script("retrace-search")

        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "sessions" / "wd_x" / "session_s1"
            session.mkdir(parents=True)
            (session / "state.json").write_text(
                json.dumps({"workDir": r"X:\Work\voice-project"}), encoding="utf-8"
            )
            wire = session / "agents" / "main" / "wire.jsonl"
            full_text = "message:" + ("x" * 400) + ":tail"
            self.write_jsonl(
                wire,
                [
                    {
                        "type": "context.append_message",
                        "message": {
                            "role": "user",
                            "content": {"type": "text", "text": full_text},
                        },
                        "time": 1_700_000_000_000,
                    }
                ],
            )
            conn = retrace_index.create_index_db(str(Path(tmp) / "index.db"))
            try:
                retrace_index.index_session_file(
                    conn, str(wire), incremental=False, platform_name="kimi"
                )
                message_id = conn.execute(
                    "SELECT id FROM messages WHERE msg_type = 'user'"
                ).fetchone()[0]

                result = retrace_search.get_full_content(conn, message_id)

                self.assertEqual(result["content"]["text"], full_text)
                self.assertEqual(result["raw"]["type"], "context.append_message")
            finally:
                conn.close()

    def test_kimi_locate_and_list_return_one_session_with_main_wire_first(self):
        retrace_locate = load_script("retrace-locate")
        from retrace_paths import find_session_files

        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("KIMI_CODE_HOME")
            os.environ["KIMI_CODE_HOME"] = tmp
            try:
                home = Path(tmp)
                session = home / "sessions" / "wd_opaque_hash" / "session_session-123"
                work_dir = r"X:\Work\voice-project"
                session.mkdir(parents=True)
                (session / "state.json").write_text(
                    json.dumps({"workDir": work_dir}), encoding="utf-8"
                )
                main = session / "agents" / "main" / "wire.jsonl"
                subagent = session / "agents" / "agent-0" / "wire.jsonl"
                self.write_jsonl(main, [{"type": "metadata", "time": 1_700_000_000_000}])
                self.write_jsonl(subagent, [{"type": "metadata", "time": 1_700_000_000_001}])

                matches = find_session_files("session-123", "kimi")
                self.assertEqual(matches, [main, subagent])

                located = retrace_locate.locate_session(
                    session_id="session-123", platform="kimi"
                )
                self.assertEqual(located["session_file"], str(main))
                self.assertEqual(located["session_files"], [str(main), str(subagent)])
                self.assertEqual(located["project_path"], work_dir)

                sessions = retrace_locate.list_sessions("voice-project", "kimi")
                self.assertEqual(len(sessions), 1)
                self.assertEqual(sessions[0]["session_id"], "session-123")
                self.assertEqual(sessions[0]["files"], [str(main), str(subagent)])

                projects = retrace_locate.list_projects("kimi")
                self.assertEqual(len(projects), 1)
                self.assertEqual(projects[0]["session_count"], 1)
                self.assertEqual(projects[0]["path"], work_dir)
            finally:
                if previous is None:
                    os.environ.pop("KIMI_CODE_HOME", None)
                else:
                    os.environ["KIMI_CODE_HOME"] = previous

    def test_kimi_locate_finds_wire_when_state_has_no_project_attribution(self):
        retrace_locate = load_script("retrace-locate")

        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("KIMI_CODE_HOME")
            os.environ["KIMI_CODE_HOME"] = tmp
            try:
                wire = (
                    Path(tmp)
                    / "sessions"
                    / "wd_do_not_decode"
                    / "session_session-123"
                    / "agents"
                    / "main"
                    / "wire.jsonl"
                )
                self.write_jsonl(wire, [{"type": "metadata"}])

                located = retrace_locate.locate_session(
                    session_id="session-123", platform="kimi"
                )

                self.assertEqual(located["session_file"], str(wire))
                self.assertEqual(located["session_files"], [str(wire)])
                self.assertIsNone(located["project_dir"])
                self.assertEqual(located["project_path"], "")
            finally:
                if previous is None:
                    os.environ.pop("KIMI_CODE_HOME", None)
                else:
                    os.environ["KIMI_CODE_HOME"] = previous

    def test_kimi_chronicle_merges_agents_in_time_order_without_thinking(self):
        retrace_chronicle = load_script("retrace-chronicle")

        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("KIMI_CODE_HOME")
            os.environ["KIMI_CODE_HOME"] = tmp
            try:
                session = (
                    Path(tmp)
                    / "sessions"
                    / "wd_opaque_hash"
                    / "session_session-123"
                )
                session.mkdir(parents=True)
                (session / "state.json").write_text(
                    json.dumps({"workDir": r"X:\Work\voice-project"}), encoding="utf-8"
                )
                timestamp_ms = 1_700_000_000_000
                main = session / "agents" / "main" / "wire.jsonl"
                subagent = session / "agents" / "agent-0" / "wire.jsonl"
                self.write_jsonl(
                    main,
                    [
                        {
                            "type": "context.append_message",
                            "message": {
                                "role": "user",
                                "content": {"type": "text", "text": "run it"},
                            },
                            "time": timestamp_ms,
                        },
                        {
                            "type": "context.append_loop_event",
                            "event": {
                                "type": "content.part",
                                "uuid": "think-1",
                                "part": {"type": "think", "think": "private thought"},
                            },
                            "time": timestamp_ms + 1,
                        },
                        {
                            "type": "context.append_loop_event",
                            "event": {
                                "type": "tool.call",
                                "uuid": "tool-1",
                                "toolCallId": "call-1",
                                "name": "Bash",
                                "args": {"command": "pwsh -NoLogo"},
                            },
                            "time": timestamp_ms + 3,
                        },
                        {
                            "type": "context.append_loop_event",
                            "event": {
                                "type": "tool.result",
                                "parentUuid": "tool-1",
                                "toolCallId": "call-1",
                                "result": {"output": "done"},
                            },
                            "time": timestamp_ms + 4,
                        },
                    ],
                )
                self.write_jsonl(
                    subagent,
                    [
                        {
                            "type": "context.append_loop_event",
                            "event": {
                                "type": "content.part",
                                "uuid": "sub-answer",
                                "part": {"type": "text", "text": "subagent reply"},
                            },
                            "time": timestamp_ms + 2,
                        }
                    ],
                )

                self.assertEqual(
                    retrace_chronicle.find_session_file(
                        "session-123", "voice-project", "kimi"
                    ),
                    main,
                )
                messages = retrace_chronicle.read_session_files([main, subagent])

                self.assertEqual(
                    [message["type"] for message in messages],
                    ["user", "assistant", "tool_use", "tool_result"],
                )
                self.assertEqual(messages[1]["content"], "subagent reply")
                self.assertEqual(messages[2]["tool"], "Bash")
                self.assertEqual(messages[3]["tool"], "Bash")
                self.assertFalse(any("private thought" in message["content"] for message in messages))
            finally:
                if previous is None:
                    os.environ.pop("KIMI_CODE_HOME", None)
                else:
                    os.environ["KIMI_CODE_HOME"] = previous

    def test_kimi_documentation_and_project_attribution_adr_stay_consistent(self):
        docs = [
            ROOT / "skills" / "retrace" / "SKILL.md",
            ROOT / "AGENTS.md",
            ROOT / "README.md",
            ROOT / "README_CN.md",
        ]
        for path in docs:
            content = path.read_text(encoding="utf-8")
            self.assertIn("--platform kimi", content, path.name)
            self.assertIn("KIMI_CODE_HOME", content, path.name)
            self.assertIn("state.json", content, path.name)

        adr = (
            ROOT
            / "skills"
            / "retrace"
            / "references"
            / "adr-001-kimi-project-attribution.md"
        ).read_text(encoding="utf-8")
        self.assertIn("state.json", adr)
        self.assertIn("workDir", adr)
        self.assertIn("wd_", adr)
        self.assertIn("must not", adr.lower())


if __name__ == "__main__":
    unittest.main()
