# Support sparse exact rational linear systems

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref]

## Problem

The rational solution and inconsistency operations used a coordinate list but admitted only 32 rows or variables. That fixed dense-style ceiling rejected sparse exact systems whose actual input, work, and output remain bounded.

## What changed

- add a domain-owned `SparseRationalMatrix` value with canonical row-major nonzero coordinates, retained axes, and explicit dense conversions
- use SymPy 1.14 `DomainMatrix` over `QQ` as the maintained sparse RREF backend
- replace the fixed 32-axis restriction with separate axis, nonzero, scalar-work, exact result-height, and transport-result bounds
- perform semantic admission once at operation invocation; result deserialization performs structural/source validation only
- remove the stale module-wide FLINT test marker now that rational-system outcomes use SymPy

This intentionally replaces the pre-stable inline coefficient-list contract. It does not claim that every matrix fitting the structural 8,192-axis/32,768-nonzero carrier is executable: operation admission rejects requests whose conservative fill-in work or exact result bounds exceed the envelope. In particular, this supports tractable sparse Atlas-style shapes without claiming the full 1,598 by 8,367 candidate-search matrix is safe in one call.

## Evidence

- 128 by 128 sparse diagonal solution
- 1 by 1,024 result-sensitive wide solution
- agreement with dense SymPy on the overlapping domain
- exact inconsistency-witness invariants
- duplicate/stored-zero, work-budget, and adversarial result-height rejection
- dense/sparse serialized round trip preserving implicit zero axes
- result deserialization regression proving semantic admission is not repeated

## Validation

`make affected AFFECTED_BASE=origin/main`

Selected lanes passed: scoped Ruff and mypy; 515 matrix tests; 112 catalog tests; 800 catalog-integration tests; and 907 integration tests.

An independent exact-diff review found no remaining correctness, contract, or boundedness issues.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
