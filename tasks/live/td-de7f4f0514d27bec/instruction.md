# feat: --add-fillers / --remove-fillers to tweak the default word list

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## What

Adds two additive flags for shaping pass-1's filler word list, plus plugin/skill and doc updates so the [redacted-repo] plugin reaches for them.

Today `--fillers` **replaces** the built-in set entirely, so adding one word like `basically` means re-typing the whole list (and silently dropping a stem if you forget one). The new flags compose with the defaults:

```
final = (--fillers or DEFAULT) ∪ --add-fillers − --remove-fillers
```

- `--add-fillers "basically,like"` — keep the defaults, union words on top (the common case)
- `--remove-fillers "ah"` — keep the defaults, drop one that over-matches your voice
- Removal is applied last, so it wins over additions det[redacted-repo]inistically.

Custom words match verbatim only — automatic elongation (`ummmm` → `um`) still applies to built-in stems only.

## Changes

- `src/[redacted-repo]/cli.py` — two new args + a testable `_resolve_filler_set()` helper
- `tests/test_cli.py` — parametrized composition tests (add/remove/precedence/no-ops) + parser-level tests
- **Plugin skills** — `skills/[redacted-repo]` and `skills/[redacted-repo]-tune` now steer the assistant to `--add-fillers`/`--remove-fillers` for word-list changes instead of `--fillers`
- Docs: README flag table, `recipes.md`, `usage.md` cheat-sheet, `troubleshooting.md`, `detection.md` (pass-1 composition), `AGENTS.md`, and a CHANGELOG `[Unreleased]` entry

## Verification

- Full non-slow suite: **178 passed**
- `[redacted-repo] --help` shows both flags; `plugin.json` validates

🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
