# fix(ml): drop MetricComputation.__module__ property so builds can load

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Problem

Any build embedding a `MetricComputation` is unloadable. `[redacted-repo] build` succeeds, then the load fails in `[redacted-repo]/ibis_yaml/common.py:deserialize_callable`:

```
TypeError: can only assign string to MetricComputation.__name__, not 'property'
```

## Root cause

`MetricComputation` defined both `__name__` and `__module__` as properties. The error names `__name__`, but that one is a red herring — the trigger is `__module__`.

- `type.__name__` is a data descriptor on the metaclass, so it shadows the class dict entry: `MC.__name__` still returns the real `str`.
- `type.__module__` has no such protection — its getter returns `cls.__dict__["__module__"]` verbatim, so the property object leaks out at class level:

```python
>>> MetricComputation.__module__
<property object at 0x73fecf19bec0>   # not a str
```

cloudpickle's `_lookup_module_and_qualname` therefore fails, so it pickles the class **by value** instead of by reference, and reconstruction dies in `_class_setstate` doing `setattr(cls, "__name__", <property>)`.

Confirmed with a two-class control at module scope: a class with only `__name__` round-trips under both `pickle` and `cloudpickle`; adding `__module__` breaks both.

## Fix

Remove the `__module__` property, with a comment on `__name__` recording why it must not come back.

The only consumer is `udf.agg.pandas_df`, which copies `fn.__module__` onto the generated node type. That now reads `[redacted-repo].expr.ml.metrics` instead of `sklearn.metrics` — metadata only:

- **Expr hash is unchanged**: `[redacted-sha]` before and after.
- A full `build_expr` → `load_expr` round-trip executes and returns the correct result; it raises on `main`.

No other class in the codebase defines `__module__` or `__qualname__` as a property.

## Tests

Three regression tests in `test_metrics.py`, all of which **fail on `main` and pass here**:

- `test_metric_computation_module_is_a_str` — the cheap invariant; fails immediately and legibly if the property is ever re-added
- `test_metric_computation_cloudpickle_round_trip`
- `test_metric_computation_survives_build_serde` — drives the real `serialize_callable` → `deserialize_callable` frames a catalog load hits

`test_metrics.py`: 89 passed. Whole `expr/ml/tests/` dir: 481 passed. `test_split_lib.py` has 7 failures that reproduce on unmodified `main` and are unrelated to this change.

## ⚠️ Does not rescue existing artifacts

The pickle payload in already-written builds embeds the broken class *by value*, so upgrading does not make them loadable — I verified that building on `main` and loading with this fix still raises. **Builds produced by 0.3.39 or earlier that use metrics must be rebuilt.** Since `build` succeeded silently, anyone using metrics has been accumulating unloadable artifacts.

🤖 Generated with [Claude Code]([redacted-url])

[redacted-url]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
