---
name: retrace
description: This skill should be used when the user asks to "find past conversations", "recall what was done", "search history", "look up previous work", "how did we handle X", "what was that implementation", "find similar code", "search session", "analyze conversation history", "recover file", "restore previous version", or mentions terms like "earlier", "before", "previously", "last time", "history", "past work".
version: 0.4.0
---

# Retrace - Codex, Claude Code, and Kimi Code Session History Search

Search and analyze Codex, Claude Code, or Kimi Code conversation history using SQLite FTS full-text search with BM25 ranking.

## Architecture

- Runtime scripts are packaged inside this skill under `scripts/`. Do not point `RETRACE_SCRIPTS` at a repository-level or user-specific path.
- Codex sessions: `%CODEX_HOME%\sessions\**\*.jsonl` / `$CODEX_HOME/sessions/**/*.jsonl`, plus `archived_sessions`; default home is `~/.codex`.
- Codex indexes: `~/.codex/projects/<encoded-cwd>/retrace-index.db`.
- Claude Code sessions and indexes: `~/.claude/projects/<encoded-cwd>/*.jsonl`, `~/.claude/projects/<encoded-cwd>/*/subagents/*.jsonl`, and `retrace-index.db`, overridable with `CLAUDE_HOME`.
- Kimi Code sessions: `$KIMI_CODE_HOME/sessions/*/session_*/agents/*/wire.jsonl`; default home is `~/.kimi-code`. Indexes live at `~/.kimi-code/projects/<encoded-cwd>/retrace-index.db`.
- Kimi project attribution comes only from the session's `state.json.workDir`. If it is unavailable, skip attribution; never decode the generated `wd_` directory name.
- The default platform is `codex`. Pass `--platform claude` or `--platform kimi` explicitly for other platforms.
- Windows-first shell: prefer PowerShell 7 (`pwsh`) on this setup, but Unix `sh` examples are packaged under `examples/`.
- Platform modules: `platforms/codex.py`, `platforms/claude.py`, and `platforms/kimi.py` own platform-specific paths and parsing; `platforms/common.py` holds the shared data model.
- Compatibility facade: `retrace_paths.py` exposes the small public API used by scripts.

## Core Workflow

1. Set script and Python variables for the current shell.
2. Ensure the project index exists before searching.
3. Search with layered output: `stats`, `list`, then `detail`.
4. Use `--hybrid` proactively for mixed Chinese/code/log queries, especially Chinese phrases plus code symbols, error names, hyphenated terms, paths, or long tool outputs.
5. Use `chronicle` for single-session history extraction.
6. Use `recover` for file version restoration.

## PowerShell Setup

Run commands from the loaded `retrace` skill directory, where this `SKILL.md` lives.

```powershell
Set-Location <loaded-retrace-skill-directory>
$env:RETRACE_SCRIPTS = Join-Path (Get-Location) "scripts"
$PYTHON_CMD = "python"
```

## Unix Setup

Run commands from the loaded `retrace` skill directory, where this `SKILL.md` lives.

```sh
RETRACE_SCRIPTS="$(pwd)/scripts"
PYTHON_CMD="python3"
```

## Ensure Index Exists

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform codex --project poly-retrace --no-summary
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform claude --project poly-retrace --no-summary
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform kimi --project poly-retrace --no-summary
```

```sh
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --auto --platform codex --project poly-retrace --no-summary
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --auto --platform claude --project poly-retrace --no-summary
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --auto --platform kimi --project poly-retrace --no-summary
```

Use `--no-summary` for normal local use. Summary and analysis commands call `codex exec`, which is slower and spends model calls.
They do not bypass sandbox or approval checks by default. Set `RETRACE_ALLOW_UNSANDBOXED_AI=1` only in trusted local environments when legacy unsandboxed behavior is required.

## List Sessions

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform codex --list-sessions --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform claude --list-sessions --project poly-retrace --json
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform kimi --list-sessions --project poly-retrace --json
```

## Search Sessions

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform codex "query" --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform codex --hybrid "Wi-Fi whd_bus_sdio_init_oob_intr EEXIST host-wake" --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform claude "error" --level stats --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform codex "pwsh" --type tool_use --tool shell_command --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform kimi --hybrid "录音确认超时 req_id" --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform kimi "command" --type tool_use --tool Bash --session <uuid> --since 2026-01-01 --until 2027-01-01 --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform kimi --context <id> --before 5 --after 5 --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform kimi --full <id> --project poly-retrace
```

Use `--hybrid` for mixed Chinese/code/log queries. It combines the normal FTS index with a selective trigram index, so it is better for Chinese phrases, hyphenated terms, paths, and substrings.

Prefer `--hybrid` immediately when queries look like `录音确认超时 req_id`, `Wi-Fi whd_bus_sdio_init_oob_intr EEXIST host-wake`, `path/to/file.c:123`, or pasted log fragments. Default FTS is still fine for simple English/code tokens such as `pwsh`, `shell_command`, or a single function name.

## AI-Powered Analysis

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-analyze.py" "error" --platform codex --prompt "classify error types" --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-analyze.py" "query" --platform claude --prompt "summarize" --json
```

AI analysis still runs through `codex exec`; Kimi support applies to index, search, locate, and chronicle, not to a Kimi-native analysis backend.

## Locate Sessions

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-locate.py" --platform kimi --session-id <uuid> --json
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-locate.py" --platform kimi --list --project poly-retrace --json
```

For Kimi, a located session returns the main Wire file first, followed by every subagent Wire file.

## Session Chronicle

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --platform codex --session <uuid> --project poly-retrace --output .\chronicle.toon
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --platform kimi --session <uuid> --project poly-retrace --output .\chronicle.toon
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --platform codex --file "$HOME\.codex\sessions\2026\05\09\<session>.jsonl" --output .\chronicle.json --json
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
| `--tool` | `shell_command`, `apply_patch`, `Read`, `Bash` (native names are platform-specific) |
| `--project` | Project name or encoded path fragment |
| `--session` | Session UUID |
| `--since` | Start date (ISO) |
| `--until` | End date (ISO) |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Kimi index is missing | Run `retrace-index.py --auto --platform kimi --project <name> --no-summary`. |
| Kimi session is skipped | Verify `<session>/state.json` exists and contains the real `workDir`; Retrace does not guess from `wd_`. |
| Kimi tool filter has no results | Use the native Kimi name such as `Bash`, `Read`, or `Skill`; names are not remapped across platforms. |

## Red Flags - Use Retrace

- "What did we do before?" -> search first.
- "Similar implementation?" -> find existing code.
- "Code was modified without git" -> use recover.
- "Need to restore previous version" -> use recover.
- "This seems familiar" -> search for it.
