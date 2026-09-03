# feat(exceptions): add __str__ method to HTTPError

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Add __str__ to HTTPError to return a human-readable string representation, and add corresponding unit tests for the new method.

[redacted-ref] 


Checklist:

- [x] Add tests that demonstrate the correct behavior of the change. Tests should fail without the change.
- [ ] Add or update relevant docs, in the `docs` folder and in code docstring.
- [x] Add an entry in `CHANGES.md` summarizing the change and linking to the issue.
- [ ] Add `*Version changed*` or `*Version added*` note in any relevant docs and docstring.
- [x] Run `pytest` and `tox`, no tests failed.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
