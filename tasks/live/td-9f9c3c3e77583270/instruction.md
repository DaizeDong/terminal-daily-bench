# fix: recognize list[UploadFile] as a multiple file field

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

`_get_fields_by_type` compares annotations with `==`, but `typing.List[X] == list[X]` is `False` even though both describe the same type (their `get_origin` and `get_args` are identical).

So for a field annotated `list[UploadFile]`:

- the `List[UploadFile]` lookup returns `[]`, so the field is never collected as a file **list**
- the plain `UploadFile` lookup still matches it (because `UploadFile` is in its `get_args`), so it is treated as a **single** file

`handle_files()` then reads it with `request.files.get()` instead of `request.files.getlist()`, and pydantic rejects the value — uploading multiple files returns 422 `"Not a valid file."` instead of 200. `t.Optional[list[UploadFile]]` is affected identically.

This adds a small `_is_same_type()` helper that compares generic aliases by their origin and arguments, and uses it for both the direct comparison and the `get_args` membership test. Bare types such as `UploadFile` and `FileStorage` have no origin, so they still fall back to `==` and existing behaviour is unchanged.

[redacted-ref]

Checklist:

- [x] Add tests that demonstrate the correct behavior of the change. Tests should fail without the change.
- [ ] Add or update relevant docs, in the `docs` folder and in code docstring.
- [x] Add an entry in `CHANGES.md` summarizing the change and linking to the issue.
- [ ] Add `*Version changed*` or `*Version added*` note in any relevant docs and docstring.
- [x] Run `pytest` and `tox`, no tests failed.

Notes on the unchecked items:

- No docs change: `list[UploadFile]` was already the documented, expected way to declare a multiple file field — this only makes it work.
- No `*Version changed*` note: the behaviour of `_get_fields_by_type` is unchanged for every annotation that already worked, so there is nothing to flag for users.
- I put the `CHANGES.md` entry under a `Version: Unreleased` heading rather than guessing the next version number — happy to retitle it to whatever you plan to release as.

Tests added:

- `tests/test_fields.py::test_multiple_file_model_with_builtin_list` — mirrors the existing `test_multiple_file_model` but with `list[UploadFile]`; posts two files and asserts a 200 with both received.
- `tests/test_helpers.py::test_get_fields_by_type_with_builtin_generics` — covers `list[UploadFile]` and `t.Optional[list[UploadFile]]` at the helper level.

Both fail on `main` and pass with the change. `pytest` gives 397 passed; the single failure, `tests/test_openapi_headers.py::test_spec_with_dict_headers`, also fails on a clean checkout here and is unrelated to this change. `ruff check` and `ruff format --check` are clean.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
