# fix(pipeline): set_parallelism now enables dependency-layer parallel execution ([redacted-ref])

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

[redacted-ref].

`PipelineBuilder.set_parallelism()` accepted a value and stored it in the pipeline config, but the execution engine never read it — steps always ran strictly sequentially. This PR wires the config through the full stack (builder → serializer → engine) and adds dependency-layer parallel execution.

## Root cause

- `set_parallelism()` validated and stored `parallelism` in `config`, but `ExecutionEngine._execute_steps()` had no parallel code path.
- `parallelism` was also lost across a serialize/deserialize round trip (nested `config` key was never promoted to the top-level dict that `build_pipeline()` reads).

## Changes

### `[redacted-repo]/pipeline/pipeline_builder.py`
- `PipelineStep` gains an opt-in `parallel_safe: bool = False` field; `add_step()` pops it from kwargs so it never leaks into handler config.
- `set_parallelism()` validates input (bool / positive int, `ValidationError` otherwise).
- `build_pipeline()`, `PipelineBuilder.serialize()`, and `serialize_pipeline()` round-trip `parallel_safe`.
- `deserialize_pipeline()` promotes the nested `config` key to the top level so `parallelism` survives a round trip.

### `[redacted-repo]/pipeline/execution_engine.py`
- `_execute_steps()` now groups steps into dependency layers (declaration order preserved within each layer).
- A layer runs in parallel only when ALL of: >1 step, dict-typed input, every step `parallel_safe`, no step in `delta_mode`. Otherwise the layer falls back to sequential execution.
- Parallel execution: each step's input is deep-copied for isolation; bounded via `ThreadPoolExecutor(max_workers=min(config parallelism, max_workers))`; retries / `StepStatus` / result / error / progress reporting are shared with the sequential path.
- On step failure, pending futures are cancelled and the error propagates so downstream layers never run.
- Layer results are merged back in declaration order; conflicting values for the same key raise `ProcessingError`.

### `docs/guides/pipeline.md`
- Documented effective parallelism cap, `parallel_safe` opt-in, fallback semantics, dict contract, isolation, merge order and conflict behavior.

## Design notes

- Parallelism is opt-in per step (`parallel_safe`) because handlers that share mutable state or rely on strict ordering are unsafe to run concurrently.
- `ParallelismManager.execute_pipeline_steps_parallel()` is intentionally NOT used; the engine implements its own bounded layer scheduler so retry/status semantics stay identical between sequential and parallel paths.

## Tests

- New `tests/pipeline/test_pipeline_parallel.py`: 22 tests, all passing.
- Full regression: `tests/pipeline` 61 passed, `tests/core` 19 passed, `tests/conflicts` 19 passed.
- Note: `tests/test_pipeline_orchestration.py` has 14 pre-existing failures on unmodified `main` (stale chained-API tests, e.g. `PipelineStep.build()`); verified via `git stash` baseline comparison that these are unrelated to this PR.

[redacted-ref]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
