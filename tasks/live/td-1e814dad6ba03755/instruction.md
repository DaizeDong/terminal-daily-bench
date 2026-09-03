# Fix divide-by-zero in rase() for zero-mean reference images

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- `rase()` raised a `RuntimeWarning: divide by zero` (and produced `inf` values) when the reference image had zero-mean bands (e.g. a fully black image or a band with all-zero pixels)
- Fixed by using `np.where` to set `rase_map` to `0.0` at pixels where `M == 0`, suppressing the numpy warning with `np.errstate`

## Test plan
- [ ] Verify `[redacted-repo].rase(img, img)` still returns `0.0`
- [ ] Verify `[redacted-repo].rase(np.zeros(...), non_zero_img)` no longer crashes or warns

[redacted-ref]

🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
