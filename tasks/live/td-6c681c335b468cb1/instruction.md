# Release [redacted-repo] 0.2.0

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- make completion-only masking token-boundary safe and expose it as a public API
- harden configuration, batching, distributed preparation, and failure handling
- add dry-run validation, Python 3.10–3.13 CI, release provenance, and project governance files
- rerun the public GSM8K comparison with controlled effective batches and publish machine-readable results

## Validation

- 59 tests pass
- Ruff check and format check pass
- wheel and sdist pass twine check
- wheel installs and runs in a clean Python 3.13 environment
- full GSM8K run completed on one RTX 4080

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
