# Fix SGDW foreach path applying weight decay once per (device, dtype) group

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

### What

`SGDW`'s multi-tensor (`foreach=True`) path applies decoupled weight decay once per `(device, dtype)` partition instead of once per step. When the parameters passed to the optimizer span more than one partition — e.g. mixed dtypes, or multiple devices — each parameter is decayed `N` times (`N` = number of partitions):

```python
import torch
from timm.optim.sgdw import SGDW

def run(foreach):
    p32 = torch.nn.Parameter(torch.tensor([1.0]))                        # float32
    p64 = torch.nn.Parameter(torch.tensor([1.0], dtype=torch.float64))   # float64
    for p in (p32, p64): p.grad = torch.zeros_like(p)
    SGDW([p32, p64], lr=1.0, momentum=0.0, weight_decay=0.1, foreach=foreach).step()
    return p32.item(), p64.item()

run(True)   # (0.81, 0.81)  -> decayed twice: 0.9**2   (WRONG)
run(False)  # (0.90, 0.90)  -> decayed once           (correct)
```

### Why

`_multi_tensor_sgdw` groups the tensors and iterates the groups:

```python
for ((device_params, device_grads, device_momentum_buffer_list), indices) in grouped_tensors.values():
    ...
    torch._foreach_mul_(params, 1. - wd_scale * weight_decay)   # <- full list, once per group
```

Every other tensor op in the loop operates on this group's `device_params` / `device_grads` — only the weight-decay line used the full `params` list, so it re-runs on every parameter once per partition. This diverges from the single-tensor path (`_single_tensor_sgdw` decays each param exactly once) and from PyTorch's own `_multi_tensor_sgd`, which applies its per-param ops to `device_params` inside the grouped loop.

It went uncaught because every existing SGDW/`csgdw` test uses single-dtype params on one device — a single partition, where `params == device_params` and the bug is masked.

### Fix

Apply the decay to `device_params`, matching every other op in the loop and the single-tensor reference. One-token change.

### Tests

Adds `test_sgdw_multi_tensor_weight_decay_matches_single_tensor`, which compares the `foreach` and single-tensor paths with two dtypes (two partitions). It fails on `main` and passes with the fix. Full `tests/test_optim.py` has no new failures (the two pre-existing failures — `test_kron[kron]` torch.compile/inductor on this platform, and the `csgdp` full-run convergence flake — reproduce identically on clean `main`).

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
