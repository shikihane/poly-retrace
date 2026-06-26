$ErrorActionPreference = "Stop"

$skillDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$errors = 0

function Test-RequiredFile {
    param([string] $Path)
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        Write-Host "    [OK] $(Split-Path $Path -Leaf)"
    } else {
        Write-Host "    [ERROR] missing $(Split-Path $Path -Leaf)"
        $script:errors++
    }
}

Write-Host "=== Retrace Skill Validation ==="

Write-Host ""
Write-Host "Checking SKILL.md..."
$skillMd = Join-Path $skillDir "SKILL.md"
if (Test-Path -LiteralPath $skillMd -PathType Leaf) {
    Write-Host "  [OK] SKILL.md exists"
    $content = Get-Content -LiteralPath $skillMd -Raw
    foreach ($field in @("---", "name:", "description:")) {
        if ($content.Contains($field)) {
            Write-Host "  [OK] contains $field"
        } else {
            Write-Host "  [ERROR] missing $field"
            $errors++
        }
    }
} else {
    Write-Host "  [ERROR] SKILL.md not found"
    $errors++
}

Write-Host ""
Write-Host "Checking references..."
$referencesDir = Join-Path $skillDir "references"
foreach ($name in @("architecture.md", "chronicle-format.md", "recover-guide.md")) {
    Test-RequiredFile (Join-Path $referencesDir $name)
}

Write-Host ""
Write-Host "Checking examples..."
$examplesDir = Join-Path $skillDir "examples"
foreach ($name in @("search-examples.ps1", "chronicle-examples.ps1", "recover-examples.ps1")) {
    Test-RequiredFile (Join-Path $examplesDir $name)
}

Write-Host ""
Write-Host "Checking scripts..."
foreach ($name in @(
    "retrace-index.py",
    "retrace-search.py",
    "retrace-analyze.py",
    "retrace-chronicle.py",
    "retrace-locate.py",
    "retrace-recover.py",
    "retrace_paths.py",
    "retrace_common.py",
    "validate-skill.ps1",
    "platforms\common.py",
    "platforms\codex.py",
    "platforms\claude.py",
    "platforms\pi.py"
)) {
    Test-RequiredFile (Join-Path $PSScriptRoot $name)
}

Write-Host ""
Write-Host "=== Validation Summary ==="
if ($errors -eq 0) {
    Write-Host "All critical checks passed."
    exit 0
}

Write-Host "Found $errors error(s)."
exit 1
