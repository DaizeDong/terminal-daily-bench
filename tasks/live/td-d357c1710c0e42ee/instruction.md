# fix(polys): terminate subresultants_pg sequences on zero remainder

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

## Bug

`subresultants_pg` and `modified_subresultants_pg` crash whenever a pseudo-remainder is identically zero (`q | p`, or exact division later in the sequence):

```python
>>> from [redacted-repo] import symbols
>>> from [redacted-repo].polys.subresultants_qq_zz import subresultants_pg, modified_subresultants_pg
>>> x = symbols('x')
>>> p = 4*x**3 + 3*x**2 + x + 2
>>> q = x + 1                      # p(-1) == 0, so the first remainder is 0
>>> subresultants_pg(p, q, x)
TypeError: Invalid NaN comparison
>>> modified_subresultants_pg(p, q, x)
TypeError: Invalid NaN comparison
```

Also later in the sequence:

| expression | master | this PR |
|---|---|---|
| `subresultants_pg(x**4 - 1, x**2 - 1, x)` | TypeError | `[x**4 - 1, x**2 - 1]` |
| `subresultants_pg(4*x**3 + 3*x**2 + x + 2, 2*x + 2, x)` | TypeError | matches `subresultants()` |

## Root cause (formal chain)

1. `a2 = -rem(p, q) = 0`
2. `d2 = degree(0, x) = -oo` ⟹ `deg_diff_new = exp_deg - d2 = oo`
3. `deg_diff_new == 0` is False → incomplete-sequence denominator gets exponent `oo`; every `rho_list` entry is ±1 and `(-1)**oo = nan` in [redacted-repo] → `den = nan`
4. `sign(num/den) = sign(nan)`, and `StrictGreaterThan(S.NaN, 0)` raises `TypeError: Invalid NaN comparison`

The existing trailing cleanup `if subres_l[m-1] == nan ...` was intended for this but can never fire since `Expr.__eq__(nan)` is always False.

## Fix

Skip the Pell-Gordon variable updates and terminate as soon as a remainder is zero — both at the first-remainder step and in the main loop. This makes the output convention identical to `[redacted-repo].polys.polytools.subresultants`:

```python
>>> subresultants_pg(4*x**3 + 3*x**2 + x + 2, x + 1, x)
[4*x**3 + 3*x**2 + x + 2, x + 1]
```

## Validation

- new regression tests (5 common-factor pairs, first-step and main-loop termination)
- randomized fuzz: 60 pairs with guaranteed common factors — `subresultants_pg` ≡ `polytools.subresultants` on all, 0 crashes
- full `[redacted-repo]/polys` suite: 2364 passed

<!-- BEGIN RELEASE NOTES -->
* polys
  * Fixed a crash (``TypeError: Invalid NaN comparison``) in ``subresultants_pg`` and ``modified_subresultants_pg`` for polynomials having a common factor.
<!-- END RELEASE NOTES -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
