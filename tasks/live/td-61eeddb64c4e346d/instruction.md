# grader: park the embodiment before capturing final frames

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

A duck-typed `embodiment.observe_parked()` hook: when a scored trial is about to be graded, the eval loop asks the embodiment to move to its parked pose and return one fresh, unobstructed observation; the vlm grader prefers it for the final frames and degrades to the last step's frames on any failure. Plan 0076 in this PR; implementation to follow.

🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
