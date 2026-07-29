# Architecture Reference

## Overview

Retrace indexes Codex, Claude Code, and Kimi Code session history into separate
per-platform, per-project SQLite databases. Search uses FTS5 with BM25 ranking and a
selective trigram index for mixed Chinese, code, path, and log queries.

## Platform Storage

| Platform | Source sessions | Project index |
|----------|-----------------|---------------|
| Codex | `~/.codex/sessions/**/*.jsonl`, `~/.codex/archived_sessions/*.jsonl` | `~/.codex/projects/<encoded-cwd>/retrace-index.db` |
| Claude Code | `~/.claude/projects/<encoded-cwd>/**/*.jsonl` | `~/.claude/projects/<encoded-cwd>/retrace-index.db` |
| Kimi Code | `~/.kimi-code/sessions/*/session_*/agents/*/wire.jsonl` | `~/.kimi-code/projects/<encoded-cwd>/retrace-index.db` |

`CODEX_HOME`, `CLAUDE_HOME`, and `KIMI_CODE_HOME` override the corresponding defaults.
Indexes from different platforms must not share a project directory.

Kimi's project bucket is derived only from `state.json.workDir`. Retrace does not parse
the generated `wd_` directory name. See
[ADR 001](./adr-001-kimi-project-attribution.md).

## Platform Boundary

- `platforms/common.py` defines the shared platform data model.
- `platforms/codex.py` and `platforms/claude.py` own their session traversal.
- `platforms/kimi.py` owns Kimi session traversal, state lookup, Wire normalization,
  session IDs, agent IDs, and epoch-millisecond timestamps.
- `retrace_paths.py` is the compatibility facade used by runtime scripts.

The default platform is Codex. Index, search, locate, and chronicle accept Kimi. Analyze
still shells out through `codex exec` and has no Kimi-native backend.

## Unified Message Model

The `messages` table stores source offsets plus normalized fields: session and agent IDs,
timestamp, message type, role, native tool name, list preview, and longer search text.
The supported types are `session_meta`, `turn_context`, `user`, `assistant`, `tool_use`,
and `tool_result`.

Kimi Wire mapping is deliberately selective:

- `context.append_message` with `role=user` becomes `user`.
- `content.part` with `part.type=text` becomes `assistant`.
- `tool.call` and `tool.result` become tool messages and retain Kimi's native tool name.
- thinking, `turn.prompt`, usage, config, and other protocol events are skipped.
- `state.json` supplies one synthetic `session_meta`; Kimi has no `turn_context` row.

## Supported Operations

| Operation | Tool | Description |
|-----------|------|-------------|
| Index | `retrace-index.py` | Build or incrementally refresh project indexes |
| Search | `retrace-search.py` | FTS/hybrid search, filters, context, and full records |
| Locate | `retrace-locate.py` | Find main and subagent source files |
| Analyze | `retrace-analyze.py` | AI analysis through `codex exec` |
| Chronicle | `retrace-chronicle.py` | Extract a time-ordered single-session history |
| Recover | `retrace-recover.py` | Restore file versions from supported histories |

## Token Budget Control

Use layered output: `stats` for counts, `list` for previews, `detail` for selected rows,
then `full` or `context` only for the relevant message IDs.
