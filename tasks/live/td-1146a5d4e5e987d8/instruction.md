# Fix function grouping skipped for lowercase 'as' in CREATE TABLE AS SELECT

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

- [x] ran the tests (`pytest`)
- [x] all style issues addressed (`ruff`)
- [x] your changes are covered by tests
- [x] your changes are documented, if needed

In `group_functions` (`[redacted-repo]/engine/grouping.py`), the guard that suppresses function grouping for `CREATE TABLE name (...)` checks three tokens, but only two are case-insensitive:

```python
if tmp_token.value.upper() == 'CREATE':
    has_create = True
if tmp_token.value.upper() == 'TABLE':
    has_table = True
if tmp_token.value == 'AS':        # case-sensitive
    has_as = True
```

Since SQL keywords are case-insensitive, a lowercase `as` in a `CREATE TABLE ... AS SELECT` (CTAS) statement leaves `has_as` False, so the guard fires and grouping returns early, skipping **all** function grouping for the statement.

```python
import [redacted-repo]
from [redacted-repo] import sql

p = [redacted-repo].parse("CREATE TABLE foo as SELECT count(x) FROM bar")[0]
# count(x) is left as a bare Name + Parenthesis instead of a sql.Function
```

With uppercase `AS` the same statement groups `count(x)` as a `Function`; only the keyword casing changes the parse tree. The existing `test_grouping_alias_ctas` covers the uppercase form.

The fix compares `as` case-insensitively like its sibling checks, and I added a lowercase regression test. The original guard behavior is preserved: `create table foo (a int, b int)` (no `AS`) still does not group `foo (...)` as a function in either case.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
