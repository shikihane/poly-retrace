#!/usr/bin/env sh
set -eu

RETRACE_SCRIPTS="$(CDPATH= cd -- "$(dirname -- "$0")/../scripts" && pwd)"
PYTHON_CMD="python3"

echo "=== Example 1: Recover a File from Codex History ==="
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-recover.py" \
  --platform codex \
  --session "550e8400-e29b-41d4-a716-446655440000" \
  --project poly-retrace \
  --file "skills/retrace/scripts/retrace-index.py" \
  --output ./recovery
