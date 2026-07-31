# Fix string_to_int radix when alphabet_index is provided

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

`string_to_int` does not honour its own docstring: when an `alphabet_index` is supplied, the docstring states `alphabet` is ignored, but the implementation still uses `len(alphabet)` as the numeric base. If the caller passes an `alphabet_index` built from a different (longer) alphabet than the `alphabet` argument, the result is decoded in the wrong radix.

## Reproduction

```python
from [redacted-repo].main import string_to_int

hex_index = {c: i for i, c in enumerate("[redacted-sha]")}
# alphabet_index is base-16; per the docstring `alphabet` is ignored.
string_to_int("10", alphabet="[redacted-sha]", alphabet_index=hex_index)
# -> 10   (decoded base-10, because len("[redacted-sha]") == 10)
```

Expected `16` (the string `"10"` decoded base-16, per the supplied index). Correct usage where `alphabet` matches the index is unaffected:

```python
string_to_int("10", alphabet="[redacted-sha]")  # -> 16
string_to_int("1f", alphabet="[redacted-sha]")  # -> 31
```

## Cause

The docstring:

> The alphabet_index, if provided, should map each character to its index … If this is passed, `alphabet` is ignored.

But the base is taken from the `alphabet` argument regardless:

```python
alpha_len = len(alphabet)
```

So when `alphabet_index` is provided and `alphabet` is shorter than the index's true radix, the magnitude is wrong.

## Fix

Derive the radix from the supplied index instead:

```diff
     number = 0
-    alpha_len = len(alphabet)
+    alpha_len = max(alphabet_index.values()) + 1
     for char in string:
```

For any index built the documented way (`{char: idx for idx, char in enumerate(alphabet)}`), `max(values) + 1 == len(alphabet)`, so all existing behaviour is byte-for-byte unchanged. Only the mismatched case is corrected.

## Tests

Adds `test_string_to_int_ignores_alphabet_when_index_given`, which builds a base-16 index while passing a base-10 alphabet and asserts the result uses base 16. It fails on the current code (`10 != 16`) and passes with the fix. Full suite: 22 tests OK.

I couldn't find an existing issue or PR covering this — happy to fold it into one if I missed it.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
