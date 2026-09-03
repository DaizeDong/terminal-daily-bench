# fix: consistent provider resolution — Gmail mode fully isolates IMAP state

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- Fixes two bugs in `_resolve_imap_settings` that caused inconsistent provider behavior
- Gmail mode now **hard-isolates** IMAP state: stale settings can never trigger an IMAP password prompt
- 14 new tests covering all provider resolution scenarios

## Root cause

### Bug 1: Broken fallback to "gmail"
```python
# Before — "gmail" only fired when settings failed to load entirely
resolved_provider = provider or (s.provider if s else "gmail")

# After — "gmail" is the default whenever provider is empty, regardless of settings load
resolved_provider = provider or (s.provider if s else "") or "gmail"
```
If `[redacted-repo]_PROVIDER` was missing from `.env` (pre-v0.3.0 installs), settings loaded successfully but `s.provider` was `""`. The old code returned `""` as the provider. The new code falls through to `"gmail"`.

### Bug 2: No IMAP isolation for Gmail mode
`_resolve_imap_settings` returned stale IMAP values (server, user, port, folder) even when the resolved provider was Gmail. If `[redacted-repo]_IMAP_USER` was non-empty from a previous IMAP setup, it would be returned as `imap_user`, which could satisfy the prompt guard `if provider == "imap" and imap_user and not imap_password` on the wrong side.

**Fix:** When `resolved_provider != "imap"`, return zeroed IMAP settings immediately — no stale config can ever bleed through.

## Test plan
- [x] 376 tests pass (14 new)
- [x] `TestGmailIsolation::test_stale_imap_user_zeroed_for_gmail` — core regression test
- [x] `TestProviderFallback::test_empty_cli_and_empty_settings_returns_gmail` — fallback fix
- [x] `TestProviderSwitching` — switching in both directions works cleanly

🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
