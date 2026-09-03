# feat: allow disabling update checks

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- add `BH_UPDATE_CHECK=0` to disable the CLI update banner before cache or network access
- preserve existing standalone behavior when the variable is unset
- cover accepted false values and the default-enabled path

## Why

Long-lived orchestrators can run Browser Harness in isolated runtime directories. Their lifecycle probes and cleanup commands should not make an unrelated PyPI request or wait on its timeout. This gives trusted callers a narrow opt-out without changing normal CLI behavior.

## Validation

- `uv run --with pytest pytest -q` (145 passed)
- `python3 -m compileall -q src tests`
- `git diff --check`

This is intentionally separate from [redacted-ref] and is not merged.


<!-- This is an auto-generated description by cubic. -->
## Summary by cubic
Allow disabling update banner update checks via the BH_UPDATE_CHECK environment variable to avoid network/cache access in CI or hermetic environments. Previously, print_update_banner always read cache and could trigger a network call; now it can be skipped.

- When BH_UPDATE_CHECK is set to 0/false/no/off (case-insensitive, trims whitespace), print_update_banner returns immediately without reading the cache or calling check_for_update.
- Default remains enabled; behavior is unchanged when the variable is unset.
- Tests cover disabled behavior (no cache/network) and default behavior (still performs the check).
- To disable in CI: set BH_UPDATE_CHECK=0.

<sup>Written for commit [redacted-sha]. Summary will update on new commits.</sup>

<a href="[redacted-url] target="_blank" rel="noopener noreferrer" data-no-image-dialog="true"><picture><source media="(prefers-color-scheme: dark)" srcset="[redacted-url]><source media="(prefers-color-scheme: light)" srcset="[redacted-url]><img alt="Review in cubic" src="[redacted-url]></picture></a>

<!-- End of auto-generated description by cubic. -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
