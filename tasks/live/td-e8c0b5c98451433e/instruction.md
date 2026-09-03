# feat(backtest): add Binance USD-M drift evidence artifacts

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- add deterministic Binance USD-M drift evidence for complete cross and isolated account snapshots
- fail closed for incomplete, unsupported, stale, or unsupported-provenance observations
- append strict-JSON audit records and atomically replace a concise latest summary
- preserve tolerance, source/schema/config provenance, comparison counts, and fidelity flags

## Why

Shadow 1 supplied immutable reconciliation contracts and Shadow 2 supplied the strict read-only observation boundary. This slice records their output as reviewable drift evidence without creating a second accounting ledger or an account action path.

Progresses [redacted-ref].

## Changes

- add a pure evidence builder over the existing reconcile_binance_account contract
- validate supported snapshot schema/profile/configuration hash before a comparison can be complete
- derive drift severity from numeric, symbol, and structural findings instead of trusting caller fields
- reject malformed or contradictory records before writing artifacts
- write artifacts only under an explicit run_dir/artifacts path: binance_drift.jsonl and binance_drift_summary.json
- add cross, isolated, rejection, tampering, strict-JSON, determinism, and import-boundary tests

## Test Plan

- 218 targeted tests passed across drift evidence, reconciliation, USD-M observation, crypto-engine regression, and write guardrails
- ruff check and ruff format --check passed for changed files
- py_compile and git diff --check passed

Full repository pytest was not run locally; CI remains authoritative for the full suite.

## Safety / Network Risk

- no network access in the evidence module or tests
- no credentials or account identifiers in artifacts
- no connector, order, alert, remediation, resize, or liquidation action path
- exchange evidence never mutates AccountState or RiskSnapshot
- CI uses synthetic fixtures only

## Fidelity Notes

- liquidation_engine_assessment is always not_assessed
- this compares reported account and position fields only
- rejected observations preserve why comparison was invalid; they do not become drift verdicts
- tolerance defaults remain explicit, versioned evidence and should be calibrated against real read-only observations separately

## Out of Scope

Live execution, alerting, dashboards, automatic correction, open orders, hedge mode, multi-assets/non-USDT collateral, portfolio margin, COIN-M, and exact Binance liquidation-engine reproduction.

## Rollback

Revert this commit. The slice has no migration and is not wired into an engine or live runtime.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
