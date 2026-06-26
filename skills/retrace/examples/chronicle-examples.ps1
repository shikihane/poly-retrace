$ErrorActionPreference = "Stop"
$PYTHON_CMD = "python"
$env:RETRACE_SCRIPTS = Join-Path $PSScriptRoot "..\scripts"
$PLATFORM = if ($env:RETRACE_PLATFORM) { $env:RETRACE_PLATFORM } else { "codex" }
$PROJECT = if ($env:RETRACE_PROJECT) { $env:RETRACE_PROJECT } else { "poly-retrace" }
$SESSION = if ($env:RETRACE_SESSION) { $env:RETRACE_SESSION } else { "<session-uuid>" }

Write-Host "=== Example 1: Chronicle by Session ID ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" `
    --platform $PLATFORM `
    --session $SESSION `
    --project $PROJECT `
    --output .\chronicle.toon

Write-Host "=== Example 2: JSON Output ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" `
    --platform $PLATFORM `
    --session $SESSION `
    --project $PROJECT `
    --output .\chronicle.json `
    --json

Write-Host "=== Example 3: Direct File Path (replace path) ==="
Write-Host "& `$PYTHON_CMD `"`$env:RETRACE_SCRIPTS\retrace-chronicle.py`" --platform $PLATFORM --file `"<path-to-session.jsonl>`" --output .\chronicle.toon"

Write-Host "=== Example 4: Filter Code Events ==="
Get-Content .\chronicle.toon | Select-String ",code,"

Write-Host "=== Example 5: Extract Commands ==="
Get-Content .\chronicle.toon | Select-String ",cmd,"

Write-Host "=== Example 6: Errors and Fixes ==="
Get-Content .\chronicle.toon | Select-String ",(error|fix|mistake),"
