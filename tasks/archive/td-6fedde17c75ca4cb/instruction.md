# Fix repeated option values across usage alternatives

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

This fixes the repeated-option case from the issue where matching one usage alternative could mutate the parsed option object shared with another alternative. `_Option.single_match()` now returns a fresh option object for the match, so a failed branch attempt cannot leak value changes back into the shared argv token list.

Validation:
- `uv run --no-project --with pytest python -m pytest tests/test_docopt.py::test_issue_60_repeated_options_across_usage_alternatives tests/test_docopt.py::test_count_multiple_flags -q`
- `uv run --no-project --with pytest python -m pytest -q`
- `uv run --no-project --with ruff ruff check docopt/__init__.py tests/test_docopt.py`
- `git diff --check HEAD~1..HEAD`
- `review-fix-loop` clean

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
