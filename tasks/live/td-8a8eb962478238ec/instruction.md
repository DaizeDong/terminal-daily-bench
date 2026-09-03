# fix: support bind params and a values list source in MERGE

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Two independent causes behind [redacted-ref], both giving a 500.

**Params bound to every part of a split statement.** A MERGE becomes four statements, and only the one building `merge_candidates` keeps the placeholders. The same params were bound to all four, so the other three failed with `Parameter argument/count mismatch, identifiers of the excess parameters: 1, 2`. They're now bound to the parts that have placeholders.

This is why the issue reported that any bind parameter breaks a MERGE, while a bound INSERT is fine: an INSERT isn't split.

**A values list as the source.** `USING (VALUES (1, 'a')) AS s (id, name)` parses to `exp.Values`, not `exp.Subquery`, and only a subquery was checked for the alias, so the name was read from `.this`, wasn't an `Identifier`, and the assert blew up.

Worth noting this one has nothing to do with binds, it fails with literals too:

```sql
MERGE INTO t tgt USING (VALUES (1, 'x')) src (id, name) ON tgt.id = src.id
WHEN MATCHED THEN UPDATE SET tgt.name = src.name
```

I checked all three shapes from the issue against an account and Snowflake accepts them, including the values list.

Reproduces without the server, on `paramstyle="qmark"`, so the tests are in `test_merge.py` rather than `test_server.py`. Also confirmed through the JDBC driver, which is where it was found: all three variants pass now, previously two retried into a 500 and one hit the assert.

[redacted-ref]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
