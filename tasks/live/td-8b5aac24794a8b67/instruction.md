# fix(guard): repair Core sidecar Mach-O headers after manifest rewrite

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- After rewriting the bundled native runtime manifest, strip the stale outer signature, expand Mach-O LINKEDIT to cover the new file length, and sign the Desktop Core sidecar again.
- Keep native manifest rewrite and embedded Mach-O identity verification. Smoke version and bootstrap checks run only after that outer signature is valid.

## Testing
- `python3 -m pytest -q tests/test_desktop_core_alpha_feed_macos_signing.py tests/test_desktop_core_alpha_feed_security.py --tb=short`
- `python3 scripts/ci/code_quality_audit.py --root . --baseline ci/code-quality-baseline.json`

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
