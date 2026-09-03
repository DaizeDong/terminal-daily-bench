# feat: add truncate argument to todb function

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

This PR has the objective of making the truncate step in `todb()` optional, so you can load into an existing table without first deleting its rows.

As @juarezr pointed out on the issue, `todb()` and `appenddb()` already share the internal `_todb()` and only differ by the `truncate` flag, so this just surfaces that flag on `todb()` with a default of `True` to keep the current behavior unchanged. Passing `truncate=False` now appends instead, same as `appenddb()`.

## Changes

1. Added a `truncate` keyword argument to `todb()`, defaulting to `True`.
2. Passed it through to the internal `_todb()` call instead of the previously hard-coded `True`.
3. Updated the `todb()` docstring to describe the new argument and the append case.
4. Added unit tests covering the default, the `truncate=False` passthrough, and an sqlite round trip that keeps existing rows.
5. Documented the change in `docs/changes.rst`.

## Testing

- `.venv/bin/python -m pytest [redacted-repo]/test/io/test_db.py`

Result:

- `12 passed, 2 warnings`

The two warnings are the existing sqlite generator cleanup warnings from `test_fromdb`, they show up on master too.

## Checklist

Use this checklist to ensure the quality of pull requests that include new code and/or make changes to existing code.

* [x] Source Code guidelines:
  * [x] Includes unit tests
  * [ ] New functions have docstrings with examples that can be run with doctest
  * [ ] New functions are included in API docs
  * [x] Docstrings include notes for any changes to API or behavior
  * [x] All changes are documented in docs/changes.rst
* [x] Versioning and history tracking guidelines:
  * [x] Using atomic commits whenever possible
  * [x] Commits are reversible whenever possible
  * [x] There are no incomplete changes in the pull request
  * [x] There is no accidental garbage added to the source code
* [x] Testing guidelines:
  * [x] Tested locally using `tox` / `pytest`
  * [x] Rebased to `master` branch and tested before sending the PR
  * [ ] Automated testing passes (see [CI]([redacted-url]))
  * [ ] Unit test coverage has not decreased (see [Coveralls]([redacted-url]))
* [x] State of these changes is:
  * [ ] Just a proof of concept
  * [ ] Work in progress / Further changes needed
  * [x] Ready to review
  * [ ] Ready to merge

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
