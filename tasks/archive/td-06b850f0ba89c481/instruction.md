# Unpack the single type arg for Counter keys when unstructuring

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

`mapping_unstructure_factory`'s single-type-arg branch (comment: "Probably a Counter") assigns the whole `args` tuple to the singular `key_arg`:

```python
if len(args) == 2:
    key_arg, val_arg = args
else:
    # Probably a Counter
    key_arg, val_arg = args, Any          # <-- args, not args[0]
# ...
kh = key_handler or converter.get_unstructure_hook(key_arg, cache_result=False)
```

`get_unstructure_hook` expects a single type, but receives the 1-tuple `(KeyType,)`, which resolves to the identity hook. So a `Counter[KeyType]` whose keys need real unstructuring has its keys left unchanged.

The parallel **structure** factory handles the identical case correctly by unpacking:

```python
else:
    # Probably a Counter
    (key_type,) = args
```

## Reproduction

```python
from collections import Counter
from attrs import define
from [redacted-repo] import Converter

@define(frozen=True)
class Key:
    v: int

c = Converter()
c.register_unstructure_hook(Key, lambda k: k.v)
c.unstructure(Counter({Key(1): 5, Key(2): 3}), unstructure_as=Counter[Key])
# before: {Key(v=1): 5, Key(v=2): 3}   (keys not unstructured)
# after:  {1: 5, 2: 3}
```

## Fix

```diff
-        key_arg, val_arg = args, Any
+        key_arg, val_arg = args[0], Any
```

## Tests

Added `test_counter_unstructure_applies_key_hook`, which fails on the previous behavior (keys left un-unstructured) and passes with the fix. The existing `Counter[int]` tests are unaffected (integer keys use the identity hook either way).

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
