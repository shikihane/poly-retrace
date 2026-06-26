#!/usr/bin/env sh
set -eu

PYTHON_CMD=${PYTHON_CMD:-python3}
RETRACE_SCRIPTS=${RETRACE_SCRIPTS:-"$(CDPATH= cd -- "$(dirname -- "$0")/../scripts" && pwd)"}
PLATFORM=${RETRACE_PLATFORM:-claude}
PROJECT=${RETRACE_PROJECT:-poly-retrace}
SESSION=${RETRACE_SESSION:-<session-uuid>}

echo "=== Example 1: Basic Recovery ==="
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-recover.py" \
  --platform "$PLATFORM" \
  --session "$SESSION" \
  --project "$PROJECT" \
  --file "src/auth.py" \
  --output ./recovery

echo "=== Example 2: Check Versions ==="
cat ./recovery/versions.txt

echo "=== Example 3: Search Reliable Sources First ==="
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-search.py" \
  --platform "$PLATFORM" \
  "src/auth.py" \
  --project "$PROJECT" \
  --type tool_use

echo "=== Example 4: Compare Versions (if two exist) ==="
echo "diff -u ./recovery/auth.py_v001.py ./recovery/auth.py_v002.py"
