# Validate the resolved chunk_overlap for float values in TokenChunker

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

`TokenChunker` accepts `chunk_overlap` as either an int (a token count) or a float (a fraction of `chunk_size`), but the validation only covers the int case:

```python
if isinstance(chunk_overlap, int) and chunk_overlap >= chunk_size:
    raise ValueError("chunk_overlap must be less than chunk_size")
```

So a float that resolves to an overlap at or above `chunk_size` gets through. Since a float is multiplied by `chunk_size`, `chunk_overlap=1.0` with `chunk_size=100` becomes an overlap of 100, and things break later in `chunk()`:

```python
>>> from [redacted-repo] import TokenChunker
>>> TokenChunker(tokenizer="character", chunk_size=100, chunk_overlap=1.0).chunk("hello world " * 50)
ValueError: range() arg 3 must not be zero
```

That comes from the step in `_token_group_generator`:

```python
for start in range(0, len(tokens), self.chunk_size - self.chunk_overlap):
```

When the overlap equals `chunk_size` the step is zero. A larger fraction is worse in a quieter way: `chunk_overlap=1.5` makes the step negative, so the `range` is empty and the text comes back as zero chunks with no error at all.

The docstring already says the constructor raises `ValueError` when `chunk_overlap >= chunk_size`, so this is just making the float path honor that. The fix resolves the overlap to a token count first and then validates it, so int and float inputs go through the same check. I also rejected a negative resolved overlap, since that makes the step larger than `chunk_size` and silently skips tokens.

Valid fractions are unchanged: `chunk_overlap=0.2` with `chunk_size=100` still resolves to 20 and chunks normally.

Added tests for the out-of-range float, the negative case, and a valid fraction. Ran the token chunker suite locally and it passes.

<!-- This is an auto-generated comment: release notes by coderabbit.ai -->
## Summary by CodeRabbit

* **Bug Fixes**
  * Improved validation for fractional and negative token-overlap values.
  * Prevented overlaps equal to or larger than the configured chunk size.

* **Improvements**
  * Fractional overlap values are now consistently converted into token counts.
  * Valid fractional overlaps produce correctly sized, reliably overlapping chunks.
<!-- end of auto-generated comment: release notes by coderabbit.ai -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
