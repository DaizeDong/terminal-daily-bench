# Fail with a clear error when device monitor stdin is not a TTY

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

`pio device monitor` crashes with a raw termios traceback (`Inappropriate ioctl for device`) whenever stdin is piped or redirected instead of a real terminal, e.g. `echo "" | pio device monitor`. This happens because pyserial's `Miniterm.Console` calls `termios.tcgetattr()` on stdin during `Terminal` construction, which only works when stdin is an actual TTY.

This PR detects non-TTY stdin before constructing the `Terminal` and raises a clear `UserSideException` instead, pointing users toward talking to the serial port directly (e.g. with pyserial) if they're trying to automate device I/O from a script, which was the reporter's use case.

[redacted-ref]

## Changes

- `[redacted-repo]/device/monitor/terminal.py`: check `sys.stdin.isatty()` at the top of `new_terminal()` before any serial/terminal setup happens
- `tests/commands/test_device_monitor.py`: regression test that mocks a non-TTY stdin and asserts the clear error is raised

## Test plan

- [x] `pytest tests/commands/test_device_monitor.py -v` — all 4 tests pass (3 existing + 1 new)
- [x] `make lint` (pylint) — 10.00/10 on both changed files
- [x] `black --check` / `isort --check-only` — clean, no changes needed
- [x] `codespell` — clean

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
