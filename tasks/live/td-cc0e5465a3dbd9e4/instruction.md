# fix(processor): harden multimodal chunks_list merge against reprocessing and absent records (refs [redacted-ref])

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Description

The multimodal `chunks_list` integration exists in both multimodal paths but has two soft spots, duplicated inline in each (see the correction posted on [redacted-ref] — the integration itself works on current main; these are the residual defects):

1. **Blind append**: chunk ids are content-hashed, so reprocessing the same multimodal content produces identical ids and every re-run duplicates them in `chunks_list` (and inflates `chunks_count`). Relevant to retries and to the `force_multimodal_reprocess` flag proposed in [redacted-ref].
2. **Silent no-op when the doc_status record is absent**: the `if current_doc_status:` guard has no else branch and the enclosing `except` only warns, so the multimodal chunks quietly end up missing from `chunks_list` — every consumer that enumerates a document's chunks from the record (deletion, audits, exporters) then orphans them with no trace.

## Related Issues

Refs [redacted-ref] (re-scoped per my comment there). Related: [redacted-ref].

## Changes Made

- `_update_doc_status_with_chunks_type_aware` now merges instead of appending (only ids not already listed are added; counts increment by the newly added ids only) and logs a warning when the doc_status record is missing instead of silently skipping.
- The individual multimodal path delegates to that helper instead of carrying its own inline copy of the same logic.

## Checklist

- [x] Changes tested locally
- [x] Code reviewed
- [ ] Documentation updated (if necessary)
- [x] Unit tests added (if applicable)

## Additional Notes

- Tests: `tests/test_multimodal_chunks_list_merge.py` (4 cases: merge appends and updates count; three re-runs do not duplicate; partial overlap appends only missing ids; absent record warns and writes nothing). Mutation-verified: removing the dedup fails two tests.
- Full suite: 239 passed. Lint: `ruff==0.6.4 check --ignore=E402` and `ruff format` clean on changed files.

🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
