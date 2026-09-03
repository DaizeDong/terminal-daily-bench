# fix: from_latlon mis-reads a lowercase forced zone letter as northern

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

`from_latlon(..., force_zone_letter=...)` derives the hemisphere straight from the forced letter without normalizing case:

```python
northern = (zone_letter >= 'N')
```

Every lowercase ASCII letter is `>= 'N'`, so a lowercase **southern**-band letter (c–m) is mis-classified as northern and the 10,000,000 m false-northing offset is dropped — a 10,000 km error. Uppercase letters, and lowercase northern letters (n–x), happen to work.

```python
>>> import [redacted-repo]
>>> [redacted-repo].from_latlon(-30, 10, force_zone_letter='M')[1]
[redacted-sha].78
>>> [redacted-repo].from_latlon(-30, 10, force_zone_letter='m')[1]
-[redacted-sha].22          # 10,000,000 m off; [redacted-repo].to_latlon() then rejects it
```

Lowercase letters are a supported input elsewhere: `to_latlon` and `check_valid_zone_letter` both `.upper()` the letter first, and the test suite already forces lowercase `'u'`. `from_latlon` was the lone case-sensitive spot.

Fix is `northern = (zone_letter.upper() >= 'N')`. This is the minimal change and leaves the returned letter's case untouched; if you'd rather normalize the forced letter to uppercase like `to_latlon` does, happy to switch to that.

Added `test_force_south_lowercase_letter` (mirrors `test_force_south` with a lowercase letter): red before, green after; full suite 165 passed.

---

Disclosure: this PR was authored by an AI coding agent (Claude Code) running on this account — it found the case-sensitivity mismatch, reproduced it, wrote the fix and the test, and wrote this description. The account holder reviews every change and is accountable for it, and the verification above is re-runnable from the diff. Happy to close it if it isn't the kind of contribution you want.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
