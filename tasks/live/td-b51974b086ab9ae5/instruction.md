# Fix "@logger.catch()" ignoring errors raised by "athrow()"

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Fix [redacted-ref].

The unit tests are a quite convoluted (again, due to Python 3.5 syntax requirements and `asyncio` internals changing the traceback across versions), but in a nutshell the behavior can be tested with:

```python
import asyncio
from [redacted-repo] import logger

@logger.catch
async def generator():
    yield 0
    yield 1


async def main():
    gen = generator()

    # Just to skip the first yield.
    await gen.asend(None)

    try:
        await gen.athrow(ValueError("Bug"))
    except StopAsyncIteration:
        pass
    

asyncio.run(main())
``` 

Without `@logger.catch()`, we can observe the exception is raised from within the generator:

```
Traceback (most recent call last):
  ...
  File "/home/[redacted-repo]/Documents/code/[redacted-repo]/demo.py", line 5, in generator
    yield 0
ValueError: Bug
```

Therefore, it makes sense such exception to be caught when adding `@logger.catch()`. It wasn't the case prior to this PR.

Note that the `except StopAsyncIteration` it tests code are expected and not a problem. This is the usual way for CPython to signal end of iterations. It doesn't show up very much in production code since we use `async for gen(): ...` which handles it automatically. Here, such usage is not possible since we want to use `athrow()`. 

Note also that the example above use two `yield` just to make the traceback more comprehensible. If `athrow()` is called directly at the start, then the traceback will points to the `@logger.catch()` / `async def generator()` line:

```
Traceback (most recent call last):
  ...
  File "/home/[redacted-repo]/Documents/code/[redacted-repo]/demo.py", line 4, in generator
    async def generator():
ValueError: Bug
```

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
