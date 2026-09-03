# fix(ci): read a reviewer's findings when it forgets to escape a quote

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Problem

Findings quote source verbatim in `window`, and source is full of double quotes, so a reviewer regularly answers with

```json
"window": "  252:   elif [ -f "yarn.lock" ]; then\n ..."
```

which is not JSON. `_salvage_findings` cannot help — it *drops* a finding it cannot decode, and one quoting habit corrupts **every** window drawn from the same file, so a quote-dense diff loses the whole review rather than one finding of it.

The Correctness lane on [redacted-ref] died exactly that way: two findings, both quoting shell out of a workflow file, nothing salvaged, `[CI FAULT]` on a contributor's PR. Any PR touching a shell-in-YAML, JS or Python file is a candidate.

## Fix

Repair the block before falling back to salvage — but only when it can be read **one** way.

Escaping alone is not sufficient, because where a value *ends* is genuinely ambiguous:

```json
"window": "  919: [{"path": "a.py", "line": 1, "body": "real"}]"
```

reads just as well as a finding anchored at line 1 with the body `"real"` — fields scraped out of the quoted source. **That reading parses**, so parsing cannot be the test. Posting source out of a window as though it were a review comment is worse than posting nothing, so an ambiguous block is declined and the existing fault stands.

Not hypothetical: this repo's own `test_post_review_comments.py` contains a findings-shaped literal.

## Bounds

The uniqueness walk is bounded three ways, each for a failure it hit while being built:

| Bound | Failure it prevents |
|---|---|
| iterative, not recursive | one field was one frame; a runaway block raised `RecursionError` **past** the caller, losing findings salvage would have kept |
| branches charged to the step budget | a wide block spent **>2 min** building readings it never finished |
| declined past 64 string fields | the walk holds a copy of the reading per branch — a 1000-finding block cost **400 MB** |

After: pathological blocks decline in 0.4 ms / 23 MB, and still reach salvage.

## Verification

| Command | Result |
|---|---|
| `pytest .github/scripts/tests/` | **372 passed** |
| `ruff check .github/scripts/` | All checks passed |
| `ruff format --check .github/scripts/` | 23 files already formatted |
| workflow YAML parse | OK |
| end-to-end replay vs live [redacted-ref] diff | `repaired 2 finding(s)` → 2 postable, **exit 0** (was exit 2) |
| prompt render (heredoc) | `\"` survives verbatim into `full_prompt.txt` |

Real reviewer output from the failing run is captured as `fixtures/unescaped_quotes_response.txt`. The pre-existing `[redacted-ref]` fixture now recovers **3** findings instead of 2 — its old assertion had codified losing one to salvage, which its own docstring called a bug.

## Also

The output spec's example used single quotes throughout, so it never showed the model a double quote being escaped. Added that.

## Known, not fixed here (pre-existing)

`_salvage_findings` can itself scrape a findings-shaped object out of a window, and `post_review_comments.py:801` (`if not verified and finding.get("window")`) lets a **windowless** finding skip window verification and post. Both predate this branch, and this change strictly *reduces* how often salvage runs. Worth a follow-up — happy to take it.

---
🤖 Generated with CloudCode — session `ses_e5fc0adaa36ffeRd4j8cH5xVH6`

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
