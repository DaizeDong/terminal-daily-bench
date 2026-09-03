# Keep large local stores responsive

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- Cache one parsed event snapshot per durable ledger revision, then share one content fingerprint across the native app's glance, tasks, plan, session, and usage refresh fan-out.
- Invalidate safely across processes with SQLite mutation triggers and coalesce concurrent cold reads with a single-flight lock; legacy flat-file stores retain their existing file-signature path.
- Move the macOS app to property-granular Observation, stabilize fallback row identities, compute the Work projection once per render, and lazily construct large scroll collections while preserving eager deterministic snapshots.
- Add cross-process/concurrency regressions, 1,000-row Swift coverage, and a reproducible 50,000-event benchmark.

## Why this design

The live store audit found three compounding costs: every dashboard endpoint decoded and hashed the complete ledger before its higher cache could answer; broad `ObservableObject` publication invalidated unrelated panes; and several high-volume collections were built eagerly with unstable legacy fallback IDs.

This follows Apple's SwiftUI guidance around explicit dependencies, stable identity, property-level Observation, and lazy stacks. It also keeps the change bounded: response schemas, endpoint limits, data ownership, and visual markup stay unchanged.

Safety properties:

- The ledger cache key lives in SQLite and is advanced by INSERT, UPDATE, and DELETE triggers, so older processes and direct repair transactions cannot leave a long-running daemon stale.
- Snapshot rebuilds are single-flight, and cross-process mutation is covered by tests.
- Existing mutable `list_all_events()` behavior remains available to write/control lanes; only read-only dashboard projections use the shared snapshot.
- SnapshotMode stays eager because ImageRenderer cannot authoritatively lay out lazy content; all reviewed pixel references still match.
- The app still performs one full ledger parse after each real revision. Persisted rollups or database-native projections would be the next step for multi-million-event stores, not part of this focused fix.

## Performance evidence

Local comparative benchmark, 50,000 synthetic events, seven warm rounds, four native refresh routes:

| Revision | Cold refresh | Warm median |
| --- | ---: | ---: |
| `origin/main` (`[redacted-sha]`) | 1.055886s | 0.568988s |
| this branch | 0.674708s | 0.024044s |

That is a 95.8% warm-time reduction (23.7x faster) and a 36.1% cold-time reduction. The comparative runs used the same routes and returned the same 6,711 aggregate response bytes. This is a local TestClient benchmark of the refresh boundary, not a claim about every end-to-end UI frame.

Reproduce:

```bash
PYTHONPATH=src .venv/bin/python benchmarks/dashboard_refresh.py --events 50000 --rounds 7
```

## Review order

1. `src/[redacted-repo]/event_log.py` and `src/[redacted-repo]/service.py` — revision contract and parsed snapshot.
2. `src/[redacted-repo]/api.py` and `src/[redacted-repo]/glance.py` — shared native refresh boundary.
3. `DashboardStore.swift`, `GlanceState.swift`, `Theme.swift`, and `WorkPane.swift` — granular observation, stable/lazy rendering, and one-pass projection.
4. `LargeDataPerformanceTests.swift`, Python regression tests, and `benchmarks/dashboard_refresh.py` — invariants and measured result.

## Test plan

- [x] Focused Python/API regressions: 137 passed (one upstream Starlette TestClient deprecation warning).
- [x] Swift suite: 122 tests, 6 visual-only skips, 0 failures.
- [x] Canonical visual references: all six suites match on `macos-26.6-25G72-xcode-26.6-17F113-arm64-2x`.
- [x] `swift build -c release` and `./Scripts/build-app.sh`.
- [x] Visual snapshot CLI, dashboard candidate packaging/intake, and app bundle identity suites.
- [x] 50,000-event benchmark after implementation.
- [ ] Full local `pytest -q`: 2,644 passed and 10 macOS process-ownership tests failed. The exact same 10 selectors fail 10/10 in a detached, untouched `origin/main` worktree with `process identity no longer matches`; none touch this diff. Linux CI remains the authoritative matrix for Python 3.11-3.13.
- [x] Secret review: no credentials or captured user data added; fixtures are synthetic.
- [x] No paid provider/API calls were run.

The packaged current-build app and a disposable daemon also launched successfully. Exact-window automation was not claimed because macOS could not disambiguate it from the already-running installed app sharing the same product identity; canonical pixel verification above is complete.

## Safety checklist

- [x] Preserves local-first behavior
- [x] Does not store API keys or secrets
- [x] Does not expose localhost services publicly by default
- [x] Does not control processes [redacted-repo] did not start
- [x] Provider/API forwarding remains opt-in and budget-gated
- [x] JSON output paths remain machine-readable when `--json` is used

## Docs

- [x] No public contract changed; code comments, tests, and the benchmark document the internal performance boundary.
- [x] Public docs avoid private strategy, private roadmap, and overbroad support claims.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
