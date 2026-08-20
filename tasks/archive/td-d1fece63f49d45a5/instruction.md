# Fix SPEA2 truncation selection

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref]

This PR updates SPEA2 survival truncation to use lexicographical ordering of sorted distances when too many non-dominated solutions are present.

Previously, the truncation step only considered the nearest-neighbor distance, which could remove an extreme non-dominated solution in tie cases. The updated implementation compares the sorted distance rows lexicographically, as required by the SPEA2 truncation procedure.

A regression test was added for the minimal example from the issue, checking that the extreme points are preserved when reducing three non-dominated points to two survivors.

Test:
python -m pytest tests/algorithms/test_spea2.py -q

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
