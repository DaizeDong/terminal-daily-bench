# Use the model's loss_default in pipeline() instead of the loss resolver's default

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

### Link to the relevant Bug(s)

[redacted-ref]

### Description of the Change

`_build_model_helper` unconditionally ran

```python
model_kwargs["loss"] = loss_resolver.make(loss, loss_kwargs)
```

so a `loss=None` was resolved to the loss resolver's default, `MarginRankingLoss(margin=1.0)`, and
handed to the model as a concrete instance. `Model.__init__` therefore never reached its
`loss is None` branch and a model's declared `loss_default` / `loss_default_kwargs` were silently
discarded — for 12 of the 40 registered models (ConvE, ComplEx, TuckER, QuatE, ProjE, PairRE, BoxE,
SimplE, ERMLPE, and the literal models).

The fix resolves the loss class from the model itself when the caller named none:

```python
if loss is None and not isinstance(model, Model):
    model_cls = model_resolver.lookup(model)
    loss = model_cls.loss_default
    loss_kwargs = {**(model_cls.loss_default_kwargs or {}), **(loss_kwargs or {})}
model_kwargs["loss"] = loss_resolver.make(loss, loss_kwargs)
```

Three deliberate details:

- It mirrors what `hpo_pipeline` already does (`model_cls.loss_default if loss is None else
  loss_resolver.lookup(loss)`), so `pipeline()` and HPO now agree on which loss a model is trained
  with.
- `loss_kwargs` passed *without* a `loss` are no longer dropped or applied to the wrong loss class:
  they now override the model's `loss_default_kwargs` entry by entry, in the same
  defaults-then-overrides spirit as the `model_kwargs.setdefault(...)` loop a few lines below.
- `model_kwargs["loss"]` is still always populated with an instantiated loss, so the result tracker's
  parameter logging (`# the loss was already logged as part of the model kwargs`) and the saved
  configuration keep working unchanged. Nothing outside this one block needed to move.

Precedence is unchanged where a loss *is* named, whether via the `loss` argument or via
`model_kwargs["loss"]`.

### Possible Drawbacks

**Results change for the 12 affected models.** Anyone who ran `pipeline(model="ConvE", ...)` without
naming a loss was training with `MarginRankingLoss` and will now train with `BCEAfterSigmoidLoss`.
That is the point of the fix, but it does mean previously recorded numbers for those models are not
reproducible on the new version without explicitly passing `loss="MarginRanking"`. It may be worth a
line in the changelog. Models inheriting `Model.loss_default` — TransE and most others — are bit-for-bit
unaffected, which `test_pipeline_loss_default_is_noop_for_margin_ranking_models` pins down.

A second, smaller change: `pipeline(loss_kwargs=..., loss=None)` used to configure a
`MarginRankingLoss` and now configures the model's own default loss. Passing a kwarg that the model's
default loss does not accept will now raise instead of quietly working. That seems strictly better than
the old behaviour, but it is a visible difference.

### Verification Process

Against `master` @ [redacted-sha] on Python 3.12 / PyTorch 2.13:

- Confirmed the bug first: the reproduction script in the linked issue prints `BCEAfterSigmoidLoss`
  for direct construction and `MarginRankingLoss` via the pipeline.
- Added five tests to `tests/test_pipeline.py` covering the default loss, the default kwargs, an
  explicit loss (both as `loss=` and inside `model_kwargs`), `loss_kwargs` without a `loss`, and the
  no-regression case for `MarginRankingLoss` models. They use `resolve_pipeline`, so they instantiate
  without training and run in under three seconds.
- Reverted the `api.py` change and re-ran: three of the five fail, the two that assert unchanged
  behaviour pass. So the tests do pin the fix rather than pass vacuously.
- `pytest tests/test_pipeline.py` → 26 passed, 1 skipped.
- `pytest tests -m 'not slow' -n 4` → 2274 passed, 182 skipped, 391 subtests passed. (One unrelated
  collection error in `tests/test_nn/test_representation.py`, `ModuleNotFoundError: No module named
  'PIL'`, from an optional extra missing in my environment; it reproduces on unmodified master.)
- `ruff format --check` and `ruff check` clean; `mypy --ignore-missing-imports src/[redacted-repo]/pipeline/`
  clean.
- `xdoctest -m src/[redacted-repo]/pipeline/api.py` and the four `python -m doctest` RST targets from
  `tox -e doctests` all pass.

### Release Notes

- Fixed an issue where `pipeline()` ignored a model's default loss function and always used
  `MarginRankingLoss` when no loss was explicitly given.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
