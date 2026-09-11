# ADR 002: Attribute Grok Sessions from summary.json

- Status: Accepted
- Date: 2026-08-01

## Context

The xAI Grok CLI (the official Rust CLI, not the community superagent-ai/grok-cli)
stores a session under `sessions/<group>/<session-id-uuidv7>/` with an append-only
`updates.jsonl` ACP event stream and a `summary.json` metadata file next to it.
The group directory name is the session's working directory URL-encoded
(percent-encoding), unless the encoded name would exceed 255 bytes — in that case
the CLI writes a lossy `slug-<hash>` directory name and stores the original path in
a `.cwd` file inside the group directory.

Retrace needs a stable project bucket so `--project` selects the same working
directory across indexing, searching, locating, and chronicle export. The group
directory name alone is ambiguous: percent-encoding is reversible only when the
name was not slugged, and the slug+hash form is not reversible at all.

## Decision

Grok project attribution must use only the session's `summary.json` `info.cwd`,
encoded with Retrace's normal `encode_path` function. `decode_path(..., "grok")`
must likewise recover a path by matching encoded `info.cwd` values from summary
files.

Two fallbacks exist, in order, and only when `summary.json` is missing, invalid,
or has no `info.cwd`:

1. URL-decode the group directory name. Grok's encoding is percent-encoding
   (`X:\Work\grok-project` -> `X%3A%5CWork%5Cgrok-project`), not the Codex-style
   `-` replacement Retrace uses for its own buckets.
2. Read the `.cwd` file in the group directory, which holds the original path
   when the CLI had to slug the directory name.

Retrace must not mix the two encodings: `encode_path`/`decode_path` govern
Retrace's own project buckets, while percent-decoding and `.cwd` only interpret
Grok's session tree. If all three sources fail, the session is left unattributed
instead of being guessed into a project.

## Consequences

- Grok indexes remain isolated at `<GROK_HOME>/projects/<encoded-cwd>/retrace-index.db`,
  where `<encoded-cwd>` follows Retrace's normal encoding.
- Renaming or editing `summary.json` `info.cwd` moves the session to the
  corresponding project bucket on the next rebuild.
- Damaged summary files fall back to the group directory name or `.cwd`; if all
  fail, the session is temporarily unattributed, but never silently
  misattributed.
- The `updates.jsonl` file remains the source of message events; `summary.json`
  is only the source of session metadata and project attribution.
- `chat_history.jsonl` next to `updates.jsonl` is never indexed.

## Alternatives Rejected

- Treat the URL-decoded group directory name as authoritative: rejected because
  long paths collapse into `slug-<hash>` names that cannot be reversed, and
  `summary.json` `info.cwd` is always the canonical record when present.
- Reuse Codex-style `-` decoding on the group directory name: rejected because
  Grok uses percent-encoding, and applying the wrong decoder corrupts real path
  components.
- Fall back to the current process directory: rejected because indexing
  historical sessions from another project would silently contaminate the
  current project index.
