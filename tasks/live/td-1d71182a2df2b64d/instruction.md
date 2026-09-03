# Fix IndexError in parse_log_seaborn on bare status lines

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## What's broken
`parse_log_seaborn` (used to grade `mwaskom/seaborn` instances) indexes `line.split()[1]` / `parts[1]` without a length check. A log line that is just a bare status word — e.g. `PASSED` or `FAILED` on its own line, common when test output is interleaved or captured stdout contains the word — raises `IndexError`, which propagates out of `get_logs_eval` (`grading.py`) and crashes grading for that instance.
parse_log_seaborn("tests/test_x.py::test_a PASSED\nPASSED\n") # IndexError

## Why it happens
Missing length guard before positional indexing of `line.split()`, inconsistent with the sibling `parse_log_pytest`, which guards this exact case with `if len(test_case) <= 1: continue`.
## Fix
Compute `parts = line.split()` once and `continue` when `len(parts) < 2`, matching the other pytest-family parsers. Valid-line parsing is unchanged.
## Test
Added `tests/test_log_parsers_python.py` feeding bare `PASSED`/`FAILED` lines (crashes before, parses cleanly after); valid output byte-identical. Mirrors the existing interleaved-logs test for the Java parser.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
