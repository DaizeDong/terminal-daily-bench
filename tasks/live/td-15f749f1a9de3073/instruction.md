# feat(pyarrow): add first-class pyarrow.Table schema validation

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref]

Adds support for validating `pyarrow.Table` directly, so Arrow tables get dtype checks, value checks and class-based models instead of callers comparing `Table.schema` by hand.

```python
import pyarrow
import [redacted-repo].pyarrow as pa
from [redacted-repo].typing.pyarrow import Table

class Schema(pa.DataFrameModel):
    state: str
    price: int = pa.Field(in_range={"min_value": 5, "max_value": 20})

@pa.check_types
def transform(t: Table[Schema]) -> Table[Schema]:
    return t
```

`validate()` returns a `pyarrow.Table`, so a schema can be dropped into an existing pipeline without changing types.

## Approach

The narwhals backends are already frame-agnostic, so this reuses them rather than adding another validation engine. Most of the diff is the API layer and registry wiring:

| New module | Contents |
| --- | --- |
| `[redacted-repo]/api/pyarrow/` | `DataFrameSchema`, `Column`, `DataFrameModel`, `BaseConfig`, `PyArrowData`, dtype/validation-depth helpers |
| `[redacted-repo]/pyarrow.py` | Entry point, following `[redacted-repo]/ibis.py` |
| `[redacted-repo]/typing/pyarrow.py` | `Table[Model]` generic for `check_types` |
| `[redacted-repo]/backends/pyarrow/register.py` | Maps `pyarrow.Table` onto the narwhals backends |

## Changes to existing modules

Four modules outside the new package needed changes:

- **`narwhals_engine.py`** — registers the builtins `int`, `float`, `str` and `bool` as dtype equivalents. They previously raised `TypeError: data type not understood`, which made `pa.Column(int)` unusable. `polars_engine` already registers all four, so this brings narwhals to parity.

- **`backends/narwhals/checks.py`** — normalises pyarrow return values from `native=True` checks (`Table`, `*Scalar`, `*Array`/`ChunkedArray`), and hands single-argument check functions a `PyArrowData`, matching how polars gets `PolarsData` and ibis gets `IbisData`.

- **`backends/narwhals/base.py`** — the eager failure-case builder round-trips through polars, which a polars-free install cannot do, and the concat step dispatches on `.union()`, which `pyarrow.Table` does not have. Adds pyarrow builders for the eager and scalar paths plus a pyarrow branch in the concat. Routing is by `Implementation.PYARROW` rather than by whether polars is importable, so `failure_cases` comes back as a `pyarrow.Table` either way instead of changing type depending on what else is installed. Column layout and values match the polars output exactly.

- **`backends/register_checks.py`** — `register_default_check_backends` was eagerly registering the polars, ibis *and* pyspark backends for any `narwhals.*` check object. That primes each library's registration `lru_cache`, so a later wipe of the shared `BACKEND_REGISTRY` leaves those libraries unregistered for the rest of the process. It surfaced as 63 ibis failures once pyarrow started routing through narwhals. There is now a fast path that returns once a check backend for the narwhals type is registered.

## Two details worth review

**Validation depth.** A `pyarrow.Table` is always fully materialised, unlike a `pl.LazyFrame` or an `ibis.Table`, so it defaults to `SCHEMA_AND_DATA`. Without that, `Check.gt(0)` on `[1, -2, 3]` passes silently, which is worse than erroring. See `test_data_level_check_failure_is_raised`.

**Dtype translation.** Only some pyarrow types stringify into something the narwhals engine resolves — `pa.int64()` renders as `"int64"` and works, but `pa.float64()` renders as `"double"` and `pa.date32()` as `"date32[day]"`, which do not. `pyarrow_dtype_to_narwhals` round-trips a zero-length array through narwhals instead, which also covers parametrised types (timestamps, decimals, lists, structs).

## Known limitation

`coerce=True` is a no-op: it emits a `SchemaWarning` and reports a `WRONG_DATATYPE` error. This is inherited rather than introduced — coercion isn't implemented in the narwhals backend at all (polars behaves the same way under it, and `tests/narwhals/test_parity.py` marks coerce `xfail(strict=True)` with "coerce is a v2 feature"). Since pyarrow is served only by narwhals, it ships without coercion for now. `test_column_coerce_is_not_supported` pins the current behaviour so it fails once coerce lands.

## Tests

76 new tests in `tests/pyarrow/`, covering the container, dtypes, checks, the model API and backend registration.

| Suite | Result |
| --- | --- |
| `tests/pyarrow tests/polars tests/ibis tests/base tests/core` | 750 passed |
| `tests/narwhals` with `[redacted-repo]_USE_NARWHALS_BACKEND=True` | 222 passed |
| `tests/pandas tests/xarray tests/dask tests/geopandas` | 2987 passed |
| `tests/pyarrow` on a wheel-built venv with only the `pyarrow` extra | 75 passed, 1 skipped |

The two failures not listed above are pre-existing and behave identically on `main`: 5 pyspark tests needing `PYSPARK_PYTHON`, and `test_ibis_backend_is_narwhals` needing `[redacted-repo]_USE_NARWHALS_BACKEND=True`.

That last row is a venv built from the wheel with narwhals and pyarrow only — no pandas, polars, ibis or numpy — to confirm the extra stands on its own. The single skip needs ibis.

`prek run --all-files` is clean, both new doctests run, and the docs build (`sphinx -W -b=doctest`) reports no warnings from the new page.

## Packaging

Adds a `pyarrow` extra pinned to `pyarrow >= 13`, the floor already used in `environment.yml` and `requirements.txt`, so no new dependency is introduced. Also adds the extra to the noxfile's `DATAFRAME_EXTRAS` and to the CI matrix, plus a `docs/source/pyarrow.md` page.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
