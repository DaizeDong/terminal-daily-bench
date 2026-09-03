# Fix sign errors in li(z).rewrite(Shi)/Chi and erfi(z).rewrite(expint)

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

#### References to other Issues or PRs

[redacted-ref]

#### Brief description of what is fixed or changed

This PR fixes two sign bugs in `[redacted-repo]/functions/special/error_functions.py`:

1. `li._eval_rewrite_as_Shi` / `Chi`: The formula used `- Shi(...)` instead of `+ Shi(...)`. Since `li(z) == Ei(log(z))` and `Ei(y) == Shi(y) + Chi(y)`, the `Shi` term must be added. The incorrect sign resulted in wrong numerical values across all test points (and introduced spurious imaginary components for real inputs like `z = 0.5`).
2. `erfi._eval_rewrite_as_expint`: The leading `sqrt(-z**2)/z` term was missing a minus sign. Fixing it to `-sqrt(-z**2)/z` brings it in line with `erfi(z).rewrite(uppergamma)` and removes an unwanted `+ 2.0*I` artifact when evaluating at `z = 2`.

Both rewrites now evaluate to the correct values when checked against `evalf`.

Changes:
- Corrected the signs in `_eval_rewrite_as_Shi` and `_eval_rewrite_as_Chi` for `li`.
- Added the missing minus sign to the leading term in `_eval_rewrite_as_expint` for `erfi`.
- Updated existing structural tests in `test_li` and `test_erfi`.
- Added multi-point numerical assertions against `evalf` for both functions.
- Updated affected doctests in `li`.

#### Other comments

#### AI Generation Disclosure

The bug search and the patch were created with Claude Code. However, I reviewed the changes and tests manually.

#### Release Notes

<!-- BEGIN RELEASE NOTES -->
* functions
  * Fixed incorrect signs in ``li(z).rewrite(Shi)``, ``li(z).rewrite(Chi)``, and ``erfi(z).rewrite(expint)``.
<!-- END RELEASE NOTES -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
