# feat: declare the ell_comps disk on EllProfile (PyAutoFit[redacted-ref])

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

> **Depends on [redacted-repo]/PyAutoFit[redacted-ref]** (`feat: project ell_comps onto its disk
> with an opt-in joint clipper`). This PR declares geometry that PyAutoFit[redacted-ref]
> introduces the machinery to read. Merge PyAutoFit[redacted-ref] **first** — without it
> `test_model_constraint.py`'s resolution tests reference
> `model.ball_constraint_index_pairs()` and `af.ClipperPriorBoxJoint`, which do
> not exist on `autofit` main. Task: PyAutoFit[redacted-ref].

`EllProfile.__model_constraint__` already *measures* how far outside the
ellipticity clamp a profile's `ell_comps` sit, but a measure cannot say how to fix
one. This declares the **structure** — the disk itself — which is what a search
needs to put a lane back inside it:

```python
__model_ball_constraints__ = ((("ell_comps",), convert.ELL_COMPS_MAGNITUDE_CLAMP),)
```

**The radius is the clamp (0.999), deliberately not `1 - margin`.** Between 0.999
and 1.0 the conversion to an axis ratio saturates, so the likelihood is flat in the
radial direction: a lane projected into that annulus would be moved from a region
the model rejects into one the optimizer cannot leave. Projecting onto the clamp
puts it exactly at the edge of the region where the radial gradient is alive again.

Declared once at `EllProfile`, which is the single assignment site for `ell_comps`,
so it reaches every elliptical light and mass profile (28 classes across
`ag.lp` / `ag.mp` / `ag.lmp`, asserted by a namespace sweep so a profile added later
is covered without editing a list). The spherical subclasses inherit the
declaration but pin `ell_comps` to an instance, so PyAutoFit resolves no free pair
and projects nothing.

**`validate_ell_comps` is untouched, on purpose.** The prompt's hard constraint:
making the guard fire on the traced path would turn a 20%-of-lanes condition into a
20%-of-lanes crash in the middle of multi-hour GPU fits, and would kill a
MultiStart search on exactly the lanes it is supposed to clip and move on from. A
dedicated test class pins its standalone-construction behaviour — still rejects
`|e| > 1` and the corner `(0.8, 0.8)`, still accepts the saturating annulus, still
returns early for a non-concrete magnitude.

**Also:** widens `AnalysisDataset.save_results`' catch from bare `AttributeError`
to `(AttributeError, af.exc.SamplesException, af.exc.FitException)` with a logged
warning, mirroring PyAutoLens[redacted-ref] line-for-line. Building the galaxies materializes
the maximum log likelihood sample as a model instance, which the model may reject;
writing an optional output file must never kill a completed fit before
`paths.completed()` is called (PyAutoFit[redacted-ref]).

## API Changes

Additive. `EllProfile` (and therefore every elliptical profile) gains the class
attribute `__model_ball_constraints__`. It is inert unless a search is configured
with `af.ClipperPriorBoxJoint` — no profile construction, evaluation, model
composition or identifier changes. `AnalysisDataset.save_results` now logs and
continues on two further exception types instead of propagating them.

See full details below.

## Test Plan

- [x] `test_autogalaxy/` full suite: **1144 passed** (45s)
- [x] `test_autogalaxy/profiles` + `test_autogalaxy/analysis`: 768 passed
- [x] `test_autolens/` against this branch: 553 passed (the declaration reaches
      lens models unchanged)
- [x] New coverage in `test_autogalaxy/profiles/test_model_constraint.py`: the
      namespace sweep (with a non-vacuity guard), the radius-is-the-clamp
      assertion, PyAutoFit resolving the declaration to `ell_comps_0`/`ell_comps_1`
      indices on a real lens model, the spherical case contributing no pair, an
      end-to-end projection of a lane at `|e| = 1.4`, and the four
      `validate_ell_comps`-is-unchanged assertions.
- [x] New coverage in `test_analysis_dataset.py`: `save_results` swallows and logs
      all three exception types and never writes `galaxies.json` (parametrised).
- [x] Unit tests are numpy-only — no `import jax`.

**Measured, on one cell.** With PyAutoFit[redacted-ref]'s clipper and an `Isothermal` lens
model, 200,000 uniform draws from the `ell_comps` prior box:

- outside the disk **before** projection: **21.57%** (analytic `1 - pi/4` = 21.46%)
- outside the disk **after** projection: **0.00%**

`ell_comps = (0.9, 0.9)` (`|e| = 1.2728`) projects to `|e| = 0.999000` with the
angle preserved and both members masked; the default `ClipperPriorBox` leaves it
where it is.

> **Heart gate.** `pyauto-heart readiness` is **RED** with the single red reason
> `release validation FAILED (stage integrate)` — a known, human-authorised
> override for this task, unrelated to this branch. Shipped to PR-open under that
> override only; **not merged**.

<details>
<summary>Full API Changes (for automation & release notes)</summary>

### Added
- `EllProfile.__model_ball_constraints__ = ((("ell_comps",), 0.999),)` — inherited
  by every elliptical light/mass profile. Read by
  `af.ClipperPriorBoxJoint` (PyAutoFit[redacted-ref]); inert otherwise.

### Changed Behaviour
- `AnalysisDataset.save_results` — the `galaxies.json` write now catches
  `(AttributeError, af.exc.SamplesException, af.exc.FitException)` and logs a
  warning, where it previously caught bare `AttributeError` and silently passed.
  A rejected maximum-log-likelihood instance no longer propagates out of
  `save_results` and costs the run its `.completed` marker (PyAutoFit[redacted-ref],
  mirrors PyAutoLens[redacted-ref]).

### Unchanged (asserted)
- `validate_ell_comps` — standalone-construction behaviour is deliberately
  identical, and pinned by test.

### Migration
- None. To use the projection:
  `search = af.MultiStartAdam(clipper=af.ClipperPriorBoxJoint())` once
  PyAutoFit[redacted-ref] is merged.

</details>

Generated by the [redacted-repo] agent workflow.

🤖 Generated with [Claude Code]([redacted-url])

[redacted-url]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
