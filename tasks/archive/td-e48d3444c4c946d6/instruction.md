# Skip malformed device identifiers in handle_devreg_changes

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Problem

`[redacted-repo]DataUpdateCoordinator.handle_devreg_changes` unpacks every device identifier directly:

```python
for ident_type, ident_id in device_entry.identifiers:
```

Home Assistant device identifiers are *expected* to be `(domain, id)` 2-tuples, but a buggy integration can register a malformed one. In my setup the **Plejd** integration registered a device whose id string was stored as many single-character elements, e.g.:

```
('plejd', 'D', '8', '9', 'D', 'F', 'D', 'A', '6', '6', '1', '1', 'C', ':', ...)   # 24 elements
```

Because [redacted-repo] listens to *every* `device_registry_updated` event, this raised on each registry change and broke the whole handler:

```
Error running job: ... [redacted-repo]DataUpdateCoordinator.handle_devreg_changes ...
  File ".../custom_components/[redacted-repo]/coordinator.py", line 441, in handle_devreg_changes
    for ident_type, ident_id in device_entry.identifiers:
ValueError: too many values to unpack (expected 2, got 24)
```

The error fires on every restart / registry update. [redacted-repo] itself is only the messenger here (the root cause is the other integration's bad data), but one misbehaving integration shouldn't be able to break [redacted-repo]'s device-registry handling.

## Fix

Guard the unpack: skip identifiers that aren't 2-tuples (logging at `debug`) and keep processing the valid ones.

## Test

Adds `tests/test_coordinator.py::test_handle_devreg_malformed_identifier`, a lightweight unit test that drives `handle_devreg_changes` with a device carrying one malformed and one valid identifier. Verified it fails with `ValueError: too many values to unpack (expected 2, got 8)` on `main` and passes with this change.

> Note: I ran the new test locally against HA 2026.7.2. It passes. The autouse bluetooth fixture emits an unrelated scanner-teardown error in my throwaway env (same for pre-existing tests like `test_[redacted-repo]_device::test_make_name`), so I've left CI to run the full suite.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
