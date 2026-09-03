# fix(ci): validate release contracts for README changes

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Scope

Scope boundary: Align the release consistency contract with the README structure introduced by [redacted-ref], and route root `README*.md` changes through the Ubuntu `release-packaging` suite.

Non-goals: No README content changes, product/runtime changes, release artifact changes, Windows/full-matrix expansion for future README-only pull requests, or changes from [redacted-ref].

## Branch

Base branch: main

Target exception: N/A

## Issue

Linked issue: None

If None, reason: This repairs a main-branch test and CI-routing inconsistency exposed after docs-only [redacted-ref] removed stale What's New prose.

## Release Note

Release note: NONE | Test and CI routing correction only; no user-visible runtime behavior changes.

## Tests

Ruff: `uv run ruff check .github/scripts/plan_ci.py tests/test_ci/test_plan_ci.py tests/test_release_consistency.py`

Pytest: 359 passed, 2 skipped across the release-packaging job tests plus CI planner, attestation, and workflow contracts. Focused post-review rerun: 168 passed.

Build: N/A; no production or package source changed.

Regression tests: added

Notes: The stale prose assertions are replaced with exact current-tag desktop and wheel URL contracts. Six localized READMEs must point to `CHANGELOG.md` and `docs/releases/`. Root README changes select `readme-locale`, `release-packaging`, and `workflow-lint` only; Python, Windows, and Desktop matrices remain empty. The release suite digest now includes root `README*.md` content.

The default test path remains offline, deterministic, credential-free, and safe for forks.

## Maintainer Live Check

Maintainer live check: no

Surface: release

Maintainer-only note: No credentialed check is needed because the change only validates repository text and deterministic CI planning.

## Safety

No secrets, local-only artifacts, private prompts/transcripts, channel identifiers, AI session artifacts, non-public fixtures, or `tests/_private/` contents are included.

## Third-Party Origin

Third-party origin: none

Details if non-none: N/A

## Documentation Changes

- [x] No documentation content changed.
- [x] Added assertions reference existing `CHANGELOG.md` and `docs/releases/` repository paths.
- [x] No examples, secrets, local paths, or private transcripts were added.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
