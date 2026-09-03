# Add OCI detection via IMDS metadata server

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Add OCI detection via IMDS metadata server

`OCIProvider` previously only detected Oracle Cloud via the DMI vendor file
(`/sys/class/dmi/id/chassis_asset_tag`) and raised `NotImplementedError` for the
metadata server. This adds metadata-server detection so OCI is identified the
same way as the AWS/GCP/Alibaba providers.

### What it does
- `identify()` now runs `check_vendor_file() or await check_metadata_server()`.
- Queries the OCI instance metadata service (IMDS)
  `_get_metadata` / `_get_metadata_v2` structure:
  - `_get_metadata()` — GETs the v1 endpoint (`[redacted-url]).
  - `_get_metadata_v2()` — delegates to `_get_metadata` against the v2 endpoint
    (`.../opc/v2/instance/`) with the required `Authorization: Bearer Oracle` header.
  - Both run concurrently via `asyncio.gather`; `check_metadata_server()` returns `any(...)`.
- Confirms it's really OCI (not just any host on the shared `169.254.169.254`
  link-local IP) by checking the returned instance `id` starts with `ocid1.instance.`.

### Tests
- Added `test_valid_metadata_server_check` and `test_invalid_metadata_server_check`
  using `aresponses`, mirroring the AWS metadata tests.
- Full suite: 36 passed. `flake8 --max-line-length 100` clean.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
