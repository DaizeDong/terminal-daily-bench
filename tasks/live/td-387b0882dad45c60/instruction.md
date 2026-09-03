# fix(guard): accept Linux desktop terminal enrollment

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- accept genuine user-owned desktop terminal sessions when Linux does not record them in `utmp`
- preserve remote-session rejection, explicit typed confirmation, and approval-factor enforcement

## Testing
- `uv run --frozen pytest tests/test_guard_extension_control_proof.py tests/test_guard_extension_control_authority.py -q`
- `uv run --frozen ruff check src/codex_plugin_scanner/guard/runtime/extension_control_proof.py tests/test_guard_extension_control_proof.py`
- interactive PTY enrollment proof through the approval-factor boundary


<!-- This is an auto-generated comment: release notes by coderabbit.ai -->

## Summary by CodeRabbit

* **Bug Fixes**
  * Improved local terminal detection for desktop PTYs without matching login records.
  * Terminal confirmation now correctly identifies the terminal when standard input is a TTY.
  * Avoids incorrectly rejecting valid local terminals when login information is unavailable.

<!-- end of auto-generated comment: release notes by coderabbit.ai -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
