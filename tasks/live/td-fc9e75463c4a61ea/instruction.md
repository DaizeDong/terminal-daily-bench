# Create missing request-cache parent directories

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- recursively create the configured request-cache directory before saving
- accept an already existing cache directory without a check-then-create race
- add regression coverage for saving and loading through a nested path with missing parents

## Testing

```text
PYTHONPATH=/tmp/lm-eval-test-deps:/tmp python3 -m pytest tests/test_cache.py -q
6 passed

PRE_COMMIT_HOME=/tmp/lm-eval-pre-commit pre-commit run --files lm_eval/caching/cache.py tests/test_cache.py
All hooks passed
```

[redacted-ref]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
