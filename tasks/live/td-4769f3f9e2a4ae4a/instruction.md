# fix: Clear error for column-dropping categorical encoders

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

#### Reference Issues/PRs

[redacted-ref].

#### What does this implement/fix? Explain your changes.

`SMOTENC` crashes with an opaque NumPy error when the user passes a `categorical_encoder` that drops columns:

```python
import numpy as np
from sklearn.preprocessing import OneHotEncoder
from imblearn.over_sampling import SMOTENC

rng = np.random.RandomState(0)
n = 2000
X = np.hstack([
    rng.randn(n, 3),                  # continuous
    rng.randint(0, 2, size=(n, 1)),   # binary categorical
    rng.randint(0, 4, size=(n, 1)),
    rng.randint(0, 3, size=(n, 1)),
]).astype(object)
y = np.array([1] * 40 + [0] * (n - 40)); rng.shuffle(y)

SMOTENC(
    categorical_features=[3, 4, 5],
    categorical_encoder=OneHotEncoder(drop="first", handle_unknown="ignore"),
    sampling_strategy="minority", random_state=0,
).fit_resample(X, y)
# ValueError: zero-size array to reduction operation maximum which has no identity
```

**Root cause.** `SMOTENC._generate_samples` rebuilds the categorical features by activating exactly one column per categorical feature, slicing the encoded matrix into per-feature blocks sized from the number of categories:

```python
categories_size = [self.continuous_features_.size] + [
    cat.size for cat in self.categorical_encoder_.categories_
]
```

A `drop=` (or infrequent-merging) encoder emits **fewer** columns than `sum(cat.size)`. For categories `[2, 4, 3]` the code assumes 9 columns while the encoder actually emits 6 (`drop="first"`) or 8 (`drop="if_binary"`). The cumulative slices then run past the encoded width, the trailing block is empty, and `col_maxs.max(axis=1)` raises the `zero-size array` error. Even when it does not crash, dropping the baseline category means the "one active column per feature" reconstruction can no longer represent that category, so the synthetic categoricals are silently wrong — a column-dropping encoder is fundamentally incompatible with how SMOTENC works.

**Fix.** Validate the encoded width against the total number of categories in `_fit_resample` and raise an actionable `ValueError` that names the encoder and the column mismatch, instead of failing deep inside sample generation:

> SMOTENC requires a one-hot encoding with one column per category for the categorical features. The provided `categorical_encoder` produced N columns for M categories. This happens when the encoder drops columns (e.g. `OneHotEncoder(drop=...)`) or merges infrequent categories, which is not supported. Pass an encoder that keeps all categories, such as `OneHotEncoder(handle_unknown='ignore')`.

Since no currently-working configuration relies on a reduced-column encoder (they are all mis-sliced today), this changes a crash/silent-corruption into a clear error without affecting any valid usage.

If you'd prefer **full support** for infrequent-category encoders (which *are* a valid one-hot) rather than rejecting them, that can be done by deriving the per-feature widths from the fitted encoder instead of `cat.size` — happy to take that route instead if you'd rather.

#### Any other comments?

- Added a parametrized non-regression test (`drop="first"` and `drop="if_binary"`) in `test_smote_nc.py`.
- Added a changelog entry under `doc/whats_new/v0.15.rst`.
- Full `test_smote_nc.py` suite passes locally (23 passed) on scikit-learn 1.8.0.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
