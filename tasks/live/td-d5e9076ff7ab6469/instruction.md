# fix: list every artifact, not just json files

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

`LogReader.artifacts` only globbed `artifacts/*.json`, so anything written by
`text()`, `pickle()` or `bytes()` was invisible, as were nested categories.

- Lists every file under `artifacts/`, recursively
- Names now keep their extension, since `report.json` and `report.txt` would
  otherwise both come back as `report`
- Nested categories appear as `category/name.ext`
- `load_json` accepts the `.json` suffix as well as a bare name, so names
  taken straight from `artifacts` can be passed back to it
- Updated the API quick reference in the README to match

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
