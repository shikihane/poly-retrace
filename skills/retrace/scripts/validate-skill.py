#!/usr/bin/env python3
"""Portable retrace skill validation."""

from pathlib import Path
import sys


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent


def check_file(path: Path, label: str, errors: list[str]) -> None:
    if path.is_file():
        print(f"    [OK] {label}")
    else:
        print(f"    [ERROR] missing {label}")
        errors.append(label)


def main() -> int:
    errors: list[str] = []

    print("=== Retrace Skill Validation ===")

    print("\nChecking SKILL.md...")
    skill_md = SKILL_DIR / "SKILL.md"
    check_file(skill_md, "SKILL.md", errors)
    if skill_md.is_file():
        content = skill_md.read_text(encoding="utf-8")
        for field in ("---", "name:", "description:"):
            if field in content:
                print(f"  [OK] contains {field}")
            else:
                print(f"  [ERROR] missing {field}")
                errors.append(f"SKILL.md:{field}")

    print("\nChecking references...")
    for name in ("architecture.md", "chronicle-format.md", "recover-guide.md"):
        check_file(SKILL_DIR / "references" / name, name, errors)

    print("\nChecking examples...")
    for name in (
        "search-examples.ps1",
        "chronicle-examples.ps1",
        "recover-examples.ps1",
        "search-examples.sh",
        "chronicle-examples.sh",
        "recover-examples.sh",
    ):
        check_file(SKILL_DIR / "examples" / name, name, errors)

    print("\nChecking scripts...")
    for name in (
        "retrace-index.py",
        "retrace-search.py",
        "retrace-analyze.py",
        "retrace-chronicle.py",
        "retrace-locate.py",
        "retrace-recover.py",
        "retrace_paths.py",
        "retrace_common.py",
        "validate-skill.py",
        "validate-skill.ps1",
    ):
        check_file(SCRIPT_DIR / name, name, errors)

    print("\n=== Validation Summary ===")
    if not errors:
        print("All critical checks passed.")
        return 0

    print(f"Found {len(errors)} error(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
