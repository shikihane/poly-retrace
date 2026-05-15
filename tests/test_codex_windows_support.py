import importlib.util
import json
import os
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


class CodexWindowsSupportTests(unittest.TestCase):
    def test_codex_home_defaults_to_lowercase_codex(self):
        from retrace_paths import get_platform

        with tempfile.TemporaryDirectory() as tmp:
            old_home = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = tmp
            try:
                self.assertEqual(get_platform("codex").home_dir, Path(tmp))
            finally:
                if old_home is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = old_home

    def test_platforms_have_separate_homes_and_projects(self):
        from retrace_paths import get_platform

        codex = get_platform("codex")
        claude = get_platform("claude")

        self.assertEqual(codex.name, "codex")
        self.assertEqual(claude.name, "claude")
        self.assertEqual(codex.home_dir.name.lower(), ".codex")
        self.assertEqual(claude.home_dir.name.lower(), ".claude")
        self.assertNotEqual(codex.projects_dir, claude.projects_dir)

    def test_auto_platform_is_not_supported(self):
        from retrace_paths import get_platforms

        with self.assertRaises(ValueError):
            get_platforms("auto")

    def test_platform_specific_modules_are_physically_split(self):
        import platforms.codex as codex_platform
        import platforms.claude as claude_platform

        self.assertEqual(codex_platform.create_platform().name, "codex")
        self.assertEqual(claude_platform.create_platform().name, "claude")

    def test_platform_iteration_is_owned_by_specific_modules(self):
        import platforms.codex as codex_platform
        import platforms.claude as claude_platform

        self.assertNotEqual(
            codex_platform.CodexPlatform.iter_session_files,
            claude_platform.ClaudePlatform.iter_session_files,
        )

    def test_windows_path_encoding_matches_codex_project_bucket(self):
        from retrace_paths import decode_path, encode_path

        encoded = encode_path(r"X:\Work\exampleproject")
        self.assertEqual(encoded, "X--Work-exampleproject")
        self.assertEqual(decode_path(encoded), r"X:\Work\exampleproject")

        self.assertEqual(encode_path(r"X:\Work\example-project"), "X--Work-example-project")

    def test_codex_session_meta_cwd_selects_project_bucket(self):
        retrace_index = load_script("retrace-index")

        record = {
            "type": "session_meta",
            "payload": {
                "id": "019e0b0a-0483-7e02-ae36-ce22111452f5",
                "cwd": r"X:\Work\example-project",
            },
        }
        project = retrace_index.extract_codex_project_name(record)
        self.assertEqual(project, "X--Work-example-project")

    def test_codex_response_items_are_indexed_with_text_and_tool_names(self):
        retrace_index = load_script("retrace-index")

        message_record = {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "done with pwsh"}],
            },
        }
        tool_record = {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "shell_command",
                "arguments": json.dumps({"command": "pwsh -NoLogo"}),
            },
        }

        message = retrace_index.normalize_record(message_record)
        tool = retrace_index.normalize_record(tool_record)

        self.assertEqual(message["msg_type"], "assistant")
        self.assertEqual(message["role"], "assistant")
        self.assertIn("done with pwsh", message["content_preview"])
        self.assertEqual(tool["msg_type"], "tool_use")
        self.assertEqual(tool["tool_name"], "shell_command")
        self.assertIn("pwsh", tool["content_preview"])

    def test_windows_examples_include_pwsh7_variants(self):
        skill = (ROOT / "skills" / "retrace" / "SKILL.md").read_text(encoding="utf-8")
        examples = ROOT / "skills" / "retrace" / "examples"

        self.assertIn("pwsh", skill.lower())
        self.assertTrue(list(examples.glob("*.ps1")))

    def test_retrace_runtime_scripts_are_packaged_inside_skill(self):
        expected_scripts = [
            "retrace-index.py",
            "retrace-search.py",
            "retrace-analyze.py",
            "retrace-chronicle.py",
            "retrace-locate.py",
            "retrace-recover.py",
            "retrace_paths.py",
            "retrace_common.py",
        ]

        for script_name in expected_scripts:
            self.assertTrue((SCRIPTS / script_name).is_file(), script_name)

    def test_skill_docs_do_not_reference_personal_or_repo_absolute_script_paths(self):
        skill = (ROOT / "skills" / "retrace" / "SKILL.md").read_text(encoding="utf-8")

        self.assertNotIn(r"E:\Heyang3", skill)
        self.assertNotIn(r"D:\Projects", skill)
        self.assertNotIn(r"C:\Users", skill)
        self.assertNotIn(r"\poly-retrace\scripts", skill)
        self.assertIn("Set-Location <loaded-retrace-skill-directory>", skill)
        self.assertIn('Join-Path (Get-Location) "scripts"', skill)

    def test_search_escapes_hyphenated_plain_text_for_fts(self):
        retrace_search = load_script("retrace-search")

        self.assertEqual(retrace_search.prepare_fts_query("poly-retrace"), '"poly-retrace"')
        self.assertEqual(retrace_search.prepare_fts_query("plain query"), "plain query")

    def test_no_incremental_rebuild_removes_existing_index_files(self):
        retrace_index = load_script("retrace-index")

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            for name in ("retrace-index.db", "retrace-index.db-wal", "retrace-index.db-shm"):
                (project_dir / name).write_text("old", encoding="utf-8")

            retrace_index.reset_index_db(project_dir)

            self.assertFalse((project_dir / "retrace-index.db").exists())
            self.assertFalse((project_dir / "retrace-index.db-wal").exists())
            self.assertFalse((project_dir / "retrace-index.db-shm").exists())

    def test_index_stores_long_search_text_separately_from_preview(self):
        retrace_index = load_script("retrace-index")

        prefix = "x" * 400
        content = prefix + " whd_bus_sdio_init_oob_intr EEXIST host-wake"
        record = {
            "type": "response_item",
            "timestamp": "2026-05-09T00:00:00Z",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": content}],
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            session_file = Path(tmp) / "session.jsonl"
            session_file.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
            conn = retrace_index.create_index_db(str(Path(tmp) / "index.db"))
            try:
                retrace_index.index_session_file(conn, str(session_file), incremental=False)

                preview, search_text = conn.execute(
                    "SELECT content_preview, search_text FROM messages"
                ).fetchone()
                self.assertNotIn("whd_bus_sdio_init_oob_intr", preview)
                self.assertIn("whd_bus_sdio_init_oob_intr", search_text)
            finally:
                conn.close()

    def test_hybrid_search_uses_selective_trigram_for_complex_queries(self):
        retrace_index = load_script("retrace-index")
        retrace_search = load_script("retrace-search")

        rows = [
            ("2026-05-09T00:00:00Z", "assistant", "记录：录音确认超时 req_id 需要读协议文档"),
            ("2026-05-09T00:01:00Z", "tool_result", "Wi-Fi host-wake failed with EEXIST after OOB init"),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            conn = retrace_index.create_index_db(str(Path(tmp) / "index.db"))
            try:
                for offset, (timestamp, msg_type, text) in enumerate(rows):
                    conn.execute(
                        """
                        INSERT INTO messages
                        (session_file, line_no, byte_offset, byte_length, timestamp,
                         msg_type, role, tool_name, content_preview, search_text, content_hash)
                        VALUES (?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?)
                        """,
                        (
                            str(Path(tmp) / "session.jsonl"),
                            offset + 1,
                            offset,
                            len(text.encode("utf-8")),
                            timestamp,
                            msg_type,
                            "assistant" if msg_type == "assistant" else "tool",
                            text[:300],
                            text,
                            str(abs(hash(text))),
                        ),
                    )
                    rowid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    conn.execute(
                        "INSERT INTO messages_fts (rowid, search_text, msg_type, role, tool_name) VALUES (?, ?, ?, ?, '')",
                        (rowid, text, msg_type, "assistant" if msg_type == "assistant" else "tool"),
                    )
                    retrace_index.insert_trigram_if_selective(
                        conn, rowid, text, msg_type, "assistant" if msg_type == "assistant" else "tool", ""
                    )
                conn.commit()

                chinese_results = retrace_search.hybrid_search_list(conn, "录音确认超时 req_id", limit=10)
                wifi_results = retrace_search.hybrid_search_list(conn, "Wi-Fi EEXIST host-wake", limit=10)

                self.assertEqual(chinese_results[0]["preview"], "记录：录音确认超时 req_id 需要读协议文档")
                self.assertIn("trigram", chinese_results[0]["match_sources"])
                self.assertEqual(wifi_results[0]["preview"], "Wi-Fi host-wake failed with EEXIST after OOB init")
                self.assertIn("trigram", wifi_results[0]["match_sources"])
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
