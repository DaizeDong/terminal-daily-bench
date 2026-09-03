# Add dense prism_omdm/oqdq/osds/oydy sample triangles

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary of Changes

Adds nine dense sample triangles derived from `prism`. Each is `load_sample("prism")` summed across every claim and aggregated to a given origin/development grain, keeping all four measures (`reportedCount`, `closedPaidCount`, `Paid`, `Incurred`) and staying incremental like `prism` itself.

Grains covered: the three matching pairs `prism_oqdq` / `prism_osds` / `prism_oydy`, plus the six mismatched pairs where origin is coarser than development - `prism_oqdm`, `prism_osdq`, `prism_osdm`, `prism_oyds`, `prism_oydq`, `prism_oydm`. (Monthly origin `prism_omdm` was dropped per review - a dense monthly triangle over 120 origins isn't a realistic reserving artifact, and `omdq` etc. aren't constructible since chainladder requires the origin grain to be coarser than development.)

Each sample is a CSV in `chainladder/utils/data/` plus a one-line `_manifest.py` entry, same as every other bundled dataset, so `load_sample`, `list_samples`, the docs table and `test_load_sample` pick them up automatically.

## Related GitHub Issue(s)

[redacted-ref].

## Additional Context for Reviewers

`test_sample_data.py` checks each sample against `load_sample("prism").sum().grain(...)` computed on the fly, so the CSVs can't drift from what they claim to be.

```
$ python -m pytest -q chainladder/utils/tests/ chainladder/core/tests/test_grain.py
206 passed, 1 skipped
$ python -m ruff format --check chainladder/utils/data/_manifest.py chainladder/utils/tests/test_sample_data.py
2 files already formatted
```

Row counts: oqdq 678, oqdm 1774, osds 197, osdq 370, osdm 992, oydy 55, oyds 107, oydq 203, oydm 555.

<!-- Do not edit anything below this. -->

## Checklist
- [x] I passed tests locally for both code (`uv run pytest`) and documentation changes (`uv run --directory docs jb build . --builder=custom --custom-builder=doctest`)

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
