# Add enhanced synthetic data evaluation metrics

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

This PR adds enhanced synthetic-data evaluation metrics.

## Changes

- Added categorical distribution similarity metrics
- Added numeric summary-statistic difference metrics
- Added boundary violation checks for numeric and categorical columns
- Added privacy-risk proxy metrics using nearest-neighbor distances and exact duplicate rate
- Added optional ML utility evaluation when a target column is configured
- Added `quality_summary.csv` output for easier review
- Updated plotting functions to use the detected schema consistently
- Added tests for the new evaluation metrics

## Why

The project previously evaluated synthetic data using distribution overlap, correlation difference, PCA, and visual diagnostics. This PR adds a stronger evaluation layer that better reflects synthetic-data quality, validity, privacy risk proxies, and downstream utility.

## Testing

Tested locally with:

```bash
python -m compileall src tests
python -m unittest discover -s tests -v
python src/main.py --method copula --run_name pr3_copula_smoke

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
