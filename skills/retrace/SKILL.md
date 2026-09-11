---
name: retrace
description: Search and analyze Codex, Claude Code, Kimi Code, Oh My Pi (OMP), and Grok CLI session history. Use when the user asks to find past conversations, recall prior work, search or analyze session history, locate an earlier implementation, recover a file/version, or mentions earlier, before, previously, last time, history, past work, OMP, Oh My Pi, or Grok CLI sessions.
---

# Retrace - Codex, Claude Code, Kimi Code, OMP, and Grok CLI Session History Search

Search and analyze Codex, Claude Code, Kimi Code, OMP, or Grok CLI conversation history using SQLite FTS full-text search with BM25 ranking.

## Architecture

- Runtime scripts are packaged inside this skill under `scripts/`. Do not point `RETRACE_SCRIPTS` at a repository-level or user-specific path.
- Codex sessions: `%CODEX_HOME%\sessions\**\*.jsonl` / `$CODEX_HOME/sessions/**/*.jsonl`, plus `archived_sessions`; default home is `~/.codex`.
- Codex indexes: `~/.codex/projects/<encoded-cwd>/retrace-index.db`.
- Claude Code sessions and indexes: `~/.claude/projects/<encoded-cwd>/*.jsonl`, `~/.claude/projects/<encoded-cwd>/*/subagents/*.jsonl`, and `retrace-index.db`, overridable with `CLAUDE_HOME`.
- Kimi Code sessions: `$KIMI_CODE_HOME/sessions/*/session_*/agents/*/wire.jsonl`; default home is `~/.kimi-code`. Indexes live at `~/.kimi-code/projects/<encoded-cwd>/retrace-index.db`.
- Kimi project attribution comes only from the session's `state.json.workDir`. If it is unavailable, skip attribution; never decode the generated `wd_` directory name.
- OMP sessions: `$PI_CODING_AGENT_SESSION_DIR/**/*.jsonl`, or `~/.omp/agent/sessions/**/*.jsonl` by default. Indexes live under `$PI_CODING_AGENT_DIR/projects/<encoded-cwd>`; the default agent home is `~/.omp/agent`. Honor `OMP_PROFILE` (or `PI_PROFILE`) as `~/.omp/profiles/<name>/agent`.
- OMP project attribution comes only from each JSONL `session` header's `cwd`; never decode OMP's session-directory name. Expand assistant `content[].type=toolCall` blocks and `role=toolResult` messages into separate tool events with native lowercase names.
- Grok CLI sessions: `$GROK_HOME/sessions/<url-encoded-cwd>/<session-id>/updates.jsonl`; default home is `~/.grok` and `GROK_HOME` is the only override. Indexes live at `~/.grok/projects/<encoded-cwd>/retrace-index.db`. The sibling `summary.json` holds metadata; `chat_history.jsonl` is not indexed.
- Grok project attribution comes only from `summary.json` `info.cwd`; fall back to URL-decoding the percent-encoded group directory name, then the group directory's `.cwd` file. Never apply Codex-style `-` decoding to Grok's directory names.
- The default platform is `codex`. Pass `--platform claude`, `--platform kimi`, `--platform omp`, or `--platform grok` explicitly for other platforms.
- Windows-first shell: prefer PowerShell 7 (`pwsh`) on this setup, but Unix `sh` examples are packaged under `examples/`.
- Platform modules under `platforms/` own platform-specific paths and parsing; `platforms/common.py` holds the shared data model.
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
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform omp --project poly-retrace --no-summary
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform grok --project poly-retrace --no-summary
```

```sh
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --auto --platform codex --project poly-retrace --no-summary
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --auto --platform claude --project poly-retrace --no-summary
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --auto --platform kimi --project poly-retrace --no-summary
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --auto --platform omp --project poly-retrace --no-summary
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --auto --platform grok --project poly-retrace --no-summary
```

Use `--no-summary` for normal local use. Summary and analysis commands call `codex exec`, which is slower and spends model calls.
They do not bypass sandbox or approval checks by default. Set `RETRACE_ALLOW_UNSANDBOXED_AI=1` only in trusted local environments when legacy unsandboxed behavior is required.

## List Sessions

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform codex --list-sessions --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform claude --list-sessions --project poly-retrace --json
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform kimi --list-sessions --project poly-retrace --json
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform omp --list-sessions --project poly-retrace --json
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform grok --list-sessions --project poly-retrace --json
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
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform omp "command" --type tool_use --tool bash --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform grok "command" --type tool_use --tool run_terminal_command --project poly-retrace
```

Use `--hybrid` for mixed Chinese/code/log queries. It combines the normal FTS index with a selective trigram index, so it is better for Chinese phrases, hyphenated terms, paths, and substrings.

Prefer `--hybrid` immediately when queries look like `录音确认超时 req_id`, `Wi-Fi whd_bus_sdio_init_oob_intr EEXIST host-wake`, `path/to/file.c:123`, or pasted log fragments. Default FTS is still fine for simple English/code tokens such as `pwsh`, `shell_command`, or a single function name.

## AI-Powered Analysis

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-analyze.py" "error" --platform codex --prompt "classify error types" --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-analyze.py" "query" --platform claude --prompt "summarize" --json
```

AI analysis still runs through `codex exec`; Kimi, OMP, and Grok support does not add platform-native analysis backends.

## Locate Sessions

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-locate.py" --platform kimi --session-id <uuid> --json
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-locate.py" --platform kimi --list --project poly-retrace --json
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-locate.py" --platform omp --session-id <uuid-or-prefix> --json
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-locate.py" --platform grok --session-id <uuid> --json
```

For Kimi, a located session returns the main Wire file first, followed by every subagent Wire file.
For OMP, resolve full IDs or unique prefixes and derive the project from the session header.
For Grok, the session ID is the UUIDv7 session-directory name and the project comes from `summary.json` `info.cwd`.

## Session Chronicle

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --platform codex --session <uuid> --project poly-retrace --output .\chronicle.toon
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --platform kimi --session <uuid> --project poly-retrace --output .\chronicle.toon
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --platform omp --session <uuid-or-prefix> --project poly-retrace --output .\chronicle.toon
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --platform grok --session <uuid> --project poly-retrace --output .\chronicle.toon
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
| `--tool` | `shell_command`, `apply_patch`, `Read`, `Bash`, `read`, `bash`, `task`, `run_terminal_command` (native names are platform-specific) |
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
| OMP sessions are missing | Check `PI_CODING_AGENT_DIR` and `PI_CODING_AGENT_SESSION_DIR`; expose a custom `--session-dir` through the latter. |
| OMP tool filter has no results | Use the native lowercase OMP name such as `bash`, `read`, or `task`. |
| Grok session is skipped | Verify the session's `summary.json` exists and contains `info.cwd`; the URL-decoded group directory name and the `.cwd` file are only fallbacks. |
| Grok tool filter has no results | Use the native Grok name such as `run_terminal_command`; names are not remapped across platforms. |

## Red Flags - Use Retrace

- "What did we do before?" -> search first.
- "Similar implementation?" -> find existing code.
- "Code was modified without git" -> use recover.
- "Need to restore previous version" -> use recover.
- "This seems familiar" -> search for it.
