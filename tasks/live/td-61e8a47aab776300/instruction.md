# feat: hand every extender hook one context object instead of re-deriving facts

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Extenders hooked on `FEATURE_GROUP_CALCULATE_FEATURE`, `VALIDATE_INPUT_FEATURE` and `VALIDATE_OUTPUT_FEATURE` only receive `(func, *args, **kwargs)`, so each one re-derives the same facts. This adds `HookContext`, built by `ComputeFramework` around each of those hook calls and read via `HookContext.current()` (a `contextvars` accessor, so `Extender.__call__` is unchanged and existing extenders keep working).

`HookContext` carries which hook fired, the feature group's `module.qualname` and `version()`, the owning plugin's installed distribution version, the requested feature names, the declared input feature names, the compute framework's class name, rows in/out, duration and status. `run_id`, `data_access_identity`, `tenant_id` and `principal` exist but stay `None` until their core seams land.

Behavior notes:

- All three hook sites dispatch through one helper, so `raise_on_error = False` is honored on the validate hooks exactly as on the calculate hook, with one extender or several.
- Every field read degrades silently to its fallback (`None` / `"unavailable"`); a root feature group, a plain-string `input_features`, or a non-introspectable `version()` no longer logs a warning per call.
- Declared input names are the union over the batched `FeatureSet`, resolved once per step (memoized on the `FeatureSet`, refreshed when option defaults materialize).
- Row counts never run a query: `__len__` is looked up on the type, a columnar dict counts its first column, DuckDB/SQLite relations report `None`, and the validate hooks never report `rows_out`.
- `status` reflects only the wrapped call and stays `None` until it finishes.
- Plugin version lookup matches package (`__init__.py`) and extension modules, skips the manifest scan when one distribution owns the namespace, ignores `.pyi` stub distributions, tolerates a malformed `RECORD`, and returns `None` instead of guessing.
- `func` handed to an extender is always an instrumentation wrapper (with `__self__` and `__wrapped__` set), not the bound classmethod; `Extender.feature_group_name(func)` and `inspect.unwrap(func)` still resolve it.

Documented in `docs/docs/chapter1/extender.md`; `HookContext` is exported from `[redacted-repo].steward`. `tox` is green.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
