# Fix: relative -d/--project-dir path causes FileNotFoundError in device monitor

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Problem

[redacted-ref].

Running `pio device monitor -d <relative-path>` can crash with a `FileNotFoundError`
when the current platform's monitor filter (e.g. espressif32's exception decoder)
changes the working directory internally.

## Root cause

The `-d/--project-dir` option on `device_monitor_cmd` uses `click.Path(...)` without
`resolve_path=True`, so a relative path stays relative. `device_monitor_cmd` itself calls
`fs.cd(project_dir)` once; when `load_build_metadata()` later calls `fs.cd()` again from
within a monitor filter, the still-relative path gets resolved against the *new* cwd,
duplicating the path segment and producing a non-existent path.

## Fix

One-line change: add `resolve_path=True` to the `click.Path(...)` type for `-d` on
`device_monitor_cmd`, so the path is resolved to an absolute path before any `fs.cd()`
calls happen. Checked all other `-d/--project-dir` definitions in the codebase (12 total)
— this fix is scoped to the one command affected; no shared helper was available to reuse
without touching unrelated commands.

## Testing

- Added `tests/commands/test_device_monitor.py` (3 tests), reusing the existing
  `clirunner`/`validate_cliresult` fixtures from `tests/conftest.py`.
- Confirmed the new regression test fails pre-fix (`FileNotFoundError`) and passes
  post-fix.
- `black --check`, `isort --check`, and `pylint --rcfile=./.pylintrc` all clean (10.00/10).

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
