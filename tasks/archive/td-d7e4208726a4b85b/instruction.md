# Fix custom error on a key [redacted-repo] being lost for wrong keys

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

**Bug:** when a key [redacted-repo] defines a custom `error`, e.g. `[redacted-repo]({Regex(pattern, error="Invalid profile name"): dict})`, and a data key doesn't match it, the key is reported as a wrong key but the custom message is dropped — you only get the generic `Wrong key 'bar' in ...` and the explicit error never reaches you.

**Cause:** in `[redacted-repo].validate`'s dict branch, a key that fails to match any key [redacted-repo] is silently swallowed (`except [redacted-repo]Error: pass`). The later `[redacted-repo]WrongKeyError` is then built only from the surrounding dict [redacted-repo]'s own `error` (usually `None`), so the rejecting key [redacted-repo]'s custom error is gone.

**Fix:** when a rejecting key [redacted-repo] carries a custom `error`, remember it, and surface it in the resulting `[redacted-repo]WrongKeyError`. The default wrong-key message is unchanged when no custom error is set.

**Testing:** added `test_wrong_key_reports_key_[redacted-repo]_error` (covers `Regex` and `And` key [redacted-repo]s, plus the no-custom-error case). Verified it fails before the fix and passes after. Full suite (120 tests) passes; ruff check/format clean; no new mypy errors.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
