# Fix off-by-one in Bits length check

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

### Summary

`Bits.__init__` guards against a value too large for the requested bit length with `val > 2 ** len_`. The largest value representable in `len_` bits is `2 ** len_ - 1`, so the check is off by one: `2 ** len_` is wrongly accepted.

```python
>>> from [redacted-repo].mathutils import Bits
>>> b = Bits(4, 2)          # 4 needs 3 bits, but len_=2 is accepted
>>> b.as_bin()
'100'                        # 3 chars, though b.len == 2
>>> Bits(b.as_bin()).len     # doesn't round-trip
3
```

The over-long value silently violates the `len` / `__len__` / `__getitem__` invariant.

### Fix

Change `>` to `>=` so a value needing more than `len_` bits raises, exactly as the guard's own error message ("cannot be represented with N bits") promises. This mirrors the correct `>=` boundary already used in `__getitem__`.

The auto-computed branch (`len_ = len(f'{val:b}')` when `len_` is omitted) is unaffected: there `val < 2 ** len_` always holds, so the stricter comparison never fires. Only explicit-length overflows like `Bits(4, 2)` / `Bits(1, 0)` are newly (correctly) rejected; `Bits(3, 2)` — the true maximum — still works.

### Tests

Added `test_bits_len_bound`. Full suite passes locally (`pytest`, 446 passed).

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
