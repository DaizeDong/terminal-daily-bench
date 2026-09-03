# Forward all user's parameters set in `PAGER` and improve flag detection

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Another PR following up on pager refactors that:
- Forwards all user's parameters set in `PAGER`
- Improve detection of raw mode by extending flag and option parsing
- Fix detection of `less.exe` on Windows (even if not currently exercised, this make the method future-proof)

But more importantly: adds dozen of testing with weird edge-cases around pager's internal methods.

Follows up on:
- [redacted-url]
- [redacted-url]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
