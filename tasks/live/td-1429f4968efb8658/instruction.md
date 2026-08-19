# Edge-case hardening sweep: six long-standing crash/hang/correctness fixes

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

A review pass over [redacted-repo]' iteration, parsing, and rendering edge cases turned up six long-standing bugs: two non-termination hangs, three crashes, and one silent data corruption. One commit per fix, each with regression tests that fail on the pre-fix code.

- **tableutils**: `Table.to_text()` crashed three ways on degenerate input (`Table([[]])`, `None` headers, short header rows). Header rendering now mirrors `to_html`'s conventions, including no header row for empty headers.
- **timeutils/isoparse**: fractional seconds were parsed as literal integers, so `.851` became 851µs instead of 851000µs, silently corrupting the `isoformat()` round-trip the docstring promises. Over-precise fractions (>6 digits) now deliberately truncate.
- **timeutils/daterange**: any step that couldn't make progress toward `stop` looped forever: zero steps, self-cancelling month/day tuples like `(0, 1, -31)`, and wrong-direction steps. Replaced with a progress invariant: stationary steps raise `ValueError`, wrong-direction yields nothing like `range(1, 5, -1)`.
- **strutils**: `MultiReplace({})` raised `KeyError: None` on any input (empty pattern matches everywhere with no lastgroup). Now a no-op.
- **jsonutils**: `JSONLIterator` read in an infinite loop when a seek landed past the last newline; also fixes the `rel_seek` negative-normalization sign bug (`1.0 - rel_seek` mapped −0.3 to 1.3, past EOF). Resolves the old `TODO: seek to end?`.
- **iterutils**: `xfrange` assumed ascending iteration (descending ranges yielded nothing) and disagreed with `frange` on element counts at inexact float boundaries. Both now share `frange`'s deterministic count-based semantics; `frange`'s output is unchanged.

Full suite: 463 passed.

Supersedes [redacted-ref], [redacted-ref], [redacted-ref], [redacted-ref], [redacted-ref], and [redacted-ref], which were closed by their author and went stale; the fixes here were re-derived and generalized from an independent review of each underlying bug.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
