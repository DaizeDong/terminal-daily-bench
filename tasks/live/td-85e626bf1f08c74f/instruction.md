# Fix required configuration option cache invalidation

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

Make a configuration option reuse and track its derived `.required()` provider so configuration cache resets also invalidate the required view.

[redacted-ref].

## Root cause and approach

`ConfigurationOption.required()` created a detached provider each time. After that provider resolved a value, the original option had no reference to its cache. An override correctly reset the root/original option tree, but could not reach the required provider captured by a `Singleton` or `Factory`, so recreating the consumer still returned the stale value.

The original option now lazily creates and retains one required provider. `reset_cache()` cascades to that provider, deepcopy preserves the relationship, and calling `required()` on an already-required option is idempotent. This keeps the existing cache for performance, as requested in the issue discussion, instead of recomputing every access.

## Verification

- New regression on unmodified code: failed because the recreated singleton received `{"value": "initial"}` during the override.
- `.venv/bin/pytest -q tests/unit/providers/configuration/test_config_py2_py3.py::test_required_cache_is_reset_after_option_override` — 1 passed.
- `.venv/bin/pytest -q tests/unit/providers/configuration` — 204 passed.
- Related Singleton, Factory, and deepcopy test groups — 328 passed.
- The Cython extension was rebuilt successfully before the green test runs.
- The changed Python test file passes Flake8; `git diff --check` passes. (`providers.pyx` is Cython and is not directly parseable by Flake8.)
- The remote `Tests and linters` workflow is currently `action_required` and generated no jobs. This is the repository's approval gate for workflows from forks, not a test execution failure; no remote-green result is claimed before a maintainer approves it.

## Scope

The change is limited to `ConfigurationOption` cache linkage/copying and one focused regression. It does not remove caching, change configuration lookup rules, or alter `Singleton`/`Factory` behavior.

## AI assistance

OpenAI Codex (GPT-5) was used to investigate the cache lifecycle, implement the focused change and regression, rebuild the extension, and run/review the verification above. I reviewed the final diff and am disclosing this assistance explicitly.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
