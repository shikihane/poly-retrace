# poly-retrace

Search and analyze Codex, Claude Code, Kimi Code, Oh My Pi (OMP), and Grok CLI conversation history with SQLite FTS full-text search, BM25 ranking, and AI-powered summaries.

Chinese version: [README_CN.md](./README_CN.md).

## What it does

- Indexes Codex, Claude Code, OMP, and Grok CLI session JSONL plus Kimi Wire files into per-project SQLite databases.
- Full-text search with BM25 ranking, plus a hybrid trigram mode for Chinese, paths, hyphenated names, and pasted log fragments.
- Layered search output (`stats` -> `list` -> `detail` -> `full`) to keep token budgets under control.
- Single-session chronicle extraction to TOON / JSON for handoff or memory.
- File-version recovery from session history when a file was edited without git.
- Optional AI analysis through `codex exec` for classification, summarization, and error triage.

## Platforms

- Codex sessions: `%CODEX_HOME%\sessions\**\*.jsonl` / `$CODEX_HOME/sessions/**/*.jsonl`, plus `archived_sessions`; default home is `~/.codex`.
- Claude Code sessions: `%CLAUDE_HOME%\projects\<encoded-cwd>\*.jsonl` / `$CLAUDE_HOME/projects/<encoded-cwd>/*.jsonl`; default home is `~/.claude`.
- Kimi Code sessions: `%KIMI_CODE_HOME%\sessions\*\session_*\agents\*\wire.jsonl` / `$KIMI_CODE_HOME/sessions/*/session_*/agents/*/wire.jsonl`; default home is `~/.kimi-code`.
- OMP sessions: `%PI_CODING_AGENT_SESSION_DIR%\**\*.jsonl` / `$PI_CODING_AGENT_SESSION_DIR/**/*.jsonl`, or `~/.omp/agent/sessions/**/*.jsonl` by default.
- Grok CLI sessions: `%GROK_HOME%\sessions\<url-encoded-cwd>\<session-id>\updates.jsonl` / `$GROK_HOME/sessions/<url-encoded-cwd>/<session-id>/updates.jsonl`; default home is `~/.grok`.
- Indexes live under each platform home at `projects/<encoded-cwd>/retrace-index.db`.

The default platform is `codex`. Pass `--platform claude`, `--platform kimi`, `--platform omp`, or `--platform grok` for other platforms. `KIMI_CODE_HOME` overrides the Kimi home. `PI_CODING_AGENT_DIR` overrides the OMP agent home; `PI_CODING_AGENT_SESSION_DIR` overrides its session root. `OMP_PROFILE` (or legacy `PI_PROFILE`) selects `~/.omp/profiles/<name>/agent`. `GROK_HOME` is the only override for the Grok home.

Kimi project attribution comes only from each session's `state.json.workDir`. A missing or invalid state file leaves the session unattributed; Retrace never guesses from the generated `wd_` directory name. See [ADR 001](./skills/retrace/references/adr-001-kimi-project-attribution.md).

OMP project attribution comes only from each JSONL `session` header's `cwd`; Retrace does not decode OMP's session-directory name. Assistant `content[].type=toolCall` blocks and `role=toolResult` messages are indexed as separate tool events with native lowercase names such as `read`, `bash`, and `task`.

Grok CLI project attribution comes only from each session's `summary.json` `info.cwd`. If the summary is missing or invalid, Retrace falls back to URL-decoding the percent-encoded group directory name, then to the `.cwd` file written for slugged long names; it never applies Codex-style `-` decoding to Grok's directory names. The append-only `updates.jsonl` ACP event stream is indexed; the sibling `chat_history.jsonl` is not. Tool events keep Grok's native names such as `run_terminal_command`. See [ADR 002](./skills/retrace/references/adr-002-grok-project-attribution.md).

### Path encoding

Windows paths are encoded with the drive separator as `--` and path separators as `-`:

`X:\Work\example-project` -> `X--Work-example-project`.

Unix paths are encoded by stripping the leading slash and replacing path separators with `-`:

`/home/user/example-project` -> `home-user-example-project`.

Hyphens can appear in real path components, so decoding is best-effort unless Codex provides `session_meta.payload.cwd`, Kimi provides `state.json.workDir`, or OMP provides its session-header `cwd`.

## Layout

