# perf: serve records_cost from the warm cache; memoize subagent nodes

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Two performance fixes (separate commits):

- **records_cost vs the warm cache**: pi/OpenClaw/CSV/JSONL probed `records_cost` in their constructors by reading the whole corpus, and `make_store` builds the leaf before `CachedStore` wraps it — so even a 100% cache hit paid a serial full read of every session file (the `"cost"` fast-skip rarely helps pi/openclaw, which write `usage.cost` on most lines). `records_cost` is now a lazy property on those four backends (derived from an already-run parse, probe only as a first-read fallback), persisted in the cache payload (`CACHE_VERSION` 3), and answered by `CachedStore` on a fingerprint hit without touching the leaf. `CombinedStore`'s AND over its backends becomes a `cached_property` for the same reason. Also folded in: a cache-hit row that no longer matches the `Workflow` dataclass falls back to a real parse instead of crashing.
- **Subagent nodes memo**: `detail_subagents` re-ran `store.workflow_nodes` (recursive CTE or backend parse) on every paint of the Subagents tab — every scroll step and every 200ms toast repaint. Rows are now cached per session in `_nodes_by_session`, the `_tool_by_session`/`_turns_by_session` pattern, cleared in the same reload/source-switch places.

Tested: 3 new tests (cache round-trip with a probe-counting fake backend, lazy-probe semantics incl. the metered/subscription split, memo hit/clear behavior); suite 307/307, ruff clean; `--demo --html` smoke-checked.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
