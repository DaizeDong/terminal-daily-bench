# fix(torch): apply quantile flip to autoregressive outputs in force_flip_invariance

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

### What

`force_flip_invariance` reverses the quantile axis of the flipped forecast (`forecast(-x)`) before averaging it against `forecast(x)`. In the PyTorch model the prefill outputs and the quantile spreads get flipped, but the autoregressive branch was concatenated without the flip:

```python
flipped_pf_outputs = flip_quantile_fn(flipped_pf_outputs)        # flipped
...
if flipped_ar_outputs is not None:
    to_cat.append(flipped_ar_outputs.reshape(...))               # not flipped
```

The Flax implementation flips all three, including `flipped_ar_outputs` (`[redacted-repo]_2p5_flax.py`). This adds the missing flip to the torch path.

### Impact

For horizons longer than one output patch (128 steps), the autoregressive region's quantile channels are misaligned in the flip-invariance average, so the prediction intervals there are wrong. The mean and median are fixed points of the quantile flip, so the point/median forecast is unaffected, which is likely why it went unnoticed. `force_flip_invariance` is on by default, and for long horizons the continuous quantile head is disallowed, so the affected bands are what gets returned.

### Test

Adds `tests/test_force_flip_invariance.py`. With `force_flip_invariance` the model satisfies `forecast(-x) == -flip_quantile(forecast(x))` at every horizon step, independent of the weights, so a random init is enough to check it. The test asserts this identity across the autoregressive region (steps 128:256). It fails before the fix (about 80% of the band values off) and passes after. Flip-invariance test passes; `ruff check` clean.

### Note — supersedes [redacted-ref]

This replaces [redacted-ref], which GitHub auto-closed after I botched a force-push: I amended the commit from a shallow clone, which dropped its parent and briefly turned the diff into the whole repo. Sorry for the noise — this PR is the same fix on a clean commit off `master`.

Addressing @rajatsen91's review on [redacted-ref]:

- The AR flip is now applied **after** `flipped_ar_outputs.reshape(batch_size, -1, self.model.q)`, as you suggested. I checked the shape: `ar_renormed_outputs` is `(batch, num_decode_steps, o, q)` (each AR step is `new_renormed_output[:, -1, ...]` stacked on dim 1), so `q` is already the innermost axis and flip-before vs flip-after is bit-identical here. Doing it after the reshape makes the quantile axis unambiguous at the flip site.
- Agreed on the `quantile_spreads`/continuous-quantile-head line — that block only reads `full_forecast` at the median index (5) and rebuilds the other bands from `quantile_spreads`, so the AR-region flip does not affect it.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
