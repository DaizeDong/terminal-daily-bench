# test: bring coverage to 100%

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- adds tests for cli, helpers, molecule, visualization, and remaining graph branches; 58% → 100%
- makes Atom hashable via `eq=False` so `Bond.atoms` and `Bond.__contains__` actually work
- shared `WATER_XYZ` and `water_molecule` fixture moved to `tests/conftest.py`

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
