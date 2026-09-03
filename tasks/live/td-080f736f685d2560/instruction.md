# fix(llm): surface the real error when retries are exhausted, cap OSError backoff

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Three bugs in `LLMClient._call_with_retry`, all on the path where retries run out. They're separate symptoms but they live in the same ~40 lines and the fix for one is the fix for the others, so I've kept them together.

## The error gets thrown away when retries are exhausted

This is the one that actually bites users. On a persistent retryable status (429, 503, 529…), the loop runs out and raises a bare `RuntimeError`, dropping the `HTTPError` on the floor.

That matters because `preflight()` classifies failures by pulling the `HTTPError` back out of `RuntimeError.__cause__`:

```python
except RuntimeError as e:
    # chat() wraps errors in RuntimeError; extract original HTTPError
    cause = e.__cause__
    if isinstance(cause, urllib.error.HTTPError):
        ...
```

The cause was never set, so that lookup always missed. With a rate-limited key you got:

```
All models failed: All models failed. Last error: LLM call failed after 3 retries for model gpt-test
```

when the code has a perfectly good message sitting right there for exactly this case:

```
Rate limited - try again in a moment
```

Same story for 401/403/404 behind a retry. `doctor` and `preflight` both go through this, which I suspect is some of what was going on in [redacted-ref] and [redacted-ref].

The final attempt now re-raises the original exception instead of falling out of the loop. The trailing `RuntimeError` is unreachable for any sane `max_retries` now, but I left it as a guard for `max_retries <= 0` and chained it with `from last_exc` so it can't swallow context either.

### Heads up: part of this is a regression

The diagnostics here were already fixed once in [redacted-ref] ([redacted-sha], "track last error across retries"). The v0.5.0 release commit ([redacted-sha]) reverted it — silently, as far as I can tell, since it's a 318-file +42k/−8.6k commit and nothing in it mentions the retry path. `git log -S"last_err" -- researchclaw/llm/client.py` shows it going in and right back out.

I went a bit further than [redacted-ref] did: it tracked the error as a formatted *string* for the message, which reads better but still leaves `__cause__` unset, so `preflight()` stays broken. Keeping the exception object fixes both.

Might be worth a look at what else went out in that release commit.

## It sleeps after the last attempt

The `HTTPError` branch had no "is this the final attempt?" guard, so it slept the full backoff *after* the last try and then failed anyway. With the 300s ceiling plus 30% jitter that's up to ~390s of dead waiting per model, and `chat()` walks the whole fallback chain, so you pay it per model.

The `URLError` and `OSError` branches already guarded this with `if attempt < self.config.max_retries - 1`; `HTTPError` just never got it. N attempts now means N−1 sleeps.

## The backoff ceiling wasn't applied to connection errors

`_MAX_BACKOFF_SEC = 300` is described as a "5-minute ceiling for retry delays", and the `HTTPError` and `URLError` branches both `min()` against it. The `TimeoutError`/`OSError` branch didn't — it just did `retry_base_delay * (2**attempt)` and let it rip. Measured delays at `max_retries=12`:

```
1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024
```

That's a 17-minute sleep on a flaky connection, from the branch that catches `ConnectionResetError` and friends — i.e. exactly the transient case you'd want to recover from quickly. Now capped like the other two.

## Why the tests didn't catch any of this

The existing preflight tests patch `chat()` directly:

```python
with patch.object(client, "chat", side_effect=err):
    ok, msg = client.preflight()
```

So `test_preflight_429_rate_limited` passes while the real 429 path is broken — it never enters the retry loop at all. The new tests patch `_raw_call` instead, so they go through `_call_with_retry` for real, and they stub `time.sleep` to assert on the delays rather than actually waiting.

Added five: the HTTPError and URLError re-raise cases, preflight reporting a rate limit through the real path, the sleep count, and the backoff cap.

## Testing

`pytest tests/` → 2802 passed, 56 skipped. Same as before the change; the one warning is a pre-existing unawaited-coroutine thing in `test_servers.py`, unrelated.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
