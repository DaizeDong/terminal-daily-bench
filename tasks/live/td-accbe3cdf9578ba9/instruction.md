# refactor(service): split service by API domain

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- split authorization, thermostat, group, hierarchy, demand, and report operations into domain service components
- preserve the `EcobeeService` compatibility facade, public method signatures, return behavior, and exception behavior
- define explicit package exports, replace wildcard imports in documentation and live integration code, and add migration guidance
- archive the OpenSpec change and sync the domain-oriented client specification

## Testing
- `.venv/bin/pytest -q` (37 passed; 63.22% coverage)
- `.venv/bin/ruff check [redacted-repo] tests`
- `.venv/bin/ruff format --check [redacted-repo] tests`
- `.venv/bin/pip wheel --no-deps --wheel-dir /tmp/[redacted-repo]-build .`
- `openspec validate split-service-by-domain --strict`

## Notes
Domain components are implementation details for now. Consumers should continue to construct and call `EcobeeService` while using explicit package imports.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
