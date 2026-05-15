# poly-retrace

Search and analyze Codex and Claude Code conversation history with SQLite FTS full-text search, BM25 ranking, and AI-powered summaries.

Chinese version: [README_CN.md](./README_CN.md).

## What it does

- Indexes every Codex and Claude Code session JSONL into a per-project SQLite database.
- Full-text search with BM25 ranking, plus a hybrid trigram mode for Chinese, paths, hyphenated names, and pasted log fragments.
- Layered search output (`stats` -> `list` -> `detail` -> `full`) to keep token budgets under control.
- Single-session chronicle extraction to TOON / JSON for handoff or memory.
- File-version recovery from session history when a file was edited without git.
- Optional AI analysis through `codex exec` for classification, summarization, and error triage.

## Platforms

- Codex sessions: `%CODEX_HOME%\sessions\**\*.jsonl` / `$CODEX_HOME/sessions/**/*.jsonl`, plus `archived_sessions`; default home is `~/.codex`.
- Claude Code sessions: `%CLAUDE_HOME%\projects\<encoded-cwd>\*.jsonl` / `$CLAUDE_HOME/projects/<encoded-cwd>/*.jsonl`; default home is `~/.claude`.
- Indexes live under each platform home at `projects/<encoded-cwd>/retrace-index.db`.

Pass `--platform codex` or `--platform claude` explicitly.

### Path encoding

Windows paths are encoded with the drive separator as `--` and path separators as `-`:

`X:\Work\example-project` -> `X--Work-example-project`.

Unix paths are encoded by stripping the leading slash and replacing path separators with `-`:

`/home/user/example-project` -> `home-user-example-project`.

Hyphens can appear in real path components, so decoding is best-effort unless a Codex `session_meta.payload.cwd` record is available.

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

# Stats
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-index.py" --stats --platform codex
```

```sh
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --auto --platform codex --project poly-retrace --no-summary
"$PYTHON_CMD" "$RETRACE_SCRIPTS/retrace-index.py" --auto --platform claude --project poly-retrace --no-summary
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
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform codex --hybrid "Wi-Fi whd_bus_sdio_init_oob_intr EEXIST host-wake" --project poly-retrace

# Filtered
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --platform codex "pwsh" --type tool_use --tool shell_command --project poly-retrace

# Context window around a result id
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --context <id> --before 5 --after 5

# Full content of a single record
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-search.py" --full <id>
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
| `--tool`     | `shell_command`, `apply_patch`, `read_mcp_resource`, `Read`, `Edit` |
| `--project`  | Project name or encoded-path fragment                           |
| `--session`  | Session UUID                                                    |
| `--since`    | ISO start date                                                  |
| `--until`    | ISO end date                                                    |

## Locate

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-locate.py" --platform codex --session-id <uuid> --json
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-locate.py" --platform codex --list
```

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
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-chronicle.py" --platform codex --file "$HOME\.codex\sessions\2026\05\09\<session>.jsonl" --output .\chronicle.json --json
```

Chronicle preserves code snippets, shell / git / npm commands, file paths touched, errors and stack traces, technical decisions, and rework reasons.

## Recover

Reconstruct file versions from a session when edits were not committed to git. Trusts only full `Write`, full `Read`, and full `cat`-style outputs.

```powershell
& $PYTHON_CMD "$env:RETRACE_SCRIPTS\retrace-recover.py" --platform codex --session <uuid> --project poly-retrace --file "skills\retrace\scripts\retrace-index.py" --output .\recovery
```

## Skill entry point

`skills/retrace/SKILL.md` is the Claude Code skill that triggers on phrases like "find past conversations", "recall what was done", "search history", "recover file", and similar. The skill drives the same scripts described above.

## Troubleshooting

| Issue                              | Fix                                                                                          |
|------------------------------------|----------------------------------------------------------------------------------------------|
| "索引数据库不存在" / index missing   | Run `retrace-index.py --auto --platform <codex|claude> --project <name> --no-summary`.       |
| No results                         | Verify `--project`, broaden the query, then retry with `--hybrid`.                           |
| Query with `-` raises FTS errors   | Update to the current script; queries are auto-quoted when they contain non-word characters. |
| Garbled console output             | Run under PowerShell 7. Scripts also force UTF-8 stdio.                                      |
| Empty analyze / chronicle result   | Check the file path and make sure search returns rows first.                                 |

## Version

This project is distributed as a standalone skill. See `skills/retrace/SKILL.md` and individual script headers for versions.
