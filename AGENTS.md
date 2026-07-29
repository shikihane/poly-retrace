# AGENTS.md - Poly-Retrace Skill

Codex, Claude Code, and Kimi Code session history search and analysis skill.

## Overview

Poly-retrace searches and analyzes Codex, Claude Code, or Kimi Code conversation history using SQLite FTS with BM25 ranking.

## Architecture

```
poly-retrace/
├── skills/
│   └── retrace/
│       ├── SKILL.md
│       └── scripts/
│           ├── retrace_paths.py
│           ├── platforms/
│           │   ├── common.py
│           │   ├── codex.py
│           │   ├── claude.py
│           │   └── kimi.py
│           ├── retrace_common.py
│           ├── retrace-locate.py
│           ├── retrace-index.py
│           ├── retrace-search.py
│           ├── retrace-analyze.py
│           └── retrace-chronicle.py
└── AGENTS.md
```

This project is distributed as a standalone skill. Do not publish or deploy it as a Claude plugin.

## Critical Rules

### Windows Shell

This project targets the author's Windows environment. Prefer PowerShell 7 directly:

```powershell
pwsh
```

No bash compatibility is required for normal usage.

### Script Path

All runtime scripts must live under `skills/retrace/scripts`. After loading the skill, call scripts via the skill-local `$env:RETRACE_SCRIPTS`:

```powershell
Set-Location .\skills\retrace
$env:RETRACE_SCRIPTS = Join-Path (Get-Location) "scripts"
$PYTHON_CMD = "python"
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" "query"
```

### Skill Installation

Do not assume one skill directory covers all clients. When installing or refreshing this skill locally, update every runtime that may provide slash-command or skill autocomplete:

| Client | Skill directory |
|--------|-----------------|
| Claude Code | `$HOME\.claude\skills\retrace` |
| Codex Desktop | `$HOME\.codex\skills\retrace` |
| Agent skill autocomplete | `$HOME\.agents\skills\retrace` |

For this Windows setup, also check both user-home aliases when they exist:

- `C:\Users\式羽\...`
- `C:\Users\shikihane\...`

The `SKILL.md` frontmatter name must be lowercase and match the directory:

```yaml
name: retrace
```

After copying, verify the installed copy, not just the repository source:

```powershell
pwsh -NoLogo -NoProfile -File "$HOME\.claude\skills\retrace\scripts\validate-skill.ps1"
python "$HOME\.claude\skills\retrace\scripts\retrace-search.py" --version
Get-Content "$HOME\.claude\skills\retrace\SKILL.md" -TotalCount 3
```

If `/retrace` does not appear in autocomplete, first check whether the UI is reading `.claude\skills`, `.codex\skills`, or `.agents\skills`; then restart the client or open a new session to clear autocomplete caches.

### Index Before Search

Always choose a platform explicitly when you do not want the Codex default:

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform codex --project poly-retrace --no-summary
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform claude --project poly-retrace --no-summary
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform kimi --project poly-retrace --no-summary
```

Use `--no-summary` for routine local indexing. AI summary and analysis paths call `codex exec`.

AI summary and analysis commands run without bypassing sandbox/approval checks by default. Set `RETRACE_ALLOW_UNSANDBOXED_AI=1` only in a trusted local environment if you explicitly need the legacy bypass behavior.

## Data Storage

| Item | Location |
|------|----------|
| Platform | Source sessions | Index database |
|----------|-----------------|----------------|
| Codex | `$HOME\.codex\sessions\**\*.jsonl`, `$HOME\.codex\archived_sessions\*.jsonl` | `$HOME\.codex\projects\<encoded-cwd>\retrace-index.db` |
| Claude Code | `$HOME\.claude\projects\<encoded-cwd>\*.jsonl` | `$HOME\.claude\projects\<encoded-cwd>\retrace-index.db` |
| Kimi Code | `$env:KIMI_CODE_HOME\sessions\*\session_*\agents\*\wire.jsonl` (default home `$HOME\.kimi-code`) | `$env:KIMI_CODE_HOME\projects\<encoded-cwd>\retrace-index.db` |

Each platform keeps its own project index root. Do not mix indexes from different platforms in the same directory. `KIMI_CODE_HOME` overrides the Kimi home.

### Path Encoding

Windows paths are encoded with the drive separator as `--` and path separators as `-`:

`X:\Work\example-project` -> `X--Work-example-project`

Because hyphens can also appear in real path components, decoding is best-effort unless a Codex `session_meta.payload.cwd` record is available.

Kimi is different: project attribution and decoding use only the session's `state.json.workDir`. Missing or invalid state means no project attribution; never parse the generated `wd_` directory name. See `skills/retrace/references/adr-001-kimi-project-attribution.md`.

## Script Reference

### Index

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform codex --project poly-retrace --no-summary
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform claude --project poly-retrace --no-summary
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform kimi --project poly-retrace --no-summary
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --stats
```

### Search

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform codex --list-sessions --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform claude "query" --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform codex --hybrid "Wi-Fi whd_bus_sdio_init_oob_intr EEXIST host-wake" --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform codex "pwsh" --type tool_use --tool shell_command --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform kimi --hybrid "录音确认超时 req_id" --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform kimi "command" --type tool_use --tool Bash --session <uuid> --since 2026-01-01 --until 2027-01-01 --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --context <id> --before 5 --after 5
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --full <id>
```

Use `--hybrid` proactively for mixed Chinese/code/log queries such as `录音确认超时 req_id`, `Wi-Fi whd_bus_sdio_init_oob_intr EEXIST host-wake`, paths, error names, hyphenated terms, or pasted log fragments. Default FTS is still fine for simple English/code tokens.

### Locate

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-locate.py" --platform codex --session-id <uuid> --json
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-locate.py" --platform kimi --session-id <uuid> --json
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-locate.py" --platform codex --list
```

### Analyze

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-analyze.py" "error" --prompt "summarize errors" --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-analyze.py" "bug" --prompt "classify" --json
```

### Chronicle

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --platform codex --session <uuid> --project poly-retrace --output .\chronicle.toon
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --platform kimi --session <uuid> --project poly-retrace --output .\chronicle.toon
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --file "$HOME\.codex\sessions\2026\05\09\<session>.jsonl" --output .\chronicle.json --json
```

## Filter Options

| Filter | Values |
|--------|--------|
| `--type` | `session_meta`, `turn_context`, `user`, `assistant`, `tool_use`, `tool_result` |
| `--role` | `user`, `assistant`, `tool` |
| `--tool` | Platform-native names: `shell_command`, `apply_patch`, `Bash`, `Read`, `Skill`, etc. |
| `--project` | Project name or encoded path fragment |
| `--session` | Session UUID |
| `--since` | ISO date |
| `--until` | ISO date |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "索引数据库不存在" | Run `retrace-index.py --auto --platform <codex\|claude\|kimi> --project <name> --no-summary` |
| No results | Check project filter, then retry complex Chinese/code/log queries with `--hybrid` |
| Kimi session is not attributed | Check that its `state.json` is valid and has `workDir`; do not infer from `wd_` |
| Kimi tool filter has no results | Use the original Kimi tool name (`Bash`, `Read`, `Skill`, etc.) |
| Query with `-` errors | Search now quotes plain text FTS queries; rebuild if using old scripts |
| Garbled console output | Run through PowerShell 7; scripts also force UTF-8 stdio |
