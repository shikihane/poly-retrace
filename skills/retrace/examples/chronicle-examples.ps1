$ErrorActionPreference = "Stop"
$PYTHON_CMD = "python"
$env:RETRACE_SCRIPTS = Join-Path $PSScriptRoot "..\scripts"

Write-Host "=== Example 1: Basic Chronicle ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" `
    --session 550e8400-e29b-41d4-a716-446655440000 `
    --project polydev

Write-Host "=== Example 2: Chronicle by Direct File Path ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" `
    --file "$HOME\.claude\projects\polydev\550e8400-e29b-41d4-a716-446655440000.jsonl"

Write-Host "=== Example 3: JSON Output ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" `
    --file "$HOME\.claude\projects\polydev\550e8400-e29b-41d4-a716-446655440000.jsonl" `
    --json

Write-Host "=== Example 4: Filter Code Events ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" `
    --session 550e8400-e29b-41d4-a716-446655440000 `
    --project polydev | Select-String ",code,"

Write-Host "=== Example 5: Extract Commands ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" `
    --session 550e8400-e29b-41d4-a716-446655440000 `
    --project polydev | Select-String ",cmd,"

Write-Host "=== Example 6: Errors and Fixes ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" `
    --session 550e8400-e29b-41d4-a716-446655440000 `
    --project polydev | Select-String ",(error|fix|mistake),"

Write-Host "=== Example 7: Project Chronicle ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --project polydev

Write-Host "=== Example 8: Save to File ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" `
    --session 550e8400-e29b-41d4-a716-446655440000 `
    --project polydev | Set-Content .\session_chronicle.txt
