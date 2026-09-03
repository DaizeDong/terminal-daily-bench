# fix(models): handle zero masked patch count in random_inverse_block_mask ([redacted-ref])

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

### Summary of Changes

[redacted-ref].

In `[redacted-repo]/models/utils.py`, `random_inverse_block_mask` previously raised a `RuntimeError: uniform_ expects to return a [from, to) range, but found from=0 > to=-6.25e-07` when `mask_ratio` was `0.0` or small enough that `num_masked = int(num_patches * mask_ratio) == 0`.

### Root Cause
When `num_masked == 0`, `num_visible == num_patches`:
- `min_lar = max(log_aspect_ratio[0], math.log(num_visible / width**2))` evaluated to `0.0`.
- `max_lar = min(log_aspect_ratio[1], math.log(height**2 / (num_visible + 1e-5)))` evaluated to `-6.25e-7` due to the epsilon term.
- `torch.empty(1).uniform_(min_lar, max_lar)` failed because `min_lar > max_lar`.

### Solution
1. Explicitly handle the boundary case `if num_visible == num_patches:` by marking all patches visible (`visible.fill_(True)`), skipping the aspect-ratio sampling loop (consistent with sibling masking functions like `random_grid_token_mask`).
2. Added unit tests in `tests/models/test_ModelUtils.py` (`test_random_inverse_block_mask__mask_ratio_extremes`) verifying `mask_ratio=0.0`, `mask_ratio=0.05` (which rounds to 0 masked patches on a 16-patch grid), and `mask_ratio=1.0`.

### Testing
- `pytest tests/models/test_ModelUtils.py`: 88 passed, 8 skipped.
- `ruff check [redacted-repo]/models/utils.py tests/models/test_ModelUtils.py`: Passed.
- `ruff format --check [redacted-repo]/models/utils.py tests/models/test_ModelUtils.py`: Passed.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
