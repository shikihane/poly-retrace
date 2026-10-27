# Architecture Reference

## Overview

Retrace indexes Codex, Claude Code, Kimi Code, Oh My Pi (OMP), Grok CLI, and DeepSeek Harness (DSH) session
history into separate per-platform, per-project SQLite databases. Search uses FTS5 with
BM25 ranking and a selective trigram index for mixed Chinese, code, path, and log queries.

## Platform Storage

| Platform | Source sessions | Project index |
|----------|-----------------|---------------|
| Codex | `~/.codex/sessions/**/*.jsonl`, `~/.codex/archived_sessions/*.jsonl` | `~/.codex/projects/<encoded-cwd>/retrace-index.db` |
| Claude Code | `~/.claude/projects/<encoded-cwd>/**/*.jsonl` | `~/.claude/projects/<encoded-cwd>/retrace-index.db` |
| Kimi Code | `~/.kimi-code/sessions/*/session_*/agents/*/wire.jsonl` | `~/.kimi-code/projects/<encoded-cwd>/retrace-index.db` |
| OMP | `~/.omp/agent/sessions/**/*.jsonl` | `~/.omp/agent/projects/<encoded-cwd>/retrace-index.db` |
| DSH | `~/.dsh/sessions/*/*/session.v4.jsonl[.zstd]` | `~/.dsh/projects/<encoded-cwd>/retrace-index.db` |
| Grok CLI | `~/.grok/sessions/<url-encoded-cwd>/<session-id>/updates.jsonl` | `~/.grok/projects/<encoded-cwd>/retrace-index.db` |

`CODEX_HOME`, `CLAUDE_HOME`, and `KIMI_CODE_HOME` override the corresponding defaults.
`PI_CODING_AGENT_DIR` overrides the OMP agent home, while
`PI_CODING_AGENT_SESSION_DIR` overrides only the OMP session root.
`OMP_PROFILE` takes precedence over legacy `PI_PROFILE` and selects
`~/.omp/profiles/<name>/agent` when no explicit session-root override is set.
`GROK_HOME` is the only override for the Grok home. `DSH_HOME` overrides the DSH home.
Indexes from different platforms must not share a project directory.

Kimi's project bucket is derived only from `state.json.workDir`. Retrace does not parse
the generated `wd_` directory name. See
[ADR 001](./adr-001-kimi-project-attribution.md).

Each Grok session's project bucket is derived only from its `summary.json` `info.cwd`.
When the summary is missing or invalid, Retrace falls back to URL-decoding the
percent-encoded group directory name, then to the `.cwd` file the Grok CLI writes when
it has to slug a long directory name. Grok's percent-encoding is never confused with
Retrace's own `-`-style bucket encoding. See
[ADR 002](./adr-002-grok-project-attribution.md).

Each OMP JSONL's project bucket is derived only from its first valid `session` header's
`cwd`. A task/advisor artifact running in an isolated worktree therefore belongs to that
worktree's project bucket. The optional fixed-width `title` slot may precede the header,
and OMP's own encoded session-directory name is never used for attribution.

Nested `<root-session-stem>/<task-run-id>.jsonl` files remain independently searchable
by their physical header session ID. Locate/list operations expose only root sessions and
attach nested task/advisor transcripts as their `files`; Chronicle merges that family.

## Platform Boundary

- `platforms/common.py` defines the shared platform data model.
- `platforms/codex.py` and `platforms/claude.py` own their session traversal.
- `platforms/kimi.py` owns Kimi session traversal, state lookup, Wire normalization,
  session IDs, agent IDs, and epoch-millisecond timestamps.
- `platforms/omp.py` owns OMP traversal, title-slot-aware session headers, message/tool
  expansion, session IDs, project cwd, and unique task-run IDs from artifact sidecar filenames.
- `platforms/grok.py` owns Grok traversal, `summary.json`/`info.cwd` attribution with
  URL-decode and `.cwd` fallbacks, `updates.jsonl` ACP session-update normalization,
  session IDs, and epoch-second timestamps.
- `platforms/dsh.py` owns V4 generation selection, Zstandard/plaintext decoding, header attribution, native session IDs, subagent lineage, and event normalization.
- `retrace_paths.py` is the compatibility facade used by runtime scripts.

The default platform is Codex. Index, search, locate, chronicle, and search-backed analyze
accept Kimi, OMP, Grok, and DSH. Analyze still shells out through `codex exec`; there is no
Kimi-, OMP-, Grok-, or DSH-native analysis backend.
Select this adapter explicitly with `--platform omp`; use `--platform grok` for the Grok adapter.

