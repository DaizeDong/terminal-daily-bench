# Add additive.cyclic_prefix_sum.residue_profile.compute operation

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

Implements `additive.cyclic_prefix_sum.residue_profile.compute` from [redacted-ref].

Given a bounded ordered integer sequence and a positive modulus, returns the complete partition of its nonempty prefix positions by their prefix sum residue modulo that modulus. This is the standard carrier for Graham's valid-ordering problem (Erdős [redacted-ref]), zero-sum block searches, and finite cyclic walk analysis.

## Design

- **Operation ID**: `additive.cyclic_prefix_sum.residue_profile.compute`
- **Input**: integer sequence + positive modulus
- **Output**: `CyclicPrefixSumResidueProfileResult` with rows (residue, positions)
- **Kernel**: O(n) modular accumulation with dictionary grouping

## Tests

- Fixture: Z/5Z sequence (1,1,3) with prefix residues 1,2,0
- Replay: each position's prefix sum matches its residue
- Collision classes: positions with equal residues are grouped
- Empty sequence: no rows
- Single element: one row
- Total positions: sum equals sequence length
- Large modulus: only occupied residues appear
- Modulus 1: everything collapses to 0
- Modulus preservation

[redacted-ref]

[Continue this on Linzumi]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
