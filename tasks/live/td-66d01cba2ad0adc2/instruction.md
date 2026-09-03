# Fix false positive on JOIN LATERAL by adding "lateral" to ALLOWED_FROM_CONTEXTS

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

Adds `"lateral"` to `ALLOWED_FROM_CONTEXTS` so that valid `JOIN LATERAL <table_function>` syntax (Snowflake, Postgres, BigQuery, Databricks) doesn't trigger a false positive in `check-script-has-no-table-name`.

[redacted-ref]

## Background

`LATERAL` is a SQL keyword used to introduce a correlated subquery or table function — it is not a table name. Two common forms exist:

    -- Form A: explicit JOIN LATERAL
    from t inner join lateral flatten(input => t.col) as f

    -- Form B: comma + LATERAL (Snowflake idiom)
    from t, lateral flatten(input => t.col) as f

Form B already passes the hook, but only by coincidence: the walker sees `from` → `t,` (comma stripped to `t`, treated as a table/CTE), and the next token after the comma has `prev=t`, so the `from`/`join` rule doesn't fire on `lateral`. There's an existing test that locks in this behaviour (added in [redacted-ref] back in 2021).

Form A — `inner join lateral ...` — fails today, because the walker sees `prev=join`, `cur=lateral` and adds `lateral` to the detected-tables set. The user gets:

    does not use source() or ref() macros for tables:
     - lateral

## Fix

One-line change to add `"lateral"` to the existing allow-list. This mirrors how `unnest` is already handled (BigQuery's analogue of `LATERAL`).

    ALLOWED_FROM_CONTEXTS: List[str] = ["distinct", "position", "unnest", "lateral"]

## Test plan

- [x] Added a new test case covering `INNER JOIN LATERAL FLATTEN(...) AS u` (the failing case from [redacted-ref]).
- [x] Added a new test case to verify a *real* hardcoded ref (`actual_table`) following a `LATERAL FLATTEN` is still detected — confirms the fix doesn't weaken the actual check.
- [x] Added unit-level coverage in `test_context_aware_parsing` for the `JOIN LATERAL`, `, LATERAL`, and "real ref after LATERAL" scenarios.
- [x] Existing tests still pass — no regressions.

## Notes

The maintainer noted in [redacted-ref] that a proper SQL parser (e.g. `sqlglot`) would be the long-term solution. This PR is a small, targeted fix in the spirit of the existing context-aware checks; it doesn't preclude that larger refactor.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
