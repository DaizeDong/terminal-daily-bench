# fix(vlm): preserve spacing for Chandra br tags

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

Preserve spacing for `<br>` tags in Chandra OCR HTML output.

## Changes

- Replace `<br>` tags with a space before stripping HTML tags.
- Preserve the existing whitespace normalization behavior.
- Add a regression test for `<br/>` between text.

## Testing

Tested with the Chandra VLM parser.

Verified that:

- `Hello<br/>World` is parsed as `Hello World`.
- Existing Chandra VLM tests continue to pass.
- Ruff checks and formatting pass.

## Checklist

- [ ] Documentation has been updated, if necessary.
- [ ] Examples have been added, if necessary.
- [x] Tests have been added, if necessary.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
