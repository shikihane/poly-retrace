# ADR 001: Attribute Kimi Sessions from state.json

- Status: Accepted
- Date: 2026-07-29

## Context

Kimi Code stores a session under `sessions/<work-directory-bucket>/session_<uuid>` and
records the original working directory in the session's `state.json` as `workDir`.
The outer directory currently has a generated `wd_<label>_<hash>` name. That name is
derived, lossy, and ambiguous: labels can be shortened or sanitized, hashes are not
reversible, and real path components may contain the same separators.

Retrace needs a stable project bucket so `--project` selects the same working directory
across indexing, searching, locating, and chronicle export. A guessed directory can
silently place a session in the wrong project's index.

## Decision

Kimi project attribution must use only `state.json.workDir`, encoded with Retrace's
normal `encode_path` function. `decode_path(..., "kimi")` must likewise recover a path
by matching encoded `workDir` values from state files.

Retrace must not parse or reverse the `wd_` directory name. If `state.json` is missing,
invalid, or has no `workDir`, automatic indexing and project listing skip that session
instead of guessing a project.

## Consequences

- Kimi indexes remain isolated at `<KIMI_CODE_HOME>/projects/<encoded-cwd>/retrace-index.db`.
- Renaming or changing `state.json.workDir` moves the session to the corresponding
  project bucket on the next rebuild.
- Damaged state files make a session temporarily unattributed, but never silently
  misattributed.
- The Wire file remains the source of message events; `state.json` is only the source
  of session metadata and project attribution.

## Alternatives Rejected

- Decode `wd_<label>_<hash>`: rejected because the transformation is not reversible and
  may change between Kimi versions.
- Fall back to the current process directory: rejected because indexing historical
  sessions from another project would silently contaminate the current project index.
