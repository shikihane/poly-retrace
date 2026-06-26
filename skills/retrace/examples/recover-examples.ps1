$ErrorActionPreference = "Stop"
$PYTHON_CMD = "python"
$env:RETRACE_SCRIPTS = Join-Path $PSScriptRoot "..\scripts"
$PLATFORM = if ($env:RETRACE_PLATFORM) { $env:RETRACE_PLATFORM } else { "claude" }
$PROJECT = if ($env:RETRACE_PROJECT) { $env:RETRACE_PROJECT } else { "poly-retrace" }
$SESSION = if ($env:RETRACE_SESSION) { $env:RETRACE_SESSION } else { "<session-uuid>" }

Write-Host "=== Example 1: Basic Recovery ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-recover.py" `
    --platform $PLATFORM `
    --session $SESSION `
    --project $PROJECT `
    --file "src/auth.py" `
    --output .\recovery

Write-Host "=== Example 2: Check Versions ==="
Get-Content .\recovery\versions.txt

Write-Host "=== Example 3: Search Reliable Sources First ==="
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform $PLATFORM "src/auth.py" --project $PROJECT --type tool_use

Write-Host "=== Example 4: Batch Recovery ==="
foreach ($file in @("src/main.py", "src/utils.py", "tests/test_main.py")) {
    $name = Split-Path $file -Leaf
    & $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-recover.py" `
        --platform $PLATFORM `
        --session $SESSION `
        --project $PROJECT `
        --file $file `
        --output ".\batch_recovery\$name"
}

Write-Host "=== Example 5: Compare Versions ==="
Write-Host "Compare-Object (Get-Content .\recovery\auth.py_v001.py) (Get-Content .\recovery\auth.py_v002.py)"
