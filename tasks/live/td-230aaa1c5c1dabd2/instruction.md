# Release 2.4.0: expose pygame sprite spatial queries

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

This is the small 2.4.0 release branch for the pygame integration. It adds sprite-oriented spatial query methods on `[redacted-repo].pygame.Group` and updates the docs/examples around the pygame API.

Changes:
- Add `Group.query(...)` for direct rectangle queries that return pygame sprites.
- Keep `Group.query_rect(...)` as a backward-compatible wrapper for 2.3.0 callers, with a `DeprecationWarning` that points users to `Group.query(...)` and notes it would be removed if a future [redacted-repo] 3.0 does breaking API cleanup.
- Add `Group.nearest_neighbor(...)` and `Group.nearest_neighbors(...)` over indexed sprite rects.
- Update internal pygame collision helpers to call `Group.query(...)` directly so users do not get `query_rect(...)` deprecation warnings through `spritecollide(...)` / `spritecollideany(...)`.
- Update internal pygame index maintenance to use object-based `RectQuadTreeObjects` update/delete helpers instead of exposing or tracking quadtree IDs.
- Update README and docs to describe sprite rect queries and k-NN.
- Minor formatting changes due to updating from Ruff 0.6 to 0.15 in the pre-commit hooks
- Bump version metadata from `2.3.0` to `2.4.0`.

## Compatibility / reviewer notes

I compared this branch to `main` for public breaking changes. I did not find public API removals:
- `[redacted-repo].pygame.__all__` is unchanged.
- `Group.query_rect(...)` remains available and delegates to `Group.query(...)`, but direct calls now emit a `DeprecationWarning`.
- The new methods are additive.
- In the project pygame-ce environment, `pygame.sprite.Group` does not define `query`, `query_rect`, `nearest_neighbor`, or `nearest_neighbors`, so the additions do not shadow existing pygame group methods.

There are no current plans for a 3.0 release; the warning only identifies a future breaking-release cleanup point if one happens.

One private helper, `Group._find_sprite_id`, was removed as part of the internals cleanup. That is not public API, but downstream code reaching into internals would need to stop using it.

## Verification

- `.venv/bin/python -m pytest --no-cov tests/test_python/integration/test_pygame_integration.py tests/test_python/integration/test_public_api_contracts.py` - 25 passed
- `.venv/bin/python -m pytest --no-cov tests/test_python/integration/test_pygame_integration.py` - 20 passed after adding the deprecation warning
- `.venv/bin/python -m pytest --no-cov tests/test_python` - 355 passed
- `cargo test` - passed before the deprecation-only Python/doc update

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
