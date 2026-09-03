# Release 0.4.1 housekeeping

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

This release branch integrates the three reviewed housekeeping PRs, in order, and adds a patch version bump to `0.4.1`.

Included branches:

1. [redacted-ref] / `housekeeping/runtime-regressions` — fixes SpecAugment dtype/mask-value handling, removes unintended Energy debug output, and adds regression coverage.
2. [redacted-ref] / `housekeeping/packaging-metadata` — refreshes packaging metadata, dependency bounds, build metadata, MANIFEST, and release scripts.
3. [redacted-ref] / `housekeeping/ci-docs-refresh` — refreshes GitHub Actions, tox/docs config, README/docs examples, and release notes.
4. `Bump version to 0.4.1` — updates `[redacted-repo].__version__` and adds the 0.4.1 release note.

## Verification

Local integration verification on `release/0.4.1`:

- `python -m pytest` → 553 passed, 9 xfailed
- `python -m build` → built sdist/wheel for 0.4.1
- `twine check dist/*` → passed
- `sphinx -W --keep-going -b html docs /tmp/[redacted-repo]-release-docs-build` → passed
- Workflow YAML parsed successfully

## Notes

The topic PRs remain useful as review units, but this PR is the intended single merge path into `master` for the 0.4.1 release.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
