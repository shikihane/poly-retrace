#!/usr/bin/env sh
set -eu

RETRACE_SCRIPTS="$(CDPATH= cd -- "$(dirname -- "$0")/../scripts" && pwd)"
PYTHON_CMD="python3"

echo "=== Example 1: List Codex Sessions ==="
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-search.py" --platform codex --list-sessions --project poly-retrace

echo "=== Example 2: Basic Claude Query ==="
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-search.py" --platform claude "query" --project poly-retrace

echo "=== Example 3: Hybrid Query ==="
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-search.py" --platform codex --hybrid "Wi-Fi whd_bus_sdio_init_oob_intr EEXIST host-wake" --project poly-retrace

echo "=== Example 4: Filtered Tool Query ==="
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-search.py" --platform codex "shell" --type tool_use --tool shell_command --project poly-retrace
