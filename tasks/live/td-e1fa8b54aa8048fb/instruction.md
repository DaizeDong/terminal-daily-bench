# Adds cache_clear() function to clear the cache.

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Usage
```python
import asyncio
from cache import AsyncTTL

@AsyncTTL()
async def func(wait: int):
    await asyncio.sleep(wait)

async def usage():
    print("Start")
    await func(1)  # Cache miss
    print("Call func, cache miss")
    await func(1)  # Cache hit
    print("Call func, cache hit")
    func.cache_clear()
    print("call func.cache_clear() to clear cache.")
    await func(1)  # Cache miss
    print("Call func, cache miss")
    print("Done")

asyncio.get_event_loop().run_until_complete(usage())
```

Contains unittests for the cache_clear() method.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
