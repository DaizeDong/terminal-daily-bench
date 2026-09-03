# fix: jail extract_archive members to the destination

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

`extract_archive` strips a shared top-level directory from zip/tar members, then writes `destination / relative_path`. A member such as `pkg/../esc[redacted-repo]d.txt` becomes `../esc[redacted-repo]d.txt` after the strip, so the write lands outside `destination`.

`_fetch_from_pypi` downloads a PyPI sdist and calls `extract_archive`. A malicious or custom-index archive can write outside the extract cache.

## Change

- Resolve each extracted path and reject members that are not under `destination`.
- Keep the existing top-level-dir strip for happy-path sdists.
- Drop the unjailed `extractall` fallback.

## Test

`pytest tests/functional/utils/test_os.py::test_extract_archive_zip_strips_top_level_dir tests/functional/utils/test_os.py::test_extract_archive_zip_rejects_parent_esc[redacted-repo] tests/functional/utils/test_os.py::test_extract_archive_tar_rejects_parent_esc[redacted-repo]`

Revert-tested: without the jail, the zip esc[redacted-repo] test writes `dest.parent/esc[redacted-repo]d.txt`.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
