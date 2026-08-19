# Expand ~ in DirectoriesCompleter ([redacted-ref])

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

`DirectoriesCompleter` (and its base `_FilteredFilesCompleter`) yields no
completions for a tilde-prefixed path such as `~/`, so `~/<TAB>` shows nothing
even though the home directory has subdirectories. Reported in [redacted-ref].

The cause is in `_FilteredFilesCompleter.__call__`: `os.path.dirname("~/")`
returns `"~"`, and `os.listdir("~")` raises `FileNotFoundError` (there is no
literal `~` directory). That exception is swallowed by the surrounding
`except Exception: return`, so the completer silently returns an empty iterator.

## Fix

Expand the prefix with `os.path.expanduser` before splitting and listing, so
the filesystem operations run against the real home directory. This mirrors the
behavior of the bash-backed `FilesCompleter`, whose `compgen` already expands
`~`. Non-tilde prefixes are unaffected (`expanduser` is a no-op for them).

```python
expanded_prefix = os.path.expanduser(prefix)
target_dir = os.path.dirname(expanded_prefix)
...
incomplete_part = os.path.basename(expanded_prefix)
```

## Tests

Added `test_directory_completion_with_tilde` (regression test for [redacted-ref]). It
points `HOME`/`USERPROFILE` at a temp directory so the test is hermetic, then
asserts that `~/`, `~/ab`, and `~/abc/` complete correctly. The test fails on
the unpatched code (empty result) and passes with the fix.

- `python -m unittest test.test.Test[redacted-repo]` — 36 passed
- `ruff check [redacted-repo] test/test.py` — clean
- `ruff format --check [redacted-repo]/completers.py test/test.py` — clean
- `mypy --install-types --non-interactive [redacted-repo]` — clean

Disclosure: prepared with AI assistance; reviewed and verified locally.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
