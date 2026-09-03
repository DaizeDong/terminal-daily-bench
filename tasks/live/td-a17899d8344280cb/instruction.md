# feat: support structured types (by treating as JSON without their element types)

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Why

[redacted-ref]   

Snowflake supports structured type declarations like `ARRAY(VARCHAR)` or `OBJECT(a INT)`. `[redacted-repo]` converts these to `JSON` types, but retains the nested type information, causing DuckDB to emit `Parser Error: Expected a constant as type modifier`. 

## How

Convert Snowflake structured types to plain DuckDB `JSON` types while preserving their nullability constraints. This allows structured values to use the same JSON-backed representation as existing semi-structured types.

## Details 

`semi_structured_types()` copies the `DataType` node and reassigns only `this`, so a Snowflake structured type keeps its `expressions`:

There are are a few `arg_types` on a `DataType` node: 

```python
arg_types = {
    "this": True,        # required
    "expressions": False,
    "nested": False,
    "values": False,
    "kind": False,
    "nullable": False,
    "collate": False,
}
```

Returns a fresh `JSON` node instead, dropping the optional `arg_types` to prevent them from flowing through as type modifiers.

---

I found Snowflake's naming a bit confusing and wasn't sure if that needs disambiguation here: 

> [The Snowflake structured types are ARRAY, OBJECT, and MAP.]([redacted-url])

(from Snowflake docs)

 However, the types share names with semi-structured types, leading to weird test names like `test_semi_structured_types_structured()`, if that should be cleaned up, please let me know

## Testing

Added `test_semi_structured_types_structured`, covering `ARRAY(T)`, `OBJECT(k T)` and a structured type nested inside a `MAP`.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
