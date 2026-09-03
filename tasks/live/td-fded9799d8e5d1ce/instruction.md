# fix(cli): use human-readable unit in batch manifest size error

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- The batch manifest size error message was interpolating the raw byte constant (`[redacted-sha]`) instead of the plain-English `1 MiB` used in the help text and companion task-count error message.
- Changed the error to say `"batch manifest exceeds the 1 MiB limit"` for consistency and readability.

## Test plan

- [ ] Provide a batch manifest file larger than 1 MiB and confirm the error message reads `"batch manifest exceeds the 1 MiB limit"`

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
