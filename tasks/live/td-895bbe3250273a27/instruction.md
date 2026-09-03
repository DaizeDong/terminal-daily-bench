# fix: serialize local ASR model access

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- guard the lazy SenseVoice model initialization so concurrent first requests build one shared model
- serialize `AutoModel.generate()` calls on that shared model
- add deterministic concurrency regressions for both behaviors

## Root cause

Each WebSocket handler sends blocking ASR work to the default thread pool, while
all handlers share the module-level `_sensevoice_model`. The previous GIL-based
assumption did not protect the check-then-initialize sequence, so concurrent
first requests could construct multiple models.

The shared FunASR `AutoModel` is also stateful during `generate()`: it resets and
updates runtime configuration dictionaries for the model and VAD pipeline.
Allowing two executor threads to enter the same instance concurrently can race
those mutations and create unnecessary GPU memory pressure.

Both locks are acquired inside executor workers, so the aiohttp event loop
remains non-blocking. Concurrent requests queue only at the shared model
boundary.

## Validation

- `python -m unittest discover -s tests -p "test_*.py" -v`
- `python -m compileall -q server/asr_server.py tests/test_asr_server.py`
- `git diff --check`

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
