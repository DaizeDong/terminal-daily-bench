# Fix AttributeError when accessing sh.SignalException_SIGUSR1 / SIGUSR2

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Accessing `sh.SignalException_SIGUSR1` or `sh.SignalException_SIGUSR2` raised an `AttributeError` because the regex used to parse exception names (`SIG[a-zA-Z]+`) rejected digit suffixes, truncating `SIGUSR1` → `SIGUSR` before the `getattr(signal, ...)` lookup.

## Changes

- **`src/sh/__init__.py`**: Extend `rc_exc_regex` character class from `SIG[a-zA-Z]+` to `SIG[a-zA-Z0-9]+`, allowing digit-suffixed signal names to match in full.
- **`tests/sh_test.py`**: Add `test_signal_exception_sigusr` regression test asserting both `SignalException_SIGUSR1` and `SignalException_SIGUSR2` are accessible and are subclasses of `SignalException`.

```python
# Previously raised AttributeError: module 'signal' has no attribute 'SIGUSR'
sh.SignalException_SIGUSR1  # now works
sh.SignalException_SIGUSR2  # now works
```

References [redacted-ref], which removed these names from the stubs to work around the runtime crash rather than fixing it.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
