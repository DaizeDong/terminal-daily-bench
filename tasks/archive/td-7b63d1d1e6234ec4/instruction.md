# fix: nicer debug print outs (and str for regex pattern)

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

This adds some `__repr__`'s and a `__str__` that should make debugging a little easier. See [redacted-ref].

This also allows printing out regex patterns with `str()`, which makes typing a little easier vs. accessing `.pattern`, which might be on None.

AI Usage Disclaimer: I used VSCode's copilot integration to add tests in the current style.

I didn't see a way to run prek or directly run ruff/black, let me know if I need to do some sort of formatting or linting.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
