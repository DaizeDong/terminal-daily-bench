# fix(recur): apply BYHOUR, BYMINUTE, BYSECOND, BYYEARDAY and BYWEEKNO

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

`as_rrule()` passed nine keyword arguments to `dateutil.rrule.rrule()`. That constructor accepts `byhour`, `byminute`, `bysecond`, `byyearday` and `byweekno` too, so the engine could already compute them — they were simply never handed over, while being parsed, stored and re-serialised. An event kept the hour from `DTSTART` and the file round-tripped unchanged, which is why this looked like it worked.

Measured before and after, `DTSTART:20250715T140000Z`:

| RRULE | before | after |
|---|---|---|
| `FREQ=DAILY;COUNT=3;BYHOUR=9,17` | 15th 14:00, 16th 14:00, 17th 14:00 | 15th 17:00, 16th 09:00, 16th 17:00 |
| `FREQ=YEARLY;COUNT=2;BYYEARDAY=200` | 2025-07-15 | 2025-07-19, 2026-07-19 |

Three places needed the new keys, and missing any one of them fails differently: the model, the rule parser that splits comma-separated lists (without it, `BYHOUR=9,17` arrives as the string `'9,17'` and validation fails), and `_as_rrule_str`.

## Tests

`tests/types/test_recur_byparts.py`, 13 cases. Each part is asserted against `dateutil.rrule` given the same arguments rather than against a hand-written list — the expansion engine is the same one this library uses, so a hand-written expectation would only restate whatever the implementation produced.

Also pinned: the parts still round-trip to ics, a rule using none of them is byte-ident[redacted-repo] to before, and negative `BYYEARDAY` counts from the end of the year.

## Two things you should look at rather than take on trust

**A test asserted the bug.** `test_recur_extra_fields_preservation` checked that `BYYEARDAY` and `BYWEEKNO` arrive as unparsed extras — a description of this defect, written when they weren't modelled. Left alone it would have failed; changed carelessly it would have stopped testing anything. It now asserts they parse, and that a genuinely unknown key (`X-EXTRA`) is still preserved as an extra, which is what the test was really for.

**Snapshots are regenerated**, because `Recur`'s repr gained five fields. I checked that no occurrence actually changed: every `dtstart` in the updated snapshots is ident[redacted-repo] to the one it replaced — the diff is only the five empty lists appearing in the repr.

## CI note

`pre-commit run ty` fails on `[redacted-repo]/recur_adapter.py:84` with an unused-ignore warning. That is present on an untouched `main` — verified against a clean worktree of `upstream/main` — and is unrelated to this change, so I have not touched it. Every other hook passes. Suite: **1469 passed, 35 skipped**.

🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
