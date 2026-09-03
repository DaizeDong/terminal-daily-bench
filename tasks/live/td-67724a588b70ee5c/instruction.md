# Fix `vacuum_lakehouse_tables` retention period formatting for single-digit hours

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

`vacuum_lakehouse_tables()` could generate an invalid `retention_period` when `retain_n_hours % 24 < 10` (for example `2:1:00:00`), which fails downstream validation requiring `d:hh:mm:ss`. This change ensures the hours segment is always zero-padded to two digits.

- **Root cause and behavior**
  - `retention_period` was built with an unpadded hour component in the vacuum helper path.
  - Values with single-digit hours produced invalid format and raised a `ValueError`.

- **Code change**
  - Updated retention period string construction to enforce two-digit hours:
    ```python
    # before
    retention_period = f"{retain_n_hours // 24}:{retain_n_hours % 24}:00:00"

    # after
    retention_period = f"{retain_n_hours // 24}:{retain_n_hours % 24:02d}:00:00"
    ```

- **Regression coverage**
  - Added a focused lakehouse unit test that verifies `retain_n_hours=49` is translated to `2:01:00:00` before calling `run_table_maintenance`.

<!-- START COPILOT CODING AGENT SUFFIX -->

- [redacted-ref]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
