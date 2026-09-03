# Enable Sentry Logging - Opt in Mode

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

<!-- What does this PR change and why? Keep it short - 1-3 sentences. -->
i) Adds Sentry Logging which is optional for users.
ii) Sentry basically logs Release Version, Python Version, Challenge Stats and Infra Failure.
iii) Documentation Updated

## Related issue

<!-- Link the issue this closes, if any. Example: [redacted-ref] -->

Closes #

## Type of change

- [ ] Bug fix
- [ ] New challenge
- [ ] New scenario / story content
- [ ] Documentation (README, GitHub Pages, CONTRIBUTING, etc.)
- [ ] Refactor / tooling / CI
- [x] Other (describe below)

## What changed

<!-- List the main files or areas touched. -->

- New directory added - `services/diagnostics` . This contains the helpers for Sentry.
-  Modification in Base Challenge Files to add the newly added helper for Sentry so that it gets called for every challenge.
- New Screen added to get users' consent on Sentry Opt In

## How to test

<!-- Help reviewers replay your change. For gameplay PRs, include challenge ID and pass/fail paths. -->

1.
2.
3.

**Install tested with:**

- [x] Source (`python app.py`)
- [ ] Docs only (no runtime test needed)

## Screenshots / recordings (optional)
<img width="2384" height="634" alt="image" src="[redacted-url] />


<!-- Terminal capture, in-game screenshot, or short clip for UI/challenge changes. -->

## Checklist

- [ ] I linked a related issue (or explained why none is needed)
- [x] I tested this locally
- [ ] New challenges include `screen.py`, `challenge_text.py`, `validator.py`, and manifests under `scenarios/`
- [ ] Validators use `services/resource_inspector.py` (no direct kubectl shell calls in validators)
- [ ] I did not commit `[redacted-repo]-lab/`, `.venv/`, or other local/generated files
- [x] I updated docs if behavior, paths, or setup changed
- [ ] This is not a security fix (security fixes should use a private advisory per [SECURITY.md](SECURITY.md))

## Notes for reviewers (optional)

<!-- Anything non-obvious: trade-offs, follow-ups, things you were unsure about. -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
