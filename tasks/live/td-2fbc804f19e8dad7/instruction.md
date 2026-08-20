# funcutils: forward target-keyword-only args as keywords in wraps invocations

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

`wraps(g)(f)` builds a shim with `g`'s signature that calls `f`. When `f` declares a parameter keyword-only that `g` accepts positionally, the generated invocation passed it positionally and `f` raised `TypeError`. [redacted-ref]'s keyword-forwarding fixed the defaulted flavor as a side effect; still broken on master were:

- the non-defaulted flavor: `wraps(g)(f)(3, 4)` with `g(a, b)` / `f(a, *, b)`
- the varargs flavor: `g(a, b, *va)` / `f(a, *va, b)` (varargs force positional forwarding per [redacted-ref]'s rules)

The fix lives in the method that already owns invocation generation: `FunctionBuilder.get_invocation_str()` grows an optional `target` (the callable the invocation will call), and any arg that `target` only accepts as a keyword is forwarded `name=name`, overriding the positional rules. That override is safe even before `*varargs` — `_call(a, *va, b=b)` — precisely because a target-kw-only name can never collide with the target's positional slots. `update_wrapper` passes `wrapper` as the target; targets without introspectable signatures (e.g. some C callables) fall back to the [redacted-ref] behavior at wrap time.

An alternative to draft [redacted-ref], which reached the same diagnosis but inlined a modified copy of `get_invocation_str()` into `update_wrapper`, leaving the method itself as dead code on that path and calling `inspect.signature(wrapper)` unguarded.

Tests pin the [redacted-ref] repro (both wrap directions), the non-defaulted and varargs flavors (both fail pre-fix), and the uninspectable-target fallback. Full suite: 468 passed.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