```
poly-retrace/
|-- skills/retrace/SKILL.md       # skill entry point
|-- skills/retrace/scripts/
|   |-- retrace_paths.py          # compatibility facade over platforms/
|   |-- retrace_common.py         # shared helpers (search, chunking, AI calls)
|   |-- platforms/
|   |   |-- common.py             # shared data model
|   |   |-- codex.py              # Codex paths and parsing
|   |   |-- claude.py             # Claude Code paths and parsing
|   |   |-- grok.py               # Grok paths, summary, and updates.jsonl parsing
|   |   |-- kimi.py               # Kimi paths, state, and Wire parsing
|   |   |-- omp.py                # OMP paths, headers, and message/tool parsing
|   |-- retrace-index.py          # build / refresh FTS index
|   |-- retrace-search.py         # search (FTS or hybrid)
|   |-- retrace-locate.py         # locate session files
|   |-- retrace-analyze.py        # AI analysis over search results
|   |-- retrace-chronicle.py      # single-session history extraction
|   |-- retrace-recover.py        # recover file versions from history
|   |-- list-session.py
|   |-- clean-index.py
|-- tests/
|-- AGENTS.md
```

## Setup

This project is Windows-first, but the Python runtime scripts and shell examples are portable across normal Unix environments.

```powershell
$env:RETRACE_SCRIPTS = Join-Path (Get-Location) "skills\retrace\scripts"
$PYTHON_CMD = "python"
```

```sh
RETRACE_SCRIPTS="$(pwd)/skills/retrace/scripts"
PYTHON_CMD="python3"
```

No external Python dependencies are required for indexing and searching; SQLite FTS5 ships with modern Python, and the scripts fall back to FTS4 if FTS5 is missing.

AI summary and analysis paths shell out to `codex exec`. They do not bypass sandbox or approval checks by default. Set `RETRACE_ALLOW_UNSANDBOXED_AI=1` only in a trusted local environment if you explicitly need legacy bypass behavior.

## Index

Always ensure the index is current before searching.

```powershell
# Codex
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform codex --project poly-retrace --no-summary

# Claude Code
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform claude --project poly-retrace --no-summary

# Kimi Code (includes main and subagent Wire files)
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform kimi --project poly-retrace --no-summary

# OMP
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform omp --project poly-retrace --no-summary

# Grok CLI (indexes updates.jsonl ACP event streams)
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --auto --platform grok --project poly-retrace --no-summary

# Stats
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --stats --platform codex
```

```sh
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --auto --platform codex --project poly-retrace --no-summary
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --auto --platform claude --project poly-retrace --no-summary
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --auto --platform kimi --project poly-retrace --no-summary
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --auto --platform omp --project poly-retrace --no-summary
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --auto --platform grok --project poly-retrace --no-summary
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --stats --platform codex
```

Use `--no-summary` for routine local indexing. Drop it only when you want Codex-generated session summaries; that path spends model calls.

## Search

```powershell
# List sessions
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform codex --list-sessions --project poly-retrace

# Basic query
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform claude "query" --project poly-retrace

# Hybrid query (use proactively for mixed Chinese / code / log inputs)
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform kimi --hybrid "录音确认超时 req_id" --project poly-retrace

# Filtered with Kimi's native tool name
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform kimi "command" --type tool_use --tool Bash --session <uuid> --since 2026-01-01 --until 2027-01-01 --project poly-retrace

# Filtered with OMP's native lowercase tool name
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform omp "command" --type tool_use --tool bash --project poly-retrace

# Filtered with Grok's native tool name
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform grok "command" --type tool_use --tool run_terminal_command --project poly-retrace

# Context window around a result id
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform kimi --context <id> --before 5 --after 5 --project poly-retrace

# Full content of a single record
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform kimi --full <id> --project poly-retrace
```

When to reach for `--hybrid` first:

- Chinese phrases plus code symbols, for example `录音确认超时 req_id`.
- Hyphenated or dotted names and paths, for example `whd_bus_sdio_init_oob_intr`, `path/to/file.c:123`.
- Pasted log fragments or error strings.

Plain FTS is still ideal for simple English / code tokens such as `pwsh`, `shell_command`, or a single function name.

### Layered output

| Level  | Output                          | Approx tokens |
|--------|---------------------------------|---------------|
| stats  | Counts and distributions        | ~50           |
| list   | Id, timestamp, preview          | ~500          |
| detail | Full preview, file location     | ~2000         |
| full   | Complete message                | variable      |

### Filters

