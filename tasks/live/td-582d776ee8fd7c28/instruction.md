# fix: build_summaries uses [redacted-ref] SAVEPOINT transaction hygiene ([redacted-ref])

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref] (D1-4). **Completes the v2 [redacted-ref] fix.**

[redacted-ref] wrapped consolidation writes in the `_consolidation_write` SAVEPOINT helper (no commit of the caller's txn, no `isolation_level` mutation) — but applied it to `detect_contradictions` and `build_structured_facts` and **missed `build_summaries`**, which still did `if conn.in_transaction: conn.commit()` (committing the **caller's** open transaction — the leaked-txn root cause behind the v2 live-lock incident) plus an `isolation_level=None` mutation on the shared connection.

`build_summaries` now wraps its `DELETE FROM summaries` + bulk insert in `_consolidation_write(conn, "summaries")`, identical to the other two consolidation writers.

**Tests** (`tests/test_issue_692_build_summaries_txn.py`): it uses the SAVEPOINT helper; a caller's uncommitted write survives `build_summaries` and is still rollback-able (proving it wasn't committed); `isolation_level` is unchanged. 114 consolidation/[redacted-ref] tests still pass. ruff clean.

This is the last of the 3 incomplete v2 fixes from the v3 validation (the other two — [redacted-ref]→[redacted-ref], [redacted-ref]→[redacted-ref] — already landed).

BLAST OFF v3.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
