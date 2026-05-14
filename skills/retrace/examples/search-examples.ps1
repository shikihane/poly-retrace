$ErrorActionPreference = "Stop"
$PYTHON_CMD = "python"
$env:RETRACE_SCRIPTS = Join-Path $PSScriptRoot "..\scripts"

Write-Host "=== Example 1: Basic Search ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" "error handling" --project polydev

Write-Host "=== Example 2: Type Filter ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" "database" --type tool_result --project polydev

Write-Host "=== Example 3: Tool Filter ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" "config" --tool shell_command --project polydev

Write-Host "=== Example 4: Session Filter ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" "API" --session 550e8400-e29b-41d4-a716-446655440000 --level detail

Write-Host "=== Example 5: Statistics ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" "authentication" --level stats --project polydev

Write-Host "=== Example 6: Context ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --context abc123 --before 3 --after 3

Write-Host "=== Example 7: Date Range ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" "refactor" --since 2025-01-01 --until 2025-01-31 --project polydev

Write-Host "=== Example 8: JSON Output ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" "bug" --project polydev --json

Write-Host "=== Example 9: List Sessions ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --list-sessions --project polydev

Write-Host "=== Example 10: Combined Filters ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" "migration" `
    --type tool_result `
    --tool shell_command `
    --project polydev `
    --since 2025-01-01 `
    --limit 20
