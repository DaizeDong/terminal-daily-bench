# fix: utf-8 reads, cost-only csv/jsonl rows, cross-file copilot dedup

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Three store correctness fixes (separate commits):

- **UTF-8 reads**: every data-file `open()` relied on the locale encoding, so native Windows (cp1252) read transcripts as mojibake and split non-ASCII cwds into separate projects. `encoding="utf-8"` is now pinned on every user-data read (`_read_text` feeding the JSONL backends, csv/jsonl request logs, pi, openclaw, vscode, the availability probe), keeping existing `errors=` handling.
- **Cost-only rows**: a CSV/JSONL row logging only `cost_usd`/credits with no token counts was dropped by the empty-row check — yet `_probe_records_cost` counted it, so the source claimed `records_cost=True` while showing $0. Rows with positive cost are now ingested; genuinely empty rows stay skipped.
- **Copilot cross-file dedup**: the trace context, coverage sets, and seen keys were local to `_parse_file`, but OTEL exporters write spans and logs to different files — one call logged as a chat span in file A and an inference log in file B counted twice. Candidates are now collected across all files, then deduped and emitted at `_parse` scope, preserving the existing record-shape priority.

Tested: 3 new tests (cost-only csv row, cost-only jsonl line, span+log split across two files → one row); suite 307/307, ruff clean.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
