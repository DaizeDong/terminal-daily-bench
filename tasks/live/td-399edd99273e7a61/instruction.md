# fix: hide Eurostat $DV_ bookmarks from the catalogue ([redacted-ref] part 1)

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Closes part 1 of [redacted-ref]. Parts 2-4 stay open — they all depend on moving Eurostat to `detail=full`.

## What is wrong

548 of Eurostat's 8,152 catalogue entries are not datasets. They are saved Data Browser views: annotated `DISSEMINATION_OBJECT_TYPE=EXTRACTION` / `EXTRACTION_TYPE=BOOKMARK`, referencing their parent's DSD, repeating its title verbatim. `search "internet activities"` returned `ISOC_CI_AC_I` six times.

They are not described anywhere in the payload: 510 of 548 carry no `<c:Description>`, 547 of 548 repeat the parent's title, and all 548 label their stored view `Default presentation`. Nothing tells a user what any of them selects.

## What changes

`catalog_hidden_id_pattern` in `portals.json`, declared for Eurostat only, read with `.get()` — the other 15 providers take the same code path byte for byte.

Measured on the live catalogue:

| | before | after |
|---|---|---|
| catalogue entries | 8,152 | 7,604 |
| ambiguous titles | 1,114 (13.7%) | 138 (1.8%) |
| bookmarks in `tree --scheme popul` | 113 | 0 |
| dataflows in scheme `cc` | 1,291 | 959 |

The +15% MRR this is worth was already measured: [`docs/search.md`]([redacted-url]) listed it among the open items, and the 2026-08-21 eval arm applied the very same filter ad hoc (`eval/results/2026-08-21/run_eval.py:36`). This makes it the shipped behaviour. No gold-set id is a `$DV_`, so the evals stay reproducible.

## Three decisions worth reviewing

**Filtered on read, never before `write_parquet`.** The ids do serve data — `data/LFST_HHEREDCH$DV_1343` returns HTTP 200 and an 8,136-row sub-cube of a 102 MB parent — and the Data Browser hands them out in links. Filtering at build time would drop them from the Parquet and make them permanently unreachable. `resolve_dataflow` falls back to the unfiltered catalogue when nothing else matches, so an id typed verbatim still resolves.

**The catalogue filter alone was not enough.** Eurostat categorises the bookmarks like any dataflow, and `tree` joins the categorisation `how="left"`, so 113 survived in `--scheme popul` after the first fix. `load_categories` now applies the same filter on read, which also corrects the per-scheme counts and `siblings`.

**The pattern is anchored on the `$`.** Real dataflows such as `GBV_DV_AGE` contain `DV_`; a naive substring filter would have eaten them. A test fixes this.

Verified across the whole catalogue that the id is an exact proxy for the annotation: 548 `$DV_`, 548 `EXTRACTION`, no entry in one set and not the other, and no other id containing `$`.

## Behaviour changes, all Eurostat-only

- `all_available()` returns 7,604 rows instead of 8,152 — `_include_hidden=True` restores the full list.
- `siblings` on a bookmark id now returns nothing (the parent still works).
- `get` on a bookmark id still returns HTTP 404, unchanged: under `detail=allstubs` Eurostat sends no structure reference, so the DSD is guessed from the dataflow id — true for datasets, false for bookmarks. Fixed in part 3.

No schema change, so existing Parquet caches stay valid and nothing needs invalidating.

## Checks

`ruff check src tests`, `mypy src`, 399 tests (4 new). `ruff check .` also reports 4 pre-existing errors under `scripts/` — dead code, untouched.

Measurements behind this: [redacted-url] and [redacted-url]

🤖 Generated with [Claude Code]([redacted-url])

[redacted-url]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
