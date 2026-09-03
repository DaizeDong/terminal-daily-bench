# fix(risk-xray): honor bars_per_year=None in cross-market annualization

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## What / why

Every **multi-market** backtest crashed on v0.1.14 with `TypeError: must be real number, not NoneType` — `runner.py` deliberately sets `bars_per_year=None` for cross-market baskets (its comment: *"Cross-market: use calendar-day annualization (bars_per_year=None)"*), and `risk_xray._volatility` called `math.sqrt(ppy)` on it without a guard. Single-market runs were unaffected. `risk_xray.py` is new in v0.1.14, so this is a regression from v0.1.11.

## Fix

**Audit of every `bars_per_year` consumer found THREE crash sites** (the issue reported one):

1. `risk_xray._volatility` (the reported trace) — `math.sqrt(ppy)` unguarded. Fixed: `_annualize_factor(ppy)` — `sqrt(ppy)` when specified, **span-derived** (observed bars per elapsed calendar year, mirroring `calc_metrics`) when `None`, keeping both `annualized_vol` and `downside_deviation_annualized` defined. `compute_risk_xray` signature widened to `int | None`.
2. `options_portfolio._calc_options_metrics` (options cross-market path, `runner.py:1257` reaches it with `None`) — `bars_per_year <= 0` / `> 0` guards and `np.sqrt` raise `TypeError` on `None` (three sites). Fixed: `None` derives the effective bpy from the observed calendar span, mirroring `metrics.calc_metrics`; 252 fallback for degenerate spans.
3. `validation.run_validation` (validation-enabled cross-market runs, `base.py:878`) — `_sharpe`'s `np.sqrt(bars_per_year)` raises `TypeError` on `None`. Fixed with the same span-derived convention at the dispatcher entry.

**One convention for `None` across all consumers** (review consistency item resolved): span-derived effective bars per year, so risk_xray's annualized_vol, calc_metrics' sharpe and validation sharpe agree in one run card — the prior fixed-365 x-ray factor sat ~18% higher on a 252-trading-day daily series; now measured ratio 0.998. Degenerate spans fall back to 252 everywhere.

Already safe (untouched): `metrics.calc_metrics` (own span-derived bpy), `attribution_core`/`quantlib.timeseries` (always fed an int from the interval). Annotations widened to `int | None` across `engines/base.py`, `options_portfolio.py`, `crypto.py`, `validation.py`, `risk_xray.py`.

## Verify

- `compute_risk_xray(..., periods_per_year=None)` — both annualized fields follow the 365 factor (zigzag fixture exercises the downside branch); explicit `252` unchanged.
- Full crash contract: `engine.run_backtest(..., bars_per_year=None)` (the exact `runner.py:1260 → composite.py:150 → base.py:860` trace) no longer raises; `risk_xray_annualized_vol` is reported.
- 28 risk-xray tests + 112 cross-suite (engines, runner, market tools) pass; ruff clean.

[redacted-ref].

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
