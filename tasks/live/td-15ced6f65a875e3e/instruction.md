# fix: support non-float32 inputs in SIGReg

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Problem

`sigreg_loss` creates random projections and integration knots using PyTorch's default float32 dtype.

When embeddings use float16, bfloat16, or float64, the projection `einsum` receives operands with different dtypes and raises an error.

## Changes

Use an explicit computation dtype:

- promote float16 and bfloat16 inputs to float32;
- keep float32 inputs in float32;
- preserve float64 inputs as float64.

Random projections and integration knots use the same computation dtype.

## Validation

Before the change, the parameterized regression failed for float16, bfloat16, and float64. All four tested dtypes now produce finite scalar losses and finite backward gradients.

Commands:

- `pytest tests/test_regularizers.py -q`: 4 passed
- `pytest -q`: 42 passed, 4 skipped

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
