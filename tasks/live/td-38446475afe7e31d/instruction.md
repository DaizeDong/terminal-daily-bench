# Canonicalize inverse Klein j-invariant

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

This PR makes `kleinjinv(J)` return the canonical representative in the standard modular fundamental domain and optimizes both `kleinjinv(J)` and `taufrom(g2, g3)` for common real inputs.

## Motivation

The inverse Klein invariant is multivalued because modularly equivalent values of `tau` produce the same `J`. Previously, `kleinjinv` returned the value selected by the principal roots in its algebraic formula, without documenting or enforcing a canonical domain.

This PR gives the function a consistent, documented result by reducing it to the standard modular fundamental domain. Relatedly, it also reduces the cost of common real-valued calculations, particularly `taufrom(g2, g3)` by using recent optimisations in `omega1omega2from` which naturally changed the modular equivalent `tau`, hence it was postponed to this PR. The fundamental domain is now enforced on the `tau` returned by `taufrom(g2, g3)` and documented.

## Changes

- Reduce the result of `kleinjinv` to the standard modular fundamental domain:
  - `abs(Re(tau)) <= 1/2`
  - `abs(tau) >= 1`
  - prefer `Re(tau) = 1/2` over `-1/2` on the vertical boundary
  - prefer the right half of `abs(tau) = 1` on the circular boundary
- Document the modular equivalence and fundamental-domain convention.
- Return the canonical special values:
  - `kleinjinv(0) = 1/2 + i*sqrt(3)/2`
  - `kleinjinv(1) = i`
- For real `J > 1`, remove insignificant imaginary rounding from the recovered modular lambda value. This allows the AGM evaluations to remain real.
- Optimize `taufrom(g2, g3)` for suitable real invariants using direct real elliptic formulas.
- Handle `g2 = 0` and `g3 = 0` directly.
- Retain `kleinjinv` as the fallback for general complex, degenerate, and numerically sensitive cases.
- Share the real elliptic data calculation with the existing period-conversion implementation.

The changes are internal apart from the newly documented canonical `tau` being returned in the fundamental domain from `kleinjinv` and `taufrom(g2, g3)`; no function signatures are changed.

## Performance

The following results were measured with `mp.dps = 50`. Each row is the mean over ten representative inputs, measured with `pyperf` on the same machine.

| Benchmark | Master | This PR | Difference |
|---|---:|---:|---:|
| `kleinjinv`, real `J > 1` | 390 μs | 181 μs | **2.16× faster** |
| `kleinjinv`, complex `J` | 410 μs | 474 μs | 1.16× slower |
| `taufrom(g2, g3)`, real invariants | 397 μs | 114 μs | **3.48× faster** |
| `taufrom(g2, g3)`, complex invariants | 440 μs | 524 μs | 1.19× slower |

The real cases benefit from real AGM arithmetic and direct elliptic formulas. General complex inputs are modestly slower because this PR additionally reduces the result to the documented fundamental domain. That canonicalization was not performed on master.

The geometric mean across the four benchmark groups was **1.53× faster**.

<details>
<summary>Benchmark script and reproduction commands</summary>

The script requires `pyperf`:

```bash
python -m pip install pyperf
```

Save the following as `/tmp/benchmark_kleinjinv_taufrom_pyperf.py`:

```python
#!/usr/bin/env python3
"""Compare kleinjinv and taufrom(g2, g3) with pyperf."""

import subprocess
import time

import pyperf

import [redacted-repo]
from [redacted-repo] import kleinjinv, mp, mpc, mpf, taufrom


mp.dps = 50

KLEINJ_REAL_CASES = [
    mpf('1.01'), mpf('1.1'), mpf('1.5'), mpf(2), mpf(5),
    mpf(10), mpf(100), mpf(1000), mpf('1e6'), mpf('1e12'),
]

KLEINJ_COMPLEX_CASES = [
    mpc('0.2', '0.3'), mpc(2, 1), mpc(-1, '0.5'),
    mpc(10, -3), mpc('-0.25', -2), mpc(100, '0.1'),
    mpc('0.01', 4), mpc(-5, -7), mpc('1.1', '0.01'),
    mpc('1e4', '1e3'),
]

TAUFROM_REAL_CASES = [
    (mpf(60), mpf(140)), (mpf(12), mpf(1)),
    (mpf(12), mpf(-1)), (mpf(4), mpf(1)),
    (mpf(4), mpf(-1)), (mpf(1), mpf(1)),
    (mpf(1), mpf(-1)), (mpf(10), mpf(5)),
    (mpf(100), mpf(1)), (mpf(-4), mpf(1)),
]

TAUFROM_COMPLEX_CASES = [
    (mpc(1, 2), mpc(3, -4)),
    (mpc(-2, 1), mpc('0.5', 3)),
    (mpc(5, -7), mpc(-3, -2)),
    (mpc(2, '0.25'), mpc(-1, '1.5')),
    (mpc(-6, -2), mpc(4, '0.75')),
    (mpc('0.125', 3), mpc('-2.5', '0.5')),
    (mpc(10, 1), mpc(1, -8)),
    (mpc(-1, '0.1'), mpc('-0.25', -2)),
    (mpc(3, -5), mpc(7, 2)),
    (mpc(-4, 6), mpc(-5, 3)),
]


def bench_kleinjinv(loops, cases):
    start = time.perf_counter()
    for _ in range(loops):
        for value in cases:
            kleinjinv(value)
    return time.perf_counter() - start


def bench_taufrom(loops, cases):
    start = time.perf_counter()
    for _ in range(loops):
        for g2, g3 in cases:
            taufrom(g2=g2, g3=g3)
    return time.perf_counter() - start


revision = subprocess.check_output(
    ['git', 'rev-parse', '--short', 'HEAD'], text=True).strip()
runner = pyperf.Runner(metadata={
    '[redacted-repo]_revision': revision,
    '[redacted-repo]_file': [redacted-repo].__file__,
    '[redacted-repo]_dps': mp.dps,
})
for name, function, cases in [
        ('kleinjinv: real J > 1 mean', bench_kleinjinv,
         KLEINJ_REAL_CASES),
        ('kleinjinv: complex J mean', bench_kleinjinv,
         KLEINJ_COMPLEX_CASES),
        ('taufrom(g2,g3): real mean', bench_taufrom,
         TAUFROM_REAL_CASES),
        ('taufrom(g2,g3): complex mean', bench_taufrom,
         TAUFROM_COMPLEX_CASES)]:
    runner.bench_time_func(name, function, cases, inner_loops=len(cases))
```

Run it on master:

```bash
git checkout master
PYTHONPATH=. python /tmp/benchmark_kleinjinv_taufrom_pyperf.py \
    --processes 10 -o /tmp/kleinj-tau-master.json
```

Run it on this branch:

```bash
git checkout kleinjinv-fundamental-domain-pr
PYTHONPATH=. python /tmp/benchmark_kleinjinv_taufrom_pyperf.py \
    --processes 10 -o /tmp/kleinj-tau-branch.json
```

Compare the results:

```bash
python -m pyperf compare_to \
    /tmp/kleinj-tau-master.json \
    /tmp/kleinj-tau-branch.json \
    --table
```

</details>

## Testing

Focused elliptic tests and doctests pass:

```text
54 elliptic tests passed
24 elliptic doctests passed
```

## AI use

OpenAI Codex using a GPT-5 model was used to help explore implementation alternatives, draft code and documentation changes, construct tests, and prepare the performance benchmarks. I reviewed the resulting changes and verified them with the focused test suite and comparative benchmarks above.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
