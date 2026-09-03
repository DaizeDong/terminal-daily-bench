# Recognize MATERIALIZED as a keyword (issue752)

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

`MATERIALIZED` is absent from the `KEYWORDS` table, so in statements like `CREATE MATERIALIZED VIEW` the token is lexed as a `Name` instead of a `Keyword`. That leaves it untouched by `keyword_case` formatting, producing inconsistent output while every other DDL keyword is normalized:

```python
import [redacted-repo]

[redacted-repo].parse("create materialized view x.y.z as select 1")[0].tokens[2].is_keyword
# -> False   (expected True; it is a Name, not a Keyword)

[redacted-repo].format("create materialized view x.y.z as select 1", keyword_case="upper")
# -> 'CREATE materialized VIEW x.y.z AS SELECT 1'   <- 'materialized' left lowercase
# expected: 'CREATE MATERIALIZED VIEW x.y.z AS SELECT 1'
```

`CREATE`, `VIEW`, `AS` and `SELECT` are all uppercased; only `materialized` is left alone.

## Fix

Add `'MATERIALIZED': tokens.Keyword` to `KEYWORDS`, next to the existing `VIEW` keyword. `MATERIALIZED` is a standard SQL keyword used for `CREATE`/`REFRESH`/`DROP MATERIALIZED VIEW` across PostgreSQL, Oracle, BigQuery and Snowflake, so classifying it as a keyword matches both the spec and how [redacted-repo] already treats `VIEW`.

After the change the token is a `Keyword` and `keyword_case='upper'` yields `CREATE MATERIALIZED VIEW x.y.z AS SELECT 1`.

## Tests

Added `test_materialized_view_issue752` in `tests/test_regressions.py`, asserting the token is a `Keyword` and that `keyword_case='upper'` normalizes it. The test is RED on the unpatched table and GREEN with the fix; the full suite stays green (488 passed, 2 xfailed, 1 xpassed). CHANGELOG and AUTHORS updated.

Disclosure: I prepared this fix with AI assistance under my direction; I reviewed and verified the change and the test myself.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
