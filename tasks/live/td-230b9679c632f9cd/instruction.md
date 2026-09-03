# fix: match the DELETE in a MERGE regardless of case

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

`merge into t using (...) s on t.id = s.id when matched then delete` fails with

```
AssertionError: Expected 'Update' or 'Delete', got delete
```

while the same statement in uppercase works. sqlglot keeps the case of the `DELETE` token, so the WHEN clause parses to `Var(this='delete')` or `Var(this='DELETE')` depending on how it was typed, and the three places that check it compared case sensitively.

Since it surfaces as a bare `AssertionError` the server turns it into a 500, which clients retry, so a lowercase merge delete looks like a transient failure rather than a rejected statement.

Found while adding `describeOnly` support for MERGE, but it's unrelated to that: this breaks ordinary execution too. The existing merge tests all spell it `THEN DELETE`, which is why it wasn't caught.

Verified all three case variants now work, and the delete-only merge returns `number of rows deleted`, matching what an account returns.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
