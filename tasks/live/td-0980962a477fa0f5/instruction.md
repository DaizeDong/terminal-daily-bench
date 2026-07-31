# feat(eval): classify benchmark regressions with false-discovery correction

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

Adds a deterministic surface that decides which benchmark regressions are *real* by correcting the whole metric family for multiple comparisons, so a nightly run with many metrics doesn't raise a blocking flag by chance.

- **`[redacted-repo]/eval/regression_significance.py`** — `regression_p_value` (one-sided **Welch t-test** per metric via the regularized incomplete beta), `benjamini_hochberg` (BH step-up **false-discovery** correction over the metric family), `classify_regressions` (per-metric BH + **blocking** (leakage-first) vs **advisory** (F1/recall) severity → a metric-only verdict payload), and `scan_nightly_regressions` (nightly monitor against a fixed reference baseline with a consecutive-confirmation debounce). Dataclasses `FalseDiscoveryDecision/Result`, `MetricRegressionSignal`, `RegressionClassification`, `NightlyRegressionWindow`.
- **`[redacted-repo]/eval/__init__.py`** — additive export block.
- **`tests/unit/eval/test_regression_significance.py`** — 12 tests.

Stdlib only (`math`, `statistics`, `json`); no dependency. `[redacted-ref]`.

## Design / judgment calls

- **FDR = Benjamini-Hochberg step-up**, pure-Python, verified against a hand-worked example (m=5, α=0.05, p={0.001,0.008,0.039,0.041,0.9} → reject only the two smallest; 0.039 survives despite being < 0.05 raw).
- **Per-metric test = Welch two-sample t-test** (Student-t tail via a continued-fraction `betai`) — chosen after a normal-approx z-test proved anti-conservative at n=5 (single-window FPR ≈ 5.2%).
- **Nightly scan uses a fixed leading baseline + non-overlapping confirmation windows**: a trailing/overlapping design can't both detect a sustained step-change and suppress noise (adjacent windows share 4/5 of their data). Measured: 0/1000 pure-noise trials block; a sustained leakage step is caught within ≤3 windows.
- **Classification**: leakage-family markers (`leak`, `leakage`, `exposure`, `reemission`, …) → blocking; F1/recall → advisory.

## Deviations from the issue's letter

- **New dedicated `regression_significance.py` module** rather than editing `regression_tracker.py` (which tracks regression *events*, not significance); structure/naming mirror that analog and `history.py`.
- **Fixed leading baseline + non-overlapping windows** for the nightly scan (justified above; the issue doesn't specify baseline handling).

## Independent review

An independent adversarial pass ran real numeric probes and found — and the branch now **fixes** (`[redacted-sha]`) — one **HIGH-severity safety hole**:

- **[HIGH] A leakage metric whose name didn't also contain a lower-is-better marker was auto-resolved to *higher-is-better*.** So a metric matched into the blocking leakage family (e.g. `phi_exposure_rate`, `leak_rate`, `boundary_leak`) but a genuine *increase* (the worse direction) produced a large p-value and was **never flagged** — not blocking, not even advisory. Reproduced: a ~50× spike in `phi_exposure_rate` → `verdict=clean`, `significant=False`. Fixed by making `_LOWER_IS_BETTER_MARKERS` a superset of the blocking-family substrings (`leak`, `exposure` added), so blocking ⟹ lower-is-better for auto-resolved directions (explicit `metric_directions` overrides still win). Post-fix: same input → `lower_is_better`, p=2.6e-08, `severity=blocking`.
- **[LOW] Stale docstring** on `regression_p_value` (said "z-test"; it's a Welch t-test) — corrected.

Verdict post-fix **clean**. Everything else verified correct: BH sets + monotone adjusted-p (boundary, ties, m=1, empty, p=0/1), Welch tails (t=2,df=8→0.0403; t=3.5,df=10→0.0029; wrong-direction correctly not significant; zero-variance/n=1 degenerate), and the nightly scan (0/1000 noise blocks, 200/200 step-changes caught within 3 windows).

## Data provenance

All test data is synthetic seeded Gaussian nightly series; no real data or PHI.

## Verification

- New tests: 12 passed. Gates + related (`regression_tracker`, `paired_significance`, `release_history_diff`, `api_surface_diff`, `public_api_docstrings`, `package_scaffold`): 44 passed. Noise FPR sweep: 0/1000 blocking; injected step: 200/200 caught ≤3 windows.
- `pre-commit` on changed files: all hooks green.
- No dependency added; `pyproject.toml` / `uv.lock` untouched.
- Base `[redacted-repo]:master`; `git rev-list --count HEAD..upstream/master` = 0.

## Relationship

Eval, Benchmarks &amp; Gates batch. Sibling of [redacted-ref] (nightly orchestration) — this is the FDR classifier [redacted-ref]'s verdict deferred to. Touches `eval/__init__.py` (additive export block); rebases trivially against sibling benchmark PRs.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
