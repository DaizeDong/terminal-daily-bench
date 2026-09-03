# fix: avoid pipeline option cache key collisions

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Fix pipeline cache collisions for concrete and pass-through option values.

Build cache keys from public typed configuration without changing Pydantic serialization or inspecting private state. Converter and extractor now share the same cache-key implementation.

Adds focused coverage for runtime types, mapping order, opaque values, and collision-prone scalars.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
