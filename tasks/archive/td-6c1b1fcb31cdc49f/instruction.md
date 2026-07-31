# Limit number of parts of a key

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-repo] has quadratic time complexity when handling parts of a key (via Flags.is_ calls in key_value_rule's loop, and maybe elsewhere). This isn't a problem unless a document has an excessive number (10_000-ish) of parts in a key.
Limiting input size seems like the best fix here.

`sys.getrecursionlimit` and `RecursionError` is already (and in the non-mypyc version, implicitly) used for `MAX_INLINE_NESTING`. Keys happen to not be parsed by recursive functions,
but that's an implementation detail; `RecursionError` works nicely for names of recursive
structures.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
