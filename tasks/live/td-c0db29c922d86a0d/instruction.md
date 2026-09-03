# feat: complete IMAP support — persistence, Trash detection, undo UX (v0.4.0)

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## What this adds

**IMAP now works end-to-end with zero flags after setup.** Previously each command required `--provider imap --imap-server ... --imap-user ...` every time. Now `[redacted-repo] setup` persists all connection settings and every command reads them automatically.

### Provider persistence
- `setup` writes `[redacted-repo]_PROVIDER`, `[redacted-repo]_IMAP_SERVER/USER/PORT/FOLDER` to `~/.[redacted-repo]/.env`
- New `_resolve_imap_settings()` helper merges CLI flags with persisted settings (CLI always wins)
- `stats`, `quickstart`, `purge`, `undo`, `doctor` all use the resolver — `--provider` defaults to `""` and reads from config

### IMAP Trash folder detection (RFC 6154)
- `_get_trash_folder()` checks `SPECIAL-USE \Trash` attribute in `LIST` response first, then falls back to well-known names (`Trash`, `Deleted Items`, `Deleted Messages`)
- Result cached per connection — no repeated `LIST` round-trips
- Used consistently in `batch_trash`, `batch_untrash`, and `doctor`

### Safety fix: `batch_trash` was permanently deleting on MOVE-unsupported servers
- **Before**: fallback on MOVE failure was `STORE \Deleted + EXPUNGE` on the source folder — permanent delete, no Trash
- **After**: `COPY → Trash + STORE \Deleted + EXPUNGE`; returns `0` if no Trash folder exists — never silently destroys email

### Undo UX polish
- Full restore: `✓ Restored N email(s).`
- Partial: `⚠ Partial restore: N restored · M skipped` + brief IMAP UID explanation
- Zero restored: `✗ Restore failed` + manual Trash check guidance

### Provider abstraction
- `EmailProvider` base: `batch_untrash()` abstract method, `supports()` defaults `False`
- `GmailProvider`: implements both
- `IMAPProvider`: MOVE → COPY+DELETE fallback in `batch_untrash()`

### Test infrastructure
- `_reset_settings` autouse fixture in `conftest.py` — resets `_settings` cache and sets IMAP env vars to defaults between tests so `~/.[redacted-repo]/.env` cannot pollute results
- `test_imap_quickstart.py` — 14 tests: auth failure paths, scan results, capability checks
- `test_imap_undo.py` — batch_untrash unit tests (MOVE/fallback/failure), undo CLI IMAP path, partial restore, unsupported operation, domain-mode undo log fix

## Test plan

- [x] 362 tests pass, 0 failures
- [x] Ruff lint clean
- [x] `[redacted-repo] setup` (IMAP path) writes all 5 settings to `.env`
- [x] `[redacted-repo] stats / purge / undo` work with zero flags after setup
- [x] SPECIAL-USE Trash detection tested via mock LIST responses
- [x] `batch_trash` COPY fallback tested (no permanent delete)
- [x] Partial undo shows restored/skipped counts

## Version bump
`0.3.0 → 0.4.0` — IMAP is now a first-class provider, not an experimental flag.

🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
