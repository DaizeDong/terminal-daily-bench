# [BUG] Magnitude-phase mode breaks dsp.average with custom weights

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

When using the `magnitude_phase` option in `dsp.average` with explicit (non-`None`) weights, there will be numpy errors (see linked issue).
This PR fixes this and adds tests that check all modes with explicit weights.

[redacted-ref]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
