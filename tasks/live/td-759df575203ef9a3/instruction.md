# ci(bench): wire bench-check into all-tests poe sequence

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Checklist

- [x] I've formatted the new code by running `uv run poe format` before committing.
- [x] I've added tests for new code.
- [x] I've added docstrings for the new code.

## Description

`bench-check` (`asv check`) existed as a standalone poe task but wasn't wired into `all-tests`, because it originally couldn't be — `benchmarks/` and `asv-constraints.txt` hadn't yet landed. That precondition has been satisfied for months now. Wires `bench-check` into the `all-tests` sequence (`["lint", "docstrings", "bench-check", "test"]`, matching the original benchmarking-infra plan's spec) and updates `benchmarks/README.md`'s now-stale "Notes on bench-check" section.

Addresses [redacted-ref].

## Test plan

- `uv run pytest tests/test_poe_tasks.py` — 2 passed
- `pyproject.toml`'s `all-tests` sequence verified by inspection to include `bench-check` in the correct position
- (`asv check` itself can't build an env in this sandbox — a pre-existing, unrelated limitation noted in the original issue's own risk section)
- `uv run poe lint` — clean

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
