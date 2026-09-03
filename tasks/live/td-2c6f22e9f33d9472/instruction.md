# Add Dreamer integration test for Pendulum-v1 and CI wiring

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- **Dreamer integration test**: Creates a Dreamer agent on Pendulum-v1 (gym backend), runs ~100 env steps, verifies no crash. Marked with `@pytest.mark.integration`.
- **CI wiring**: New `integration` job in `test.yml` runs only on push to `main`. Executes `pytest -m integration` with a 120s timeout.
- **CI badge**: Added to README so the test status is visible at a glance.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
