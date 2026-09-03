# Do not apply type parameters to bare fields

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

`generate_models(bare_fields=True)` raises `TypeError` on any table with a parameterized `VARCHAR(n)` column where n != 255:

```python
sqlite3.connect('t.db').executescript(
    'CREATE TABLE t (id INTEGER PRIMARY KEY, name VARCHAR(64));')

DataSet('sqlite:///t.db', bare_fields=True).tables
# TypeError: Field.__init__() got an unexpected keyword argument 'max_length'
```

`generate_models` substitutes `BareField` for the introspected field class, then applies the parameters recovered by `_extract_type_params`, which `BareField` does not accept. This is the same reasoning behind the existing `extra_parameters = None  # e.g. max_length does not apply to FK.` for foreign keys.

Introduced in 4.1.2 by [redacted-sha]; 4.1.1 is unaffected. `pwiz` has no bare-fields mode, so the code generation path does not need the same guard.

sqlite-web calls `SqliteDataSet(db, bare_fields=True)`, so it currently fails to start against most databases when installed with [redacted-repo] >= 4.1.2.

Added a test to `TestReflectionFacets` that fails without the change. Full suite passes (1705 tests, sqlite).

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
