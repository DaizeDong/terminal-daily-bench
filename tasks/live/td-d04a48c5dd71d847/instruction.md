# [FEATURE] Add CrossMAE as a method

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

Adds [CrossMAE]([redacted-url]) as a native `stable_pretraining.methods` method.

This includes:
- `CrossMAE` and `CrossMAEDecoder`
- Cross-attention decoder support built on the existing `MAEDecoder` abstraction
- CrossMAE-specific feature-map mixing and `kept_mask_ratio` reconstruction behavior
- Top-level and `stable_pretraining.methods` exports
- `METHODS.md` catalog entry
- Focused CrossMAE unit tests plus generic method smoke coverage

No linked issue.

## Testing

Local unit tests pass:

- `uv run pytest stable_pretraining/tests -m unit`
  - `2088 passed, 5 skipped, 101 deselected`

## Checklist

- [x] I have read the [Contributing]([redacted-url]) document.
- [x] The documentation is up-to-date with the changes I made (check build artifacts).
- [x] All tests passed, and additional code has been covered with new tests.
- [ ] I have added the PR to the [RELEASES.rst]([redacted-url]) file.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
