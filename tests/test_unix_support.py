import importlib.util
import sys
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


class UnixSupportTests(unittest.TestCase):
    def test_unix_path_encoding_round_trips_best_effort(self):
        import retrace_paths

        with mock.patch.object(retrace_paths.sys, "platform", "linux"):
            encoded = retrace_paths.encode_path("/home/shiyu/work/poly-retrace")

        self.assertEqual(encoded, "home-shiyu-work-poly-retrace")
        self.assertEqual(
            retrace_paths.decode_path(encoded, "codex"),
            "/home/shiyu/work/poly/retrace",
        )

    def test_shell_examples_include_unix_and_windows_variants(self):
        examples = ROOT / "skills" / "retrace" / "examples"

        self.assertTrue((examples / "search-examples.ps1").is_file())
        self.assertTrue((examples / "search-examples.sh").is_file())
        self.assertTrue((examples / "chronicle-examples.sh").is_file())
        self.assertTrue((examples / "recover-examples.sh").is_file())

    def test_validation_script_is_available_without_powershell(self):
        self.assertTrue((SCRIPTS / "validate-skill.py").is_file())

    def test_common_search_passes_platform_to_search_cli(self):
        retrace_common = load_script("retrace_common")

        with mock.patch.object(retrace_common.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "[]"

            retrace_common.search("query", project="poly-retrace", platform="claude")

        cmd = run.call_args.args[0]
        self.assertIn("--platform", cmd)
        self.assertEqual(cmd[cmd.index("--platform") + 1], "claude")


if __name__ == "__main__":
    unittest.main()
