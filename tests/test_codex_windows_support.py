import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
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

        encoded = encode_path(r"D:\Projects\poly-retrace")
        self.assertEqual(encoded, "D--Projects-poly-retrace")
        self.assertEqual(decode_path(encoded), r"D:\Projects\poly-retrace")

    def test_codex_session_meta_cwd_selects_project_bucket(self):
        retrace_index = load_script("retrace-index")

        record = {
            "type": "session_meta",
            "payload": {
                "id": "019e0b0a-0483-7e02-ae36-ce22111452f5",
                "cwd": r"D:\Projects\poly-retrace",
            },
        }
        project = retrace_index.extract_codex_project_name(record)
        self.assertEqual(project, "D--Projects-poly-retrace")

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

    def test_windows_examples_prefer_pwsh7_not_bash(self):
        skill = (ROOT / "skills" / "retrace" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("pwsh", skill.lower())
        self.assertNotIn("```bash", skill)

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


if __name__ == "__main__":
    unittest.main()
