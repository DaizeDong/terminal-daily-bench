# Fix completion when wordbreak is first character

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

When a completion argument starts with a wordbreak character (e.g. "a :b"), [redacted-repo] doesn't properly set `last_wordbreak_pos` and remove the wordbreak character from the results. This causes bash to add an extra wordbreak character (e.g. "a ::b") which then breaks any further completion. This commit properly sets `last_wordbreak_pos` in the _shlex parser, and adds a test case for a leading colon.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
