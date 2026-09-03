# Sanitize control characters in backup filenames

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- Replace ASCII control-character runs with `_` in backup filename sanitization.
- Add a regression test for CR/LF in generated backup filenames.

[redacted-ref].

## Validation

```text
.\.venv\Scripts\python.exe -m pytest tests\test_base_backup_module.py -q
```

This failed before the change because `_prepare_file_name()` returned the CR/LF unchanged.

```text
.\.venv\Scripts\python.exe -m pytest tests\test_base_backup_module.py tests\Backup\Intune\test_Applications.py -q
.\.venv\Scripts\python.exe -m pytest --cov-report=xml --cov=src/[redacted-repo] tests
uvx flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
uvx flake8 . --count --exit-zero --max-complexity=35 --max-line-length=127 --statistics
git diff --check
gitleaks detect --pipe --redact --verbose --no-color
```

Results:

- Focused tests passed: 4 passed.
- Full pytest passed: 133 passed.
- Critical flake8 gate returned 0.
- The non-failing style flake8 command reported existing warnings in untouched files: `src/[redacted-repo]/__main__.py` and `src/[redacted-repo]/[redacted-repo]lib/documentation_functions.py`.
- `git diff --check` passed.
- gitleaks found no leaks.

## Notes

I did not run against a real Intune tenant. The change is limited to the local filename sanitizer used before backup files are written.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
