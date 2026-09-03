# 🐛 Separate bar labels and p-values

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Purpose

Prevent bar value labels from crossing p-value brackets and annotation text when `add_tip=True` and statistical comparisons are shown together.

## Changes

- Measure the value-label extent for vertical and horizontal bar plots.
- Reserve label-aware clearance before drawing p-value annotations, accounting for the axis expansion caused by stacked comparisons.
- Add regression coverage that checks value labels against both p-value lines and text.

## Root cause

The p-value annotation layout started from bar heights and did not account for the fixed-size text drawn above or beside each bar. Stacking comparisons then expanded the value axis and reduced the visible clearance further.

## Testing

- `make test` — 429 tests passed with 100% coverage.
- `make lint` — all formatting, linting, type-checking, and repository hooks passed.
- Reproduced the affected gallery example and verified that the annotation bounding boxes no longer overlap.

## Risks and follow-ups

Risk is limited to p-value spacing when bar value labels are enabled. Bar plots without value labels and outside p-value annotations retain their existing layout. No follow-up work is required.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
