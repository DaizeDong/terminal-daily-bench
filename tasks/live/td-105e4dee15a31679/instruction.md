# Recognize ROW_FORMAT as a keyword (issue773)

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

## Problem

`ALTER TABLE mytable ROW_FORMAT=Dynamic` parses the table name and the option together as a single identifier:

```python
>>> import [redacted-repo]
>>> [str(t) for t in [redacted-repo].parse("ALTER TABLE mytable ROW_FORMAT=Dynamic")[0].tokens]
['ALTER', ' ', 'TABLE', ' ', 'mytable ROW_FORMAT', '=', 'Dynamic']
#                                ^^^^^^^^^^^^^^^^^^ table name absorbs the option
```

`ROW_FORMAT` was tokenized as a `Name`, so the identifier grouper treated it as an alias of `mytable` (`mytable ROW_FORMAT`).

## Fix

`ENGINE`, `AUTO_INCREMENT` and similar table options are already listed in `KEYWORDS`, which is why `ALTER TABLE mytable ENGINE=InnoDB` parses correctly (the table name is a standalone identifier). This adds `ROW_FORMAT` to `KEYWORDS` for consistent behavior:

```python
>>> [str(t) for t in [redacted-repo].parse("ALTER TABLE mytable ROW_FORMAT=Dynamic")[0].tokens]
['ALTER', ' ', 'TABLE', ' ', 'mytable', ' ', 'ROW_FORMAT', '=', 'Dynamic']
```

## Verification

- Added `test_alter_table_row_format_issue773` to `tests/test_regressions.py`; it fails on `main` (no `ROW_FORMAT` keyword) and passes with this change.
- Full test suite: `488 passed, 2 xfailed, 1 xpassed` (the `xpassed` is pre-existing and identical on `main`); no regressions.
- `ruff check [redacted-repo]/` (the CI lint command) is clean.
- Added a `CHANGELOG` entry.

---

*Disclosure: this change was prepared with the assistance of an AI tool (Claude Code). I reproduced the issue, reviewed and verified the fix and test results, and take responsibility for the contribution and will respond to review feedback personally.*

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
