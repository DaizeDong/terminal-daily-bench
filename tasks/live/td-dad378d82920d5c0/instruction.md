# Optimize conversion from Weierstrass invariants to half-periods

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Motivation

Passing `g2, g3` directly is a popular and natural way to evaluate the Weierstrass elliptic functions. For repeated evaluations, precomputing `omega1, omega2` remains the fastest approach, since otherwise the conversion from invariants to half-periods is performed on every call. However, it would be useful to reduce the timing difference between these two interfaces.

This PR optimizes the internal conversion performed by `omega1omega2from(g2=..., g3=...)`. It does not change the public API, function signatures, documented period conventions, or accepted inputs.

## Approach

Previously, the general conversion recovered `tau` through the inverse Klein j-invariant and then reconstructed the period scale using Eisenstein series and theta constants.

The optimized implementation instead obtains the elliptic parameter and period scale together:

- For real invariants with three real cubic roots, it uses the trigonometric cubic solution followed by complete elliptic integrals.
- For real invariants with one real root, it uses real Cardano radicals and a quadratic transformation, keeping the elliptic-integral calculations real.
- For generic complex invariants, it solves the cubic directly and constructs the periods using AGM formulas.
- The lemniscatic case uses its closed-form period.
- Near the cusp and elliptic points, where the direct root formulas become singular or ill-conditioned, it retains the previous inverse-j/Eisenstein route as a fallback.
- The fallback Eisenstein calculation uses Jacobi's theta identity to avoid one theta-constant evaluation.

The resulting basis is reduced and oriented according to the existing `omega1omega2from` convention.

## Timings

These are median wall-clock timings at 50 decimal digits using Python 3.13.4 on macOS arm64, with five timing repeats.

### Half-period conversion

| Input cases | Before (ms/call) | After (ms/call) | Speedup |
|---|---:|---:|---:|
| Mean of 10 generic real cases | 0.937 | 0.112 | 8.4x |
| Representative generic complex case | 0.918 | 0.550 | 1.7x |

### Relative cost of passing invariants

The following table reports time when passing `g2`, `g3` / time when passing precomputed `omega1`, `omega2`.

A value of `1.00x` would mean that passing `g2, g3` adds no measurable conversion overhead. For example, `2.38x` means that the call using `g2, g3` took 2.38 times as long as the corresponding call using precomputed periods. Lower values are therefore better.

Each column is the mean ratio across the same 10 generic real invariant pairs:

- **Before**: the ratio using the implementation on `master`.
- **After**: the ratio using this optimized implementation.

| Function | Before | After |
|---|---:|---:|
| `weierp` | 2.38x | 1.28x |
| `weierpprime` | 1.74x | 1.17x |
| `weiersigma` | 2.81x | 1.32x |
| `weierzeta` | 2.11x | 1.21x |

Precomputing `omega1, omega2` therefore remains worthwhile for repeated calculations, but using the direct `g2, g3` interface is substantially less expensive as a result of this PR.

## Validation against Wolfram Engine

The optimized `omega1omega2from(g2=..., g3=...)` was compared with Wolfram Engine's `WeierstrassHalfPeriods[{g2, g3}]` at 60 decimal digits.

The 245 deterministic cases comprised:

- 100 random real invariant pairs;
- 100 random complex invariant pairs;
- 5 fixed and special cases;
- 24 cases on both sides of the direct/Eisenstein fallback threshold;
- 16 cases approaching the discriminant-zero cusp from both sides.

| Result | Cases |
|---|---:|
| Same ordered and signed period pair | 244 |
| Equivalent period basis | 1 |
| Failures | 0 |
| Total | 245 |

The maximum relative error among the 244 direct matches was `1.[redacted-sha]-35`.

The sole equivalent-basis result was the lemniscatic case `(g2, g3) = (1, 0)`. If Wolfram returns `(w1, w2)`, [redacted-repo] returns `(-w2, w1)`. This is a determinant-one change of basis representing the same period lattice, with `tau = i`. It is also present on master and does not constitute a change in expected output.

