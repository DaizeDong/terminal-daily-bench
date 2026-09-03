# fix: atomic writes for adapter configs, recall cache, and pre-migration backup ([redacted-ref])

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref] (X2-1 + C1-1 + D1-6). Three non-atomic write sites that could corrupt user data:

- **X2-1** — 6 adapters (`cursor`/`codex`/`gemini`/`kimi`/`hermes`/`openclaw`) wrote the user's **live** editor/CLI config with a bare `write_text`; a crash mid-write truncates it. Factored `atomic_write_text`/`atomic_write_json` into `adapters/base.py` (tmp-in-same-dir + `os.replace`) and routed all 20 write sites through it. (claude/antigravity/chatgpt already did this.)
- **C1-1** — recall cache `set`/`invalidate` wrote a **fixed** `RECALL_CACHE_PATH.with_suffix('.tmp')`; concurrent writers interleaved on that single tmp, leaving the cache as two concatenated JSON docs and silently dropping sibling entries. Routed through `_shared._atomic_write_text` (unique per-pid tmp). Confirmed by the v3 stress harness.
- **D1-6** — the pre-migration backup copied the DB + `-wal` + `-shm` separately (non-atomic); a concurrent writer could tear the WAL pair so a restore failed (`no such table`). Now uses SQLite's **Online Backup API** for a single, internally-consistent snapshot file (restore = one `cp`).

**Tests** (`tests/test_issue_691_atomic_writes.py`): base atomic write + parent-mkdir; no bare `.write_text` remains in the 6 adapters; recall cache writes via the unique tmp + roundtrips + is 0600; the backup is a complete single-file snapshot openable without `-wal`. 269 adapter/recall/backup/storage tests still pass. ruff clean.

BLAST OFF v3.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
