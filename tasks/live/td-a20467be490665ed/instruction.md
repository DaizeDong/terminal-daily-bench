# Fix TypeError when calling decorated methods with positional arguments

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

### Description
Calling decorated methods (such as `output()`) with positional arguments resulted in a `TypeError` (e.g., `TypeError: TerraformTest._cache.<locals>.cache() takes 1 positional argument but 2 were given`). This occurred because the `_cache` decorator's wrapper was defined to only accept `self` and `**kwargs`.

This PR fixes the issue by updating the decorator to:
1.  Accept both `*args` and `**kwargs`.
2.  Use `inspect.signature` to dynamically bind the arguments to the target function's signature. This ensures positional arguments are correctly mapped to their parameter names.
3.  Remove the `self` argument from the bound arguments before hashing to prevent the object's memory address from invalidating the cache.
4.  Maintain the early short-circuit when caching is disabled globally.

### Tests
*   Added `test_output_positional_arg` to `test/test_cache.py` to verify that calling `output()` with positional arguments works correctly when caching is enabled.

### Related Issues
*   [redacted-ref]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
