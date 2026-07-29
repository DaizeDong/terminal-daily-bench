# Validate format string keys in logger.add() for early error feedback

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

[redacted-ref]

When an invalid key is used in a format string passed to `logger.add()` (e.g., `format="{nonexistent}"`), the error previously only surfaced at **logging time** as a generic "Logging error in [redacted-repo] Handler" message with a bare `KeyError`. This made it difficult to identify and fix configuration issues, especially in larger applications where the error could go unnoticed.

This PR adds **early validation** of format string field names at `logger.add()` time:

- Parses the format string using `string.Formatter` to extract field names
- Validates each top-level field name against the known record keys (`elapsed`, `exception`, `extra`, `file`, `function`, `level`, `line`, `message`, `module`, `name`, `process`, `thread`, `time`)
- Raises a clear `ValueError` that identifies the invalid key, lists all available keys, and suggests using `logger.bind()` with `{extra[your_key]}` for custom data
- Only applies to static (string) format strings; callable/dynamic formats are not validated at `add()` time since their output depends on runtime state
- Nested access like `{level.name}` or `{extra[custom]}` is handled correctly by only validating the top-level key

### Before

```python
logger.add(sink, format="{nonexistent}")
logger.info("test")
# --- Logging error in [redacted-repo] Handler [redacted-ref] ---
# ...
# KeyError: 'nonexistent'
# --- End of logging error ---
```

### After

```python
logger.add(sink, format="{nonexistent}")
# ValueError: Invalid format: the field '{nonexistent}' does not correspond to any
# known record key. The available keys are: elapsed, exception, extra, file, function,
# level, line, message, module, name, process, thread, time. To use custom data, pass
# it via 'logger.bind()' and reference it as '{extra[your_key]}' in the format string.
```

## Test plan

- [x] Added parametrized tests for invalid format keys (`{nonexistent}`, `{foobar}`, `{unknown.attr}`, `{bogus[key]}`, etc.)
- [x] Added parametrized tests confirming all valid record keys still work (`{message}`, `{level.name}`, `{extra[custom]}`, `{thread.name}`, etc.)
- [x] Verified error message includes the invalid key name, lists available keys, and mentions `logger.bind()`
- [x] Confirmed dynamic (callable) formats are not validated at `add()` time
- [x] All existing tests continue to pass (1269 passed, only pre-existing multiprocessing sandbox failures unrelated to this change)

*This PR was developed with AI assistance (Claude). All changes have been reviewed and tested.*

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
