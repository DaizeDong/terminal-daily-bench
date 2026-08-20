# Fix: `torch.compile` was a no-op in `load_checkpoint`

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref]

`[redacted-repo]_2p5_200M_torch_module.load_checkpoint` called `self = torch.compile(self)` inside the method body. That rebinds the local name `self` but doesn't mutate the object — the compiled version is immediately thrown away. Users passing `torch_compile=True` got no speedup at all.

The fix moves the compile call to the outer `[redacted-repo]_2p5_200M_torch.load_checkpoint`, targeting `self.model.forward` directly:

```python
torch_compile = kwargs.pop("torch_compile", self.torch_compile)
self.model.load_checkpoint(model_file_path, **kwargs)
if torch_compile:
    self.model.forward = torch.compile(self.model.forward)
```

`nn.Module.__call__` dispatches through `self.forward`, so reassigning the instance attribute is enough for the compiled version to be used by the `decode()` path.

## Why it still helps despite graph breaks

`forward` does not trace into a single clean graph. Each transformer layer writes to its KV cache with a data-dependent slice:

```python
start = decode_cache.next_index[0]    # tensor value, needs an implicit .item()
decode_cache.key[:, start:end] = key  # transformer.py:279
```

Dynamo can't trace a slice whose index is a runtime tensor value, so it graph-breaks here — once per layer. `torch._dynamo.explain()` on the real decode call path (forward + a populated cache) shows **8 graphs / 7 breaks**.

The breaks land on cheap memory copies. The expensive work — the QKV/attention/MLP matmuls — sits inside the compiled subgraphs and gets fused and optimized normally. So compile still pays off, just not as much as a fully unbroken graph would.

Measured on A100 with `google/[redacted-repo]-2.5-200m-pytorch`, batch=64, context=512, horizon=128: **1.55x median speedup** (**111ms → 72ms**). Numerical diff vs uncompiled: max abs 7.2e-05 (TF32 rounding).

## Tests

Two new tests in `tests/test_model_loading.py` verify that `model.forward` is compiled after `load_checkpoint(torch_compile=True)` and left as a plain bound method when `torch_compile=False`.

## **Possible follow-up** (not in this PR)

The per-layer graph break could be removed by making the cache-write index non-data-dependent (e.g. `capture_scalar_outputs=True`, or an `index_copy`/`slice_scatter` with a precomputed index). That would unlock the remaining headroom but is a larger, separate change.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
