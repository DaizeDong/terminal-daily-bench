# Admit larger bounded integer Sidon profiles

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Problem

`combinatorics.integer_set.sidon.decide` returns a complete ordered nonzero-difference ledger, but both request and result contracts reject every source above 32 elements. Its actual work and output are determined by `n(n-1)` rows and the source/difference wire widths, so the fixed cap excludes tractable profiles such as the first 69 squares.

## What changed

- widen the parser-level source carrier from 32 to 256 elements;
- reserve the complete canonical JSON result from the actual normalized values and all ordered differences before constructing row models;
- reject requests whose full ledger would exceed the real 10 MiB canonical output boundary;
- construct kernel-produced results through the trusted factory;
- make independent result validation replay every canonical ordered pair, subtraction, and the Sidon multiplicity decision.

The public postcondition is unchanged: the result contains each ordered pair of distinct normalized source elements exactly once. This does not introduce a decision-only shortcut or an incomplete profile.

## Evidence

- the first 69 squares are admitted and return all 4,692 rows;
- 256 small integers are admitted with a roughly 3.59 MB canonical payload;
- 256 maximum-width positive integers are rejected before result materialization;
- singleton input returns an empty ledger and `is_sidon=true`; duplicate input remains rejected;
- forged differences and decisions fail closed on `IntegerSidonResult.model_validate`;
- independent review checked the byte formula against canonical JSON: it is exact for `is_sidon=false` and conservatively overcounts true results by one byte.

`make affected AFFECTED_BASE=origin/main` passed on commit `[redacted-sha]`:

- scoped Ruff formatting and lint;
- scoped mypy;
- 912 combinatorics owner tests.

[redacted-ref].

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
