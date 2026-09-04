# Rewrite log(sqr(x)) to 2 * log(abs(x)) to avoid underflow

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Taking the log of a squared product materializes the product first, and in float32 a product of a few hundred terms underflows to zero once squared, so `log(abs(sqr(prod(x))))` returns `-inf`. Shows up in GP code with a few hundred inducing points, on every backend.

`log(sqrt(x))` and `log(sqr(x))` are now one rewrite, so the square peels off and the existing `log(abs(prod(x))) -> sum(log(abs(x)))` case finishes the job before anything is squared. Dropping the `abs` is driven by a new `non_negative` flag on unary scalar ops instead of a hardcoded list, so `abs(exp(x))` folds too. `Sqrt` deliberately doesn't carry the flag: `sqrt(-0.0)` is `-0.0`, and dropping the `abs` there would flip the sign of a downstream division.

```python
x = pt.vector("x", dtype="float32")
f = [redacted-repo].function([x], pt.log(pt.abs(pt.sqr(pt.prod(x)))))
f(np.full(250, 0.7, dtype="float32"))  # -inf before, -178.3 after
```

[redacted-ref]. Sharing one rewrite means sharing the constant's dtype, which is what stops the `0.5` factor truncating to `0` on integer input.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
