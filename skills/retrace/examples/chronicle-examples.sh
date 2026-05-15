#!/usr/bin/env sh
set -eu

RETRACE_SCRIPTS="$(CDPATH= cd -- "$(dirname -- "$0")/../scripts" && pwd)"
PYTHON_CMD="python3"

echo "=== Example 1: Chronicle by Codex Session ID ==="
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-chronicle.py" \
  --platform codex \
  --session "550e8400-e29b-41d4-a716-446655440000" \
  --project poly-retrace \
  --output ./chronicle.toon

echo "=== Example 2: Chronicle by Direct File Path ==="
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-chronicle.py" \
  --platform claude \
  --file "$HOME/.claude/projects/polydev/550e8400-e29b-41d4-a716-446655440000.jsonl" \
  --output ./chronicle.json \
  --json
