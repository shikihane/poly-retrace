$ErrorActionPreference = "Stop"
$PYTHON_CMD = "python"
$env:RETRACE_SCRIPTS = Join-Path $PSScriptRoot "..\scripts"

Write-Host "=== Example 1: Basic Recovery ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-recover.py" `
    --session 550e8400-e29b-41d4-a716-446655440000 `
    --project polydev `
    --file "src/auth.py" `
    --output .\recovery

Write-Host "=== Example 2: Recover Config ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-recover.py" `
    --session 550e8400-e29b-41d4-a716-446655440000 `
    --project polydev `
    --file "config/settings.json" `
    --output .\config_recovery

Write-Host "=== Example 3: Check Versions ==="
Get-Content .\recovery\versions.txt

Write-Host "=== Example 4: Batch Recovery ==="
foreach ($file in @("src/main.py", "src/utils.py", "tests/test_main.py")) {
    $name = Split-Path $file -Leaf
    & $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-recover.py" `
        --session 550e8400-e29b-41d4-a716-446655440000 `
        --project polydev `
        --file $file `
        --output ".\batch_recovery\$name"
}

Write-Host "=== Example 5: Find Session ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --list-sessions --project polydev

Write-Host "=== Example 6: Search File History ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" "src/auth.py" --tool Write --project polydev

Write-Host "=== Example 7: Compare Versions ==="
Compare-Object (Get-Content .\recovery\src_auth_v001.py) (Get-Content .\recovery\src_auth_v002.py)

Write-Host "=== Example 8: Review First ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-recover.py" `
    --session 550e8400-e29b-41d4-a716-446655440000 `
    --project polydev `
    --file "src/auth.py" `
    --output .\review_recovery
