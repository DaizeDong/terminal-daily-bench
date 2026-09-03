# 0.8.0.5: mimic code-column patterns + decimal fidelity

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## What

- Profiler detects alphanumeric identifier columns (Ticket, Cabin, SKU) and reproduces them as weighted character-class patterns instead of prose text. Same shapes, zero verbatim leak.
- Fixed `_infer_decimals` (searched for a literal backslash-dot, never matched), so mimicked floats keep their decimal places.
- Profiled numeric columns opt out of semantic quantization: the fitted distribution is ground truth.
- `pattern` accepts weighted lists, `[a-z]` expands, both reachable from dict schemas.

## Tests

773 passed (12 new in `test_mimic_profiler.py`, mimic's first dedicated coverage).

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
