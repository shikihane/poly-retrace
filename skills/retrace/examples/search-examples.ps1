$ErrorActionPreference = "Stop"
$PYTHON_CMD = "python"
$env:RETRACE_SCRIPTS = Join-Path $PSScriptRoot "..\scripts"
$PLATFORM = if ($env:RETRACE_PLATFORM) { $env:RETRACE_PLATFORM } else { "codex" }
$PROJECT = if ($env:RETRACE_PROJECT) { $env:RETRACE_PROJECT } else { "poly-retrace" }
if ($PLATFORM -eq "pi") {
    $TOOL = "bash"
    $BASIC_QUERY = "worker_done"
    $HYBRID_QUERY = "多 pi 编排 worker_done"
    $TYPE_QUERY = "cat"
    $TOOL_QUERY = "cat"
} elseif ($PLATFORM -eq "claude") {
    $TOOL = "Bash"
    $BASIC_QUERY = "error handling"
    $HYBRID_QUERY = "TypeScript build error"
    $TYPE_QUERY = "config"
    $TOOL_QUERY = "npm"
} else {
    $TOOL = "shell_command"
    $BASIC_QUERY = "error handling"
    $HYBRID_QUERY = "Wi-Fi whd_bus_sdio_init_oob_intr EEXIST host-wake"
    $TYPE_QUERY = "pwsh"
    $TOOL_QUERY = "pwsh"
}

Write-Host "=== Example 1: Ensure Index ($PLATFORM) ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform $PLATFORM --project $PROJECT --no-summary

Write-Host "=== Example 2: List Sessions ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform $PLATFORM --list-sessions --project $PROJECT

Write-Host "=== Example 3: Basic Search ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform $PLATFORM $BASIC_QUERY --project $PROJECT

Write-Host "=== Example 4: Hybrid Search ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform $PLATFORM --hybrid $HYBRID_QUERY --project $PROJECT

Write-Host "=== Example 5: Type Filter ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform $PLATFORM $TYPE_QUERY --type tool_use --project $PROJECT

Write-Host "=== Example 6: Tool Filter ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform $PLATFORM $TOOL_QUERY --tool $TOOL --project $PROJECT

Write-Host "=== Example 7: Statistics ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform $PLATFORM "authentication" --level stats --project $PROJECT

Write-Host "=== Example 8: Date Range ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform $PLATFORM "refactor" --since 2026-01-01 --until 2026-12-31 --project $PROJECT

Write-Host "=== Example 9: JSON Output ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform $PLATFORM "bug" --project $PROJECT --json

Write-Host "=== Example 10: Context / Full (replace <id>) ==="
Write-Host "& `$PYTHON_CMD `"`$env:RETRACE_SCRIPTS\retrace-search.py`" --platform $PLATFORM --project $PROJECT --context <id> --before 3 --after 3"
Write-Host "& `$PYTHON_CMD `"`$env:RETRACE_SCRIPTS\retrace-search.py`" --platform $PLATFORM --project $PROJECT --full <id>"
