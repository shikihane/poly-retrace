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


class PiSupportTests(unittest.TestCase):
    def run_script(self, env, *args):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / args[0]), *args[1:]],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            self.fail(
                f"command failed: {' '.join(args)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )
        return result

    def make_env(self, pi_home: Path):
        env = os.environ.copy()
        env["PI_AGENT_HOME"] = str(pi_home)
        env.pop("CODEX_HOME", None)
        env.pop("CLAUDE_HOME", None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env

    def load_script_module(self, name: str, filename: str):
        module_path = SCRIPTS / filename
        old_path = list(sys.path)
        sys.path.insert(0, str(SCRIPTS))
        try:
            spec = importlib.util.spec_from_file_location(name, module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            sys.path = old_path

    def write_pi_session(self, pi_home: Path, cwd: Path):
        session_id = "019effd6-8914-7460-a62c-d3537f91cae5"
        session_dir = pi_home / "sessions" / "--tmp-work-poly-retrace--"
        session_dir.mkdir(parents=True)
        session_file = session_dir / f"2026-06-25T17-31-50-420Z_{session_id}.jsonl"
        rows = [
            {
                "type": "session",
                "version": 3,
                "id": session_id,
                "timestamp": "2026-06-25T17:31:50.420Z",
                "cwd": str(cwd),
            },
            {
                "type": "message",
                "id": "u0000001",
                "parentId": None,
                "timestamp": "2026-06-25T17:32:00.000Z",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "使用多pi 编排分析 poly-retrace"}],
                },
            },
            {
                "type": "message",
                "id": "a0000001",
                "parentId": "u0000001",
                "timestamp": "2026-06-25T17:32:01.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "I will inspect the file."},
                        {
                            "type": "toolCall",
                            "id": "call_read_readme",
                            "name": "read",
                            "arguments": {"path": "README.md"},
                        },
                        {
                            "type": "toolCall",
                            "id": "call_read_auth",
                            "name": "bash",
                            "arguments": {"command": "cat src/auth.py"},
                        },
                    ],
                },
            },
            {
                "type": "message",
                "id": "t0000000",
                "parentId": "a0000001",
                "timestamp": "2026-06-25T17:32:01.500Z",
                "message": {
                    "role": "toolResult",
                    "toolCallId": "call_read_readme",
                    "toolName": "read",
                    "content": [{"type": "text", "text": "# fixture\n"}],
                    "isError": False,
                },
            },
            {
                "type": "message",
                "id": "t0000001",
                "parentId": "t0000000",
                "timestamp": "2026-06-25T17:32:02.000Z",
                "message": {
                    "role": "toolResult",
                    "toolCallId": "call_read_auth",
                    "toolName": "bash",
                    "content": [{"type": "text", "text": "print('v1')\n"}],
                    "isError": False,
                },
            },
            {
                "type": "message",
                "id": "a0000002",
                "parentId": "t0000001",
                "timestamp": "2026-06-25T17:32:03.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "toolCall",
                            "id": "call_write_auth",
                            "name": "write",
                            "arguments": {"path": "src/auth.py", "content": "print('v2')\n"},
                        }
                    ],
                },
            },
            {
                "type": "message",
                "id": "t0000002",
                "parentId": "a0000002",
                "timestamp": "2026-06-25T17:32:04.000Z",
                "message": {
                    "role": "toolResult",
                    "toolCallId": "call_write_auth",
                    "toolName": "write",
                    "content": [{"type": "text", "text": "ok"}],
                    "isError": False,
                },
            },
            {
                "type": "message",
                "id": "a0000003",
                "parentId": "t0000002",
                "timestamp": "2026-06-25T17:32:05.000Z",
                "message": {
                    "role": "assistant",
                    "content": [],
                    "api": "openai-responses",
                    "provider": "openai",
                    "model": "gpt-5.5",
                    "usage": {"input": 0, "output": 0},
                    "stopReason": "error",
                    "errorMessage": "Connection error.",
                },
            },
            {
                "type": "compaction",
                "id": "c0000001",
                "parentId": "a0000003",
                "timestamp": "2026-06-25T17:33:00.000Z",
                "summary": "Recovered auth file versions",
                "firstKeptEntryId": "u0000001",
                "tokensBefore": 1234,
            },
        ]
        session_file.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )
        return session_id, session_file

    def test_pi_index_search_locate_and_recover(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pi_home = tmp_path / "pi-home"
            cwd = tmp_path / "work" / "poly-retrace"
            cwd.mkdir(parents=True)
            session_id, _session_file = self.write_pi_session(pi_home, cwd)
            env = self.make_env(pi_home)

            self.run_script(
                env,
                "retrace-index.py",
                "--auto",
                "--platform",
                "pi",
                "--project",
                "poly-retrace",
                "--no-summary",
            )

            search = self.run_script(
                env,
                "retrace-search.py",
                "--platform",
                "pi",
                "--project",
                "poly-retrace",
                "--hybrid",
                "多pi 编排",
                "--json",
            )
            search_rows = json.loads(search.stdout)
            self.assertTrue(search_rows)
            self.assertEqual(search_rows[0]["platform"], "pi")

            tool_search = self.run_script(
                env,
                "retrace-search.py",
                "--platform",
                "pi",
                "--project",
                "poly-retrace",
                "cat",
                "--type",
                "tool_use",
                "--tool",
                "bash",
                "--json",
            )
            tool_rows = json.loads(tool_search.stdout)
            self.assertTrue(tool_rows)
            self.assertEqual(tool_rows[0]["tool"], "bash")

            read_tool_search = self.run_script(
                env,
                "retrace-search.py",
                "--platform",
                "pi",
                "--project",
                "poly-retrace",
                "README.md",
                "--type",
                "tool_use",
                "--tool",
                "read",
                "--json",
            )
            read_tool_rows = json.loads(read_tool_search.stdout)
            self.assertTrue(read_tool_rows)
            self.assertEqual(read_tool_rows[0]["tool"], "read")

            context = self.run_script(
                env,
                "retrace-search.py",
                "--platform",
                "pi",
                "--project",
                "poly-retrace",
                "--context",
                str(tool_rows[0]["id"]),
                "--before",
                "2",
                "--after",
                "2",
                "--json",
            )
            context_rows = json.loads(context.stdout)
            self.assertTrue(any(row["is_target"] for row in context_rows))
            self.assertTrue(any(row["tool"] == "read" for row in context_rows))
            self.assertTrue(any(row["tool"] == "bash" for row in context_rows))

            error_search = self.run_script(
                env,
                "retrace-search.py",
                "--platform",
                "pi",
                "--project",
                "poly-retrace",
                "Connection error",
                "--json",
            )
            error_rows = json.loads(error_search.stdout)
            self.assertTrue(error_rows)
            self.assertIn("stopReason=error", error_rows[0]["preview"])

            chronicle_module = self.load_script_module("retrace_chronicle", "retrace-chronicle.py")
            raw_messages = chronicle_module.read_session_file(_session_file)
            self.assertTrue(
                any("Connection error." in message.get("content", "") for message in raw_messages)
            )

            located = self.run_script(
                env,
                "retrace-locate.py",
                "--platform",
                "pi",
                "--session-id",
                session_id,
                "--json",
            )
            locate_result = json.loads(located.stdout)
            self.assertEqual(locate_result["platform"], "pi")
            self.assertEqual(locate_result["session_id"], session_id)

            recovery_dir = tmp_path / "recovery"
            self.run_script(
                env,
                "retrace-recover.py",
                "--platform",
                "pi",
                "--session",
                session_id,
                "--project",
                "poly-retrace",
                "--file",
                "src/auth.py",
                "--output",
                str(recovery_dir),
            )
            self.assertTrue((recovery_dir / "versions.txt").is_file())
            recovered = sorted(recovery_dir.glob("auth.py_v*.py"))
            self.assertEqual(len(recovered), 2)
            self.assertEqual(recovered[0].read_text(encoding="utf-8"), "print('v1')\n")
            self.assertEqual(recovered[1].read_text(encoding="utf-8"), "print('v2')\n")


if __name__ == "__main__":
    unittest.main()
