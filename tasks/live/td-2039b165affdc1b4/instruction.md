# The `fully_commutes_with_sum` property was incorrectly using `sum()` on the flattened commuting structure, which does not yield a boolean. Changed to use `all()` to ensure the property returns True only if all sub-encoders fully commute with sum. Added type assertions in tests to verify the return type is boolean.

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

The `fully_commutes_with_sum` property was incorrectly using `sum()` on the flattened commuting structure, which does not yield a boolean. Changed to use `all()` to ensure the property returns True only if all sub-encoders fully commute with sum. Added type assertions in tests to verify the return type is boolean.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
