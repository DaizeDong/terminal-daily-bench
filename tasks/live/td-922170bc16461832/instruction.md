# Restore pathlib.Path support in iFrame

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref]

[redacted-ref] broke pathlib.Path support in IFrame._repr_html_() because html.escape() doesn't handle Path objects (it hits Path.replace() instead of converting to a string).

### Changes:

- Explicitly convert src to a string before passing it to html.escape().
- Add a regression test using a path with & to verify both conversion and escaping work as expected.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
