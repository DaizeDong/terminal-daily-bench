# Fix millisecond timeout parsing in link checker

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Hi,

This fixes timeout parsing in the standalone Markdown link checker.

`markdown-link-check` accepts timeouts in milliseconds as well as seconds, but `load_config()` previously stripped the unit and interpreted `1500ms` as 1,500 seconds. The updated parser converts millisecond values to seconds while preserving second-based and unitless configurations.

The PR also adds focused standard-library regression tests for both `60s` and `1500ms`.

Validation:

* `.venv/bin/python -m unittest discover -s tests -v`
* `.venv/bin/python -m compileall -q ci tests subprojects/statistics/scripts subprojects/validator/test_suite_mock.py`
* `.venv/bin/python ./ci/validate_md_links.py -c markdown-link-check_config.json` (all links valid, exit code 0)

The change is limited to the timeout parser and its tests.

Thanks in advance 😀

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
