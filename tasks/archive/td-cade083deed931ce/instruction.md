# Add opt-in planner metaphor mode

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- add `--planner-metaphor` and `ExpConfig.planner_metaphor`, defaulting to false
- add a diagram-only Planner prompt supplement that asks for a compact visual metaphor before the normal detailed description
- keep the default Planner prompt unchanged and ignore the metaphor flag for plot tasks

[redacted-ref].

## Validation
- PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/jeff/Codex_projects/[redacted-repo]/.venv/bin/python -m pytest -q -p no:cacheprovider tests
- git diff origin/main --check

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