#### Comparison with Wolfram Engine Timings

The following timings use the same 10 real and 10 complex invariant pairs, with 50-digit approximate inputs:

| Case group | [redacted-repo] mean | Wolfram mean | Comparison |
|---|---:|---:|---:|
| Generic real invariants | 0.112 ms/call | 0.152 ms/call | [redacted-repo] is approximately 1.36x faster |
| Generic complex invariants | 0.562 ms/call | 0.229 ms/call | Wolfram is approximately 2.45x faster |

### Possible future work

The complex path constructs the periods using two complex AGM evaluations. These account for approximately 0.241 ms of the 0.571 ms measured for the complete complex conversion, or about 42% of its runtime.

The current [`mpc_agm` implementation]([redacted-url]) already contains explicit TODO items to:

- check that convergence works as intended;
- optimize the implementation;
- select a nonarbitrary branch.

In particular, `mpc_agm` uses generic complex arithmetic and repeatedly computes complex absolute values when checking convergence. Profiling identified this as the largest individual cost in the complex invariant-to-period path.

Optimizing `mpc_agm` is therefore a promising direction for future work, although it would not account for the entire difference from Wolfram. The remaining cost includes complex cubic radicals, square roots, root construction, modular-basis reduction, and other Python-level multiprecision operations.

## Tests

The added tests cover:

- round trips from invariants to periods and back at several precisions;
- real and complex invariants in the different discriminant regions;
- reduction of the resulting period ratio to the fundamental domain;
- continuity across the threshold between the direct and fallback methods.

The focused elliptic test file passes:

```text
51 passed
```

## AI use declaration

OpenAI GPT-5, through Codex, was used to assist with investigating the performance bottlenecks, implementing the optimization, developing tests and benchmark scripts, running and interpreting the Wolfram Engine comparison. I designed the scope of the PR, suggested things to explore, reviewed all generated changes and results, and ran test suites.

## Reproducibility

Below is a minimal timing script to compare this branch and master. It shows comparable numbers to the tables reported above.

```
git switch master
python my_data/benchmark_omega1omega2from_pyperf.py -o /tmp/omega-master.json

git switch omega-period-optimize-pr
python my_data/benchmark_omega1omega2from_pyperf.py -o /tmp/omega-pr.json

python -m pyperf compare_to \
    /tmp/omega-master.json \
    /tmp/omega-pr.json \
    --table
```

```python
#!/usr/bin/env python3
"""Benchmark invariant-to-half-period conversion for real and complex cases."""

import subprocess
import time

import pyperf

import [redacted-repo]
from [redacted-repo] import mp, mpc, mpf, omega1omega2from


mp.dps = 50

REAL_CASES = [
    (mpf(60), mpf(140)),
    (mpf(12), mpf(1)),
    (mpf(12), mpf(-1)),
    (mpf(4), mpf(1)),
    (mpf(4), mpf(-1)),
    (mpf(1), mpf(1)),
    (mpf(1), mpf(-1)),
    (mpf(10), mpf(5)),
    (mpf(100), mpf(1)),
    (mpf(-4), mpf(1)),
]

COMPLEX_CASES = [
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


def bench_cases(loops, cases):
    start = time.perf_counter()
    for _ in range(loops):
        for g2, g3 in cases:
            omega1omega2from(g2=g2, g3=g3)
    return time.perf_counter() - start


revision = subprocess.check_output(
    ['git', 'rev-parse', '--short', 'HEAD'], text=True).strip()
runner = pyperf.Runner(metadata={
    '[redacted-repo]_revision': revision,
    '[redacted-repo]_file': [redacted-repo].__file__,
    '[redacted-repo]_dps': mp.dps,
})
runner.bench_time_func(
    'omega1omega2from: real mean', bench_cases, REAL_CASES,
    inner_loops=len(REAL_CASES))
runner.bench_time_func(
    'omega1omega2from: complex mean', bench_cases, COMPLEX_CASES,
    inner_loops=len(COMPLEX_CASES))
```

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
