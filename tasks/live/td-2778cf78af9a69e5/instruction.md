# fix(pandas): apply parsers to Index fields and schema components

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref]

## Problem

`@pa.parser` on a field annotated as `Index` is silently ignored:

```python
import pandas as pd
import [redacted-repo].pandas as pa
from [redacted-repo].typing import Index, Series

class Model(pa.DataFrameModel):
    idx: Index[int]
    col: Series[int]

    @pa.parser("idx")
    @classmethod
    def double(cls, series):
        return series * 2

df = pd.DataFrame({"col": [1, 2, 3]}, index=pd.Index([1, 2, 3]))
print(Model.validate(df).index.tolist())  # [1, 2, 3], parser never ran
```

Two things cause this. `FieldInfo.index_properties` never forwards the field's parsers, so `Index` components built from a `DataFrameModel` don't have them at all. And even with `parsers` passed directly to `pa.Index`, the index backend validates a series copy of the index and discards the parsed result, while coercion runs before parsers, so a parser that cleans raw values into a coercible form never gets a chance (the same ordering [redacted-ref] fixed for columns).

This forwards `parsers` in `FieldInfo.index_properties`, writes the validated series back to `check_obj.index` in `IndexBackend` when the schema has parsers, and defers index coercion (index-level and dataframe-level) to the array backend when parsers are present, so they run before dtype coercion like they do for columns. Added regression tests in `tests/pandas/test_parsers.py` for the model `Index` field case from the issue, parsers on a `pa.Index` inside a `DataFrameSchema`, and an index parser whose output needs coercion.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
