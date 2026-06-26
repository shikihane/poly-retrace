#!/usr/bin/env sh
set -eu

PYTHON_CMD=${PYTHON_CMD:-python3}
RETRACE_SCRIPTS=${RETRACE_SCRIPTS:-"$(CDPATH= cd -- "$(dirname -- "$0")/../scripts" && pwd)"}
PLATFORM=${RETRACE_PLATFORM:-codex}
PROJECT=${RETRACE_PROJECT:-poly-retrace}
SESSION=${RETRACE_SESSION:-<session-uuid>}

echo "=== Example 1: Chronicle by Session ID ==="
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-chronicle.py" \
  --platform "$PLATFORM" \
  --session "$SESSION" \
  --project "$PROJECT" \
  --output ./chronicle.toon

echo "=== Example 2: JSON Output ==="
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-chronicle.py" \
  --platform "$PLATFORM" \
  --session "$SESSION" \
  --project "$PROJECT" \
  --output ./chronicle.json \
  --json

echo "=== Example 3: Direct File Path (replace path) ==="
echo "\"$PYTHON_CMD\" \"$RETRACE_SCRIPTS/retrace-chronicle.py\" --platform $PLATFORM --file <path-to-session.jsonl> --output ./chronicle.toon"

echo "=== Example 4: Filter Code Events ==="
grep ',code,' ./chronicle.toon || true

echo "=== Example 5: Extract Commands ==="
grep ',cmd,' ./chronicle.toon || true
