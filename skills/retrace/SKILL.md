---
name: Retrace
description: This skill should be used when the user asks to "find past conversations", "recall what was done", "search history", "look up previous work", "how did we handle X", "what was that implementation", "find similar code", "search session", "analyze conversation history", "recover file", "restore previous version", or mentions terms like "earlier", "before", "previously", "last time", "history", "past work".
version: 0.3.0
---

# Retrace - Codex and Claude Code Session History Search

Search and analyze Codex or Claude Code conversation history using SQLite FTS full-text search with BM25 ranking.

## Architecture

- Codex sessions: `$env:CODEX_HOME\sessions\**\*.jsonl` and `$env:CODEX_HOME\archived_sessions\*.jsonl`; default home is `$HOME\.codex`.
- Codex indexes: `$env:CODEX_HOME\projects\<encoded-cwd>\retrace-index.db`.
- Claude Code sessions and indexes: `$env:CLAUDE_HOME\projects\<encoded-cwd>\*.jsonl` and `retrace-index.db`; default home is `$HOME\.claude`.
- Platform selection is mandatory: pass `--platform codex` or `--platform claude`.
- Windows-first shell: use PowerShell 7 (`pwsh`) examples and commands.
- Platform modules: `platforms/codex.py` and `platforms/claude.py` own platform-specific paths; `platforms/common.py` holds the shared data model.
- Compatibility facade: `retrace_paths.py` exposes the small public API used by scripts.

## Core Workflow

1. Set script and Python variables in PowerShell 7.
2. Ensure the project index exists before searching.
3. Search with layered output: `stats`, `list`, then `detail`.
4. Use `chronicle` for single-session history extraction.
5. Use `recover` for file version restoration.

## PowerShell Setup

```powershell
$env:RETRACE_SCRIPTS = "D:\Projects\poly-retrace\scripts"
$PYTHON_CMD = "python"
```

## Ensure Index Exists

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform codex --project poly-retrace --no-summary
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform claude --project poly-retrace --no-summary
```

Use `--no-summary` for normal local use. Summary and analysis commands call `codex exec`, which is slower and spends model calls.

## List Sessions

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform codex --list-sessions --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform claude --list-sessions --project poly-retrace --json
```

## Search Sessions

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform codex "query" --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform claude "error" --level stats --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform codex "pwsh" --type tool_use --tool shell_command --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --context <id> --before 5 --after 5
```

## AI-Powered Analysis

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-analyze.py" "error" --prompt "classify error types" --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-analyze.py" "query" --prompt "summarize" --json
```

## Session Chronicle

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --platform codex --session <uuid> --project poly-retrace --output .\chronicle.toon
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --file "$HOME\.codex\sessions\2026\05\09\<session>.jsonl" --output .\chronicle.json --json
```

## File Recovery

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-recover.py" --platform codex --session <uuid> --project poly-retrace --file "scripts\retrace-index.py" --output .\recovery
```

## Search Levels

| Level | Output | Token Cost |
|-------|--------|------------|
| `stats` | Counts and distributions | ~50 |
| `list` | ID, timestamp, preview | ~500 |
| `detail` | Full preview, file location | ~2000 |
| `full` | Complete message | Variable |

Default workflow: `stats` -> `list` -> `detail` -> `full`.

## Filter Options

| Filter | Example |
|--------|---------|
| `--type` | `tool_result`, `tool_use`, `user`, `assistant` |
| `--role` | `user`, `assistant`, `tool` |
| `--tool` | `shell_command`, `apply_patch`, `Read` |
| `--project` | Project name or encoded path fragment |
| `--session` | Session UUID |
| `--since` | Start date (ISO) |
| `--until` | End date (ISO) |

## Red Flags - Use Retrace

- "What did we do before?" -> search first.
- "Similar implementation?" -> find existing code.
- "Code was modified without git" -> use recover.
- "Need to restore previous version" -> use recover.
- "This seems familiar" -> search for it.