| Filter       | Examples                                                        |
|--------------|-----------------------------------------------------------------|
| `--type`     | `session_meta`, `turn_context`, `user`, `assistant`, `tool_use`, `tool_result` |
| `--role`     | `user`, `assistant`, `tool`                                     |
| `--tool`     | Platform-native names: `shell_command`, `apply_patch`, `Bash`, `Read`, `Skill`, `bash`, `read`, `task`, `run_terminal_command` |
| `--project`  | Project name or encoded-path fragment                           |
| `--session`  | Session UUID                                                    |
| `--since`    | ISO start date                                                  |
| `--until`    | ISO end date                                                    |

## Locate

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-locate.py" --platform codex --session-id <uuid> --json
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-locate.py" --platform kimi --session-id <uuid> --json
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-locate.py" --platform kimi --list --project poly-retrace --json
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-locate.py" --platform omp --session-id <uuid-or-prefix> --json
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-locate.py" --platform grok --session-id <uuid> --json
```

Kimi locate results put the main Wire file first and include all subagent Wire files.

OMP accepts full session IDs or unique prefixes and derives the project from the session header rather than the source directory name.

Grok session IDs are the UUIDv7 session-directory names; locate returns the session's `updates.jsonl` and derives the project from `summary.json` `info.cwd`.

## Analyze

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-analyze.py" "error" --platform codex --prompt "classify error types" --project poly-retrace
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-analyze.py" "bug" --platform claude --prompt "summarize" --json
```

Small result sets go through a single `codex exec` call. Large sets are chunked in parallel; expect roughly 5-7 seconds per small call and 15-22 seconds per chunk, with up to 20 concurrent chunks.

## Chronicle

Single-session history extraction with strong prompt constraints. Emits TOON by default, JSON on request.

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --platform codex --session <uuid> --project poly-retrace --output .\chronicle.toon
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --platform kimi --session <uuid> --project poly-retrace --output .\chronicle.toon
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --platform omp --session <uuid-or-prefix> --project poly-retrace --output .\chronicle.toon
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --platform grok --session <uuid> --project poly-retrace --output .\chronicle.toon
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --platform codex --file "$HOME\.codex\sessions\2026\05\09\<session>.jsonl" --output .\chronicle.json --json
```

Chronicle preserves code snippets, shell / git / npm commands, file paths touched, errors and stack traces, technical decisions, and rework reasons.

## Recover

Reconstruct file versions from a session when edits were not committed to git. Trusts only full `Write`, full `Read`, and full `cat`-style outputs.

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-recover.py" --platform codex --session <uuid> --project poly-retrace --file "skills\retrace\scripts\retrace-index.py" --output .\recovery
```

## Skill entry point

`skills/retrace/SKILL.md` is the standalone skill entry point used by supported agent clients. It triggers on phrases like "find past conversations", "recall what was done", "search history", "recover file", and similar, then drives the scripts described above.

## Troubleshooting

| Issue                              | Fix                                                                                          |
|------------------------------------|----------------------------------------------------------------------------------------------|
| "索引数据库不存在" / index missing   | Run `retrace-index.py --auto --platform <codex|claude|kimi|omp|grok> --project <name> --no-summary`. |
| No results                         | Verify `--project`, broaden the query, then retry with `--hybrid`.                           |
| Kimi session is skipped            | Verify its `state.json` exists and contains `workDir`; `wd_` is never decoded.              |
| Kimi `--tool` finds nothing        | Use the original Kimi name such as `Bash`, `Read`, or `Skill`.                              |
| OMP sessions are missing           | Check `PI_CODING_AGENT_DIR` / `PI_CODING_AGENT_SESSION_DIR`; expose custom `--session-dir` through the latter. |
| OMP `--tool` finds nothing         | Use OMP's original lowercase name such as `bash`, `read`, or `task`.                        |
| Grok session is skipped            | Verify its `summary.json` exists and contains `info.cwd`; URL-decoding the group directory name and the `.cwd` file are only fallbacks. |
| Grok `--tool` finds nothing        | Use Grok's original tool name such as `run_terminal_command`.                              |
| Query with `-` raises FTS errors   | Update to the current script; queries are auto-quoted when they contain non-word characters. |
| Garbled console output             | Run under PowerShell 7. Scripts also force UTF-8 stdio.                                      |
| Empty analyze / chronicle result   | Check the file path and make sure search returns rows first.                                 |

## Version

This project is distributed as a standalone skill. See `skills/retrace/SKILL.md` and individual script headers for versions.
