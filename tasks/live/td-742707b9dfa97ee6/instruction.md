# fix: preserve unavailable process metrics as null

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Changes

- Return `None` when CPU or RSS collection fails.
- Keep total RAM unknown when initialization fails.
- Preserve unknown CUDA availability and GPU count until CUDA can be safely probed.
- Update the Process sample schema to allow these nullable values.
- Add focused sampler tests.

## Scope

This PR changes upstream collection and wire semantics only. SQLite already preserves these values as `NULL`.

Legacy terminal, dashboard, and diagnosis handling of unavailable values is intentionally out of scope and will be addressed separately.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
