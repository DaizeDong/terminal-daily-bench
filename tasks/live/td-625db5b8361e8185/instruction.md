# fix(isbn, iban, mac_address): raise ValidationError for non-string input

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

`ISBN`, `IBAN` and `MacAddress` register `_validate` as a **before** validator, so it runs ahead of `str_schema()` and receives the raw input. Each then calls a str-only method on it, so a non-string leaks out of validation instead of raising `ValidationError`:

```python
Book(isbn=[redacted-sha])     # TypeError: object of type 'int' has no len()
BankAccount(iban=12345)      # AttributeError: 'int' object has no attribute 'replace'
Network(mac_address=12345)   # AttributeError: 'int' object has no attribute 'encode'
```

`except ValidationError` does not catch these, so an int id, or a missing field arriving as `None`, crashes past the validation boundary instead of being reported as a validation error.

## Fix

There are four `with_info_before_validator_function` types. `DomainStr` is the one that gets it right:

```python
def _validate(cls, v: Any) -> DomainStr:
    if not isinstance(v, str):
        raise [redacted-repo]CustomError('domain_type', 'Value must be a string')
```

It annotates the input as `Any` — the truth for a before-validator — and checks. The other three annotate it as `str` and omit the check. This applies `DomainStr`'s pattern to each, following its message and error-type naming.

The 14 **after**-validator types (`ISIN`, `routing_number`, `payment`, …) are unaffected: `str_schema()` rejects non-strings before their `_validate` runs. `test_isin_requires_string` already asserts this contract, which is why it's the contract I matched.

**Return types are unchanged**, which is the reason for this route rather than the obvious alternative. Switching these three to after-validators (converging with the other 14) also fixes the bug — but it changes what `model_dump()` yields for `isbn`/`iban` from `str` to `ISBN`/`IBAN`. That felt like a separate decision, so this PR takes the `DomainStr` route, which is inert in that respect. Happy to switch if you'd rather converge on after-validators.

## On `MacAddress`

`test_format_for_mac_address` already carries `b'12.!4.5!.7/.#G.AB......'` and `float([redacted-sha])` as cases expecting `valid=False`, so the intent is on record. But the test body calls `MacAddress(mac_address)` first, and since `MacAddress` subclasses `str`, that stringifies the input before it reaches the validator — `MacAddress(b'12.!4')` is the *string* `"b'12.!4'"`. The non-string path those two cases were written for has never actually been exercised. Passing them the way a caller would, `Network(mac_address=b'...')`, gives `AttributeError` today.

I left that test as it is; the new tests cover the path directly.

## Tests

Repro against unmodified `main`, with `ISIN` and `DomainStr` as controls on the same inputs:

```
isbn         int:TypeError       None:TypeError       bytes:TypeError       float:TypeError
iban         int:AttributeError  None:AttributeError  bytes:AttributeError  float:AttributeError
mac_address  int:AttributeError  None:AttributeError  bytes:AttributeError  float:AttributeError
isin         int:ValidationError None:ValidationError bytes:ValidationError float:ValidationError  <- control
domain       int:ValidationError None:ValidationError bytes:ValidationError float:ValidationError  <- control
```

After the fix, all three broken rows look like the control rows.

Added `test_{isbn,iban,mac_address}_requires_string`, modelled on `test_invalid_domain_types`. Red before the fix (18 failures across the three parametrized cases), green after. Full suite `13548 passed`, no failures. `ruff check` / `ruff format` / `mypy` clean.

---

**Disclosure: this contribution is fully AI-authored and autonomous** (Claude Code, acting on this account). An AI found the bug, ran the repro, wrote the tests, and wrote this description; the human operator of this account did not hand-review the diff or run the tests. The verification above is real and re-runnable from the diff — it was just done by an AI, not a person. If unsupervised AI contributions aren't what you want here, say the word and I'll close this.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
