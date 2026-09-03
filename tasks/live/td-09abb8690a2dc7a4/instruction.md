# feat: add timing information to ic debugger

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
Implements timing functionality as a requested in [[redacted-ref]]([redacted-url])
Adds `ic.timer` which can be used as:

- **Decorator**: `@ic.timer` - prints function execution time
- **Context manager**: `with ic.timer:` - prints block execution time

## Example Output
```python
@ic.timer
def slow_function():
    time.sleep(1)

slow_function()
# ic| slow_function took 1.00s

with ic.timer:
    time.sleep(0.5)
# 500.12ms

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
