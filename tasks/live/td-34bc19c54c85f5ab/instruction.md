# fix(dashboard): clean up loop-owned dashboard

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

  - treat the dashboard launched by `[redacted-repo] loop` as a loop-owned child service
  - clean up the dashboard on normal loop exit and interruption signals
  - register cleanup immediately after spawning the dashboard process
  - preserve and report the dashboard URL when the initial 8-second readiness probe times out but the process is still starting
  - align loop/DAG completion messages and README documentation with the actual lifecycle
  - add regression coverage for late dashboard startup and failed startup

  The dashboard started by `[redacted-repo] dashboard <project>` remains independently managed.

  ## Tests

  - `PYTHONPATH=src python -m pytest tests/test_dashboard_process.py -q`
  - `python -m py_compile src/[redacted-repo]/commands/loop/services.py src/[redacted-repo]/commands/loop/command.py src/[redacted-repo]/commands/dag/command.py`
  - `git diff --check`

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
