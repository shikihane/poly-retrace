#!/usr/bin/env sh
set -eu

PYTHON_CMD=${PYTHON_CMD:-python3}
RETRACE_SCRIPTS=${RETRACE_SCRIPTS:-"$(CDPATH= cd -- "$(dirname -- "$0")/../scripts" && pwd)"}
PLATFORM=${RETRACE_PLATFORM:-codex}
PROJECT=${RETRACE_PROJECT:-poly-retrace}
case "$PLATFORM" in
  pi)
    TOOL=bash
    BASIC_QUERY="worker_done"
    HYBRID_QUERY="多 pi 编排 worker_done"
    TYPE_QUERY="cat"
    TOOL_QUERY="cat"
    ;;
  claude)
    TOOL=Bash
    BASIC_QUERY="error handling"
    HYBRID_QUERY="TypeScript build error"
    TYPE_QUERY="config"
    TOOL_QUERY="npm"
    ;;
  *)
    TOOL=shell_command
    BASIC_QUERY="error handling"
    HYBRID_QUERY="Wi-Fi whd_bus_sdio_init_oob_intr EEXIST host-wake"
    TYPE_QUERY="pwsh"
    TOOL_QUERY="pwsh"
    ;;
esac

echo "=== Example 1: Ensure Index ($PLATFORM) ==="
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --auto --platform "$PLATFORM" --project "$PROJECT" --no-summary

echo "=== Example 2: List Sessions ==="
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-search.py" --platform "$PLATFORM" --list-sessions --project "$PROJECT"

echo "=== Example 3: Basic Search ==="
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-search.py" --platform "$PLATFORM" "$BASIC_QUERY" --project "$PROJECT"

echo "=== Example 4: Hybrid Search ==="
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-search.py" --platform "$PLATFORM" --hybrid "$HYBRID_QUERY" --project "$PROJECT"

echo "=== Example 5: Type Filter ==="
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-search.py" --platform "$PLATFORM" "$TYPE_QUERY" --type tool_use --project "$PROJECT"

echo "=== Example 6: Tool Filter ==="
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-search.py" --platform "$PLATFORM" "$TOOL_QUERY" --tool "$TOOL" --project "$PROJECT"

echo "=== Example 7: JSON Output ==="
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-search.py" --platform "$PLATFORM" "bug" --project "$PROJECT" --json

echo "=== Example 8: Context / Full (replace <id>) ==="
echo "\"$PYTHON_CMD\" \"$RETRACE_SCRIPTS/retrace-search.py\" --platform $PLATFORM --project $PROJECT --context <id> --before 3 --after 3"
echo "\"$PYTHON_CMD\" \"$RETRACE_SCRIPTS/retrace-search.py\" --platform $PLATFORM --project $PROJECT --full <id>"
