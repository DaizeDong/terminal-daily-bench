# Fix cplot points rounding ([redacted-ref])

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Previously `int(x+1)` was used with the intention of rounding up when the result of the calculation of points per axis was not an integer. But it fails when the result is already an integer, such as 3, because it still adds 1 and ends with a 4x4 grid:

```text
points = 8 -> int(sqrt(8) + 1) -> int(2.83 + 1) -> int(3.83) -> 3 -> correct
points = 9 -> int(sqrt(9) + 1) -> int(3 + 1) -> 4 -> incorrect
```

This calculation is replaced by the `ceil` function, which rounds to the smallest integer greater than or equal to the original value.

I added a test to check that `points=8` and `points=9` produce a 3x3 grid with 9 evaluations in both `mp` and `fp`. Finally, I updated the documentation to make it clear what `points` means.

AI usage notice: I used Codex to implement the code and documentation changes in this patch. I reviewed the complete diff, ran the relevant tests and checks, and I understand the changes described above.

[redacted-ref]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