## Unified Message Model

The `messages` table stores source offsets plus a `part_index` and normalized fields: session and agent IDs,
timestamp, message type, role, native tool name, list preview, and longer search text.
The supported types are `session_meta`, `turn_context`, `user`, `assistant`, `tool_use`,
and `tool_result`.

Kimi Wire mapping is deliberately selective:

- `context.append_message` with `role=user` becomes `user`.
- `content.part` with `part.type=text` becomes `assistant`.
- `tool.call` and `tool.result` become tool messages and retain Kimi's native tool name.
- thinking, `turn.prompt`, usage, config, and other protocol events are skipped.
- `state.json` supplies one synthetic `session_meta`; Kimi has no `turn_context` row.

OMP JSONL mapping is also selective:

- The `session` header becomes `session_meta`; an optional preceding `title` slot supplies its title.
- `session_init` updates task-agent context only. Its duplicated task is not indexed; the
  attributed user message is canonical. An agent definition name such as `scout` is not
  confused with the unique task-run ID stored in `agent_id`.
- User and assistant text becomes `user` and `assistant`; thinking/image blocks are skipped.
- Each assistant `content[].type=toolCall` becomes its own `tool_use`, so parallel calls on one JSONL line remain independently searchable.
- Each `role=toolResult` message becomes `tool_result`; OMP native tool names (`read`, `bash`, `task`, and others) are preserved.
- `part_index` lets multiple normalized events share the same source byte offset while `full` still returns the original JSONL record.

Grok `updates.jsonl` mapping is also selective:

- `summary.json` supplies one synthetic `session_meta` plus project attribution; Grok has
  no `turn_context` row.
- `user_message_chunk` becomes `user`; `agent_message_chunk` becomes `assistant`.
- `tool_call` becomes `tool_use`; the native tool name comes from `_meta["x.ai/tool"].name`
  or the call `title` (for example `run_terminal_command`).
- A `tool_call_update` carrying a `status` becomes `tool_result`, backfilling the tool
  name recorded for its `toolCallId`.
- `agent_thought_chunk`, `plan`, `hook_execution`, `turn_completed`, and status-less
  `tool_call_update` records are skipped.
- The stream is append-only, so incremental indexing uses the shared offset mechanism
  rather than an OMP-style fingerprint. Subagent sessions are ordinary sessions in the
  same tree and need no special handling.

DSH V4 mapping and offsets:

- Header `cwd` alone determines project attribution. Select one latest generation per session; refuse unsupported versions and ambiguous plaintext/compressed copies.
- `user/message` and `assistant/message` contribute text only. Standalone `tool/call` and `tool/result` retain native names and pair through call IDs. Embedded streams, tool-call blocks, and reasoning are skipped.
- Header and `session/title` events become `session_meta`. Times are Unix milliseconds.
- Each physical session keeps its native ID. Exact-ID locate/chronicle include subagent descendants via `parentSession` and `origin=subagent`; forks remain independent. Locate lists root sessions with attached child files.
- Source offsets refer to decompressed JSONL bytes. Unchanged files are skipped by size/mtime; changed files are decoded and the indexed prefix is hashed before appending. A rewritten prefix rebuilds that source, including both FTS indexes. Incomplete JSONL rows wait for the next update.
- Python 3.14+ uses standard-library Zstandard; older Python requires `zstandard`. Changed compressed logs are decoded from the beginning; no frame checkpoint cache is maintained.

## Supported Operations

| Operation | Tool | Description |
|-----------|------|-------------|
| Index | `retrace-index.py` | Build or incrementally refresh project indexes |
| Search | `retrace-search.py` | FTS/hybrid search, filters, context, and full records |
| Locate | `retrace-locate.py` | Find main and subagent source files |
| Analyze | `retrace-analyze.py` | AI analysis through `codex exec` |
| Chronicle | `retrace-chronicle.py` | Extract a time-ordered single-session history |
| Recover | `retrace-recover.py` | Restore file versions from supported histories |

Recover intentionally supports only Codex and Claude histories; like Kimi and OMP,
Grok and DSH sessions are out of scope for recovery.

## Token Budget Control

Use layered output: `stats` for counts, `list` for previews, `detail` for selected rows,
then `full` or `context` only for the relevant message IDs.
