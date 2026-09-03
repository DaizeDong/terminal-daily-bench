# Keep BlockCache and BackgroundBlockCache usable after pickling

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

### Problem

`BlockCache.__getstate__` and `BackgroundBlockCache.__getstate__` used
`self.__dict__` directly and then removed runtime-only attributes from that
mapping. Because it is the live instance dictionary, `pickle.dumps(cache)`
left the original cache unusable.

Subsequent reads raised `AttributeError` for `_fetch_block_cached` in
`BlockCache` and `_fetch_future_lock` in `BackgroundBlockCache`.

### Change

Copy the instance dictionary before removing unpicklable runtime state. This
mirrors `MMapCache.__getstate__` and keeps the original cache intact.

The serialized form remains unchanged in intent: runtime executors, locks,
futures, and in-memory block-cache contents are reconstructed rather than
persisted.

The existing parametrized pickle test now verifies both the original cache
after serialization and the restored cache.

### Validation

On `master`, the regression reproduces both `AttributeError` failures above.

- focused pickle regression: 9 passed
- `[redacted-repo]/tests/test_caches.py`: 157 passed
- `[redacted-repo]/tests`: 576 passed, 91 skipped, 2 xfailed
- targeted pre-commit hooks: passed
- `git diff --check`: passed

The full cross-platform, downstream, s3fs, and gcsfs matrix was not run locally
and is left to GitHub CI.

### AI assistance disclosure

OpenAI Codex assisted with investigation, test design, adversarial validation,
and drafting this change.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
