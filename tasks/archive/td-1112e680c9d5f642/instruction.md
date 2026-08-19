# fix: incorrect q=2 coefficient in PiecewisePolynomialKernel

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## What's broken
`PiecewisePolynomialKernel(q=2)` (q=2 is the default) returns incorrect covariance values. The q=2 covariance polynomial uses the coefficient `(j + 4*j + 3)/3` = `(5j+3)/3`, but it should be `(j**2 + 4*j + 3)/3`.

## Why it happens
In `_get_cov`, the q=2 branch dropped the square on the `j` term: `(j + 4 * j + 3)` instead of `(j**2 + 4 * j + 3)`. This contradicts the kernel's own docstring, Rasmussen & Williams Eq. 4.21, and the q=3 branch in the same function (which correctly uses `j**2`). Existing tests only exercised q=0 with point pairs whose distances fall outside the compact support, so `(1 - r)_+ = 0` zeroed the polynomial and the bug went undetected.

## Fix
Restore the square: `(j**2 + 4 * j + 3) / 3.0`.

## Test
Added `test_computes_piecewise_polynomial_kernel_q2` with closely-spaced inputs (r < 1, inside the support), comparing kernel output against the R&W closed form. Fails on the old coefficient (norm diff ~0.105), passes after.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
