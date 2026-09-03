# fix: Fitness rejects implausibly large finite log-likelihoods

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

## Summary

`Fitness.call` guarded `NaN` and `inf` log-likelihoods but passed any *finite*
value straight through, however physically impossible its magnitude. RAL pilot
`341908_5` (`slam_source_pix_nn`, free `AdaptSplit` on `DelaunayNN`) was killed by
exactly that hole: a non-positive-definite regularization matrix made the fp64
Cholesky return finite garbage (`log_l` up to `3e+303`), Nautilus accepted it as
its best point, `shell_log_l` reached `~1e56`, and `f_live` never terminated. The
run was ledgered as "0 calls / thrashes" when it had in fact made 90,000 calls
and reached maxL 30,701.

This adds a **magnitude ceiling** beside the existing isnan/isinf `where`s, so
any `|log_likelihood|` above it is mapped to `resample_figure_of_merit`. It lives
inside `call`, so every consumer inherits it — numpy, `_jit`, `_vmap`, Nautilus
`n_batch`, BlackJAXNUTS. `af.NSS` samples through its own inline JAX closure
rather than `Fitness.call`, so that closure moves into a module-level
`nss_log_likelihood_from` factory carrying the same guard: one implementation,
directly testable, and no test that merely resembles the sampled path.

The ceiling is read **once** in `Fitness.__init__` and kept as a static Python
float — the comparison it feeds is traced by JAX, so it cannot be a Python branch
and cannot be looked up per call. The value is coerced with `float` because
PyYAML parses a bare `1e20` as a *string* (it needs a decimal point or a signed
exponent to resolve a float).

Like the guards it sits beside, this is **value-only, never gradient**: under
`jax.grad` both branches of an `xp.where` are differentiated, so it cannot repair
a non-finite derivative. The existing caveat paragraph in the `call` docstring is
extended to say so explicitly.

## API Changes

Behavioural, opt-out via config, with no signature or import changes to anything
that existed before:

- `Fitness.call` now maps a finite `|log_likelihood|` above
  `general.test.log_likelihood_ceiling` to `resample_figure_of_merit`, in
  addition to the `NaN`/`inf` it already mapped. Default ceiling `1e20`, which is
  ~15 orders of magnitude above anything a real fit reaches, so no legitimate fit
  changes. Setting the key to blank (`null`) or `inf` restores the previous
  behaviour exactly.
- New config key `general.test.log_likelihood_ceiling` in the packaged
  `autofit/config/general.yaml`. A workspace whose `general.yaml` pre-dates the
  key inherits the `1e20` default rather than losing the guard.
- New public helper `autofit.non_linear.fitness.get_log_likelihood_ceiling()`
  reading that key, and `Fitness.log_likelihood_ceiling` holding the resolved
  static float.
- `af.NSS`'s inline log-likelihood closure is now built by
  `autofit.non_linear.search.nest.nss.search.nss_log_likelihood_from`, with the
  `-1e30` sentinel named as `NSS_INVALID_LOG_LIKELIHOOD`. Same numerics as
  before, plus the ceiling.

Downstream (PyAutoGalaxy / PyAutoLens / the workspaces) needs no change.

## Tests

- `test_autofit/non_linear/test_fitness_assertions.py` — numpy path: values above
  the ceiling (both signs) rejected, plausible values (including a real fit's
  ~3e4) passed untouched, the guard disabled by `inf`, the `NaN`/`inf` guards
  still intact, idempotence against a finite `-1e99` resample sentinel, and the
  config reader's coercion (string `"1e20"`, `null`, unparseable, non-positive,
  key absent).
- `test_autofit/non_linear/test_fitness_ceiling_jax.py` — `jax.jit` and
  `jax.vmap` paths, `pytest.importorskip`-gated. `vmap` is the load-bearing one:
  every parameter is a tracer there, so a ceiling that was not a static Python
  float would fail even where jit-on-concrete passed. Test values are chosen
  inside float32 range so the magnitude guard is what rejects them, not an
  overflow to `inf` caught by the isinf guard.
- `test_autofit/non_linear/search/nest/nss/test_log_likelihood_ceiling.py` — the
  NSS closure, via the real factory.

Full suite: **2337 passed, 3 skipped**.

## Notes

The upstream cause of the garbage likelihoods — `Adapt*` regularization squaring
its coefficient twice (λ⁴), driving the regularization matrix non-PD — is a
separate PyAutoArray task. This guard is the backstop that stops any such
numerical failure from silently burning a multi-hour run, whatever produces it.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
