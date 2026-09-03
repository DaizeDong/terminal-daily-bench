# pytest_plugin(fix[pytest_ignore_collect]): abstain with None

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

`[redacted-repo].pytest_plugin.pytest_ignore_collect` returned a concrete `False` in
its fall-through instead of `None`. `pytest_ignore_collect` is a
[`firstresult=True`]([redacted-url])
hook, so the first implementation to return a non-`None` value wins and
short-circuits the rest. [redacted-repo]'s implementation runs first, so its `False`
silently suppressed every other implementation — gp-libs'
[`_build` skip]([redacted-url])
and pytest's own
[`__pycache__`/`norecursedirs`/`collect_ignore` handling]([redacted-url]).

The user-visible symptom: after building the docs, the suite aborts during
collection on the generated Sphinx output, whose copied sources have relative
`{include}` targets that don't resolve from `docs/_build/`:

```
ERROR docs/_build/html/history.md - docutils.utils.SystemMessage: Directive "include": file not found: '.../docs/_build/html/../CHANGES'
!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!
```

Full root-cause writeup in [redacted-ref].

## Fix

Return `None` (abstain) from every non-matching branch so the `firstresult`
chain continues to gp-libs and pytest's builtin. The hook still returns `True`
only to skip tests whose VCS binary is missing. The return annotation widens
to `bool | None` accordingly.

## Testing

- `uv run pytest` — 660 passed, 1 skipped; collection no longer aborts with
  stale `docs/_build/` output on disk.
- Three added regression tests in `tests/test_pytest_plugin.py` cover: abstain
  (`None`) on a non-VCS path, ignore (`True`) when a VCS binary is missing, and
  abstain when the binary is present.
- `uv run ruff check` and `uv run mypy` clean.

[redacted-ref]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
