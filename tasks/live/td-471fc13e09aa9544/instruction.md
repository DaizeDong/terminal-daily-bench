# Clarify equal opportunity warning message

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Clarifies the warning emitted by `equal_opportunity_score` so it includes both the `y_true` and `y_hat` positive-target conditions that trigger the zero-return path.

This only updates the warning text and its regression coverage; it does not change the metric logic.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
