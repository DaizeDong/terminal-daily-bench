# ⚡️ perf(quantity): answer the angular-unit check once per unit

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

`AbstractAngle.__check_init__` runs on every angle constructed, and cost ~138 µs of the ~221 µs that construction took. Almost none of it was the check:

```
dimension_of(angle instance)   138.1 us
dimension_of(unit)              70.9 us
unit.physical_type               0.9 us   <- the actual work
```

Two things are going on. `dimension_of(self)` forwards to `dimension_of(self.unit)`, so asking about the *instance* pays for two dispatches to reach a lookup that takes under a microsecond. And the answer depends only on the unit — an immutable value object, so one that is angular stays angular — which makes it answerable once per unit rather than once per angle.

## Result

```
u.Angle(1.0, "rad")   221.2 us -> 46.4 us     4.8x
u.Q(1.0, "rad")        45.9 us -> 45.5 us
```

Angle construction now costs what a plain `Quantity` does. The angle-specific overhead is **gone**, not merely reduced.

## Correctness

A non-angular unit is still rejected, and is **never cached** — so it is re-checked on every attempt rather than remembered as bad:

```pycon
>>> u.Angle(1.0, "m")
ValueError: Angle must have units with angular dimensions.
```

The cache is bounded by the distinct units a program constructs angles with, which is a handful.

## Why I was looking

Found while profiling [redacted-repo]/coordinax[redacted-ref], which canonicalises angular components on every chart transition. That PR had to reach for `AbstractQuantity._mk` — the unchecked constructor — specifically to avoid this cost. With this change the checked constructor is cheap enough that reaching past it is far less tempting.

## Verification

`pytest`: **4060 passed**, 49 skipped, 20 xfailed. `prek run --all-files` clean.

🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
