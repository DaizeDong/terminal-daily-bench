# datetime: propagate NaN for week and days_in_month with missing_values=ignore

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

When `missing_values="ignore"`, `DatetimeFeatures.transform()` raises for the `week` and `days_in_month` features if the input has a missing date. Both cast to `np.int64`, which fails on the NaT-derived NA:

```
IntCastingNaNError: Cannot convert non-finite values (NA or inf) to integer
```

The other datetime features (month, year, day_of_month, ...) do not force an int cast and correctly return NaN for the missing row, so only these two were affected.

Repro:

```python
import pandas as pd
from [redacted-repo].datetime import DatetimeFeatures

X = pd.DataFrame({"date": pd.to_datetime(["2022-01-01", None, "2022-03-01"])})
DatetimeFeatures(features_to_extract=["days_in_month"],
                 missing_values="ignore").fit(X).transform(X)
```

This casts both to `float64` instead, so the missing row becomes NaN like the other features. Added a test covering `week` and `days_in_month` with `missing_values="ignore"`.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
