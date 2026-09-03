# Add biology_singlecell benchmarks (PBMC3k/68k) to benchmark knowledge base

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## What
Adds a `biology_singlecell` domain entry to `researchclaw/data/benchmark_knowledge.yaml`,
following the existing schema (keywords / standard_benchmarks / common_baselines).

- 3 benchmarks: `PBMC3k`, `PBMC3k-processed`, `PBMC68k-reduced` — all loaded via
  `scanpy.datasets.*` (already installed in `Dockerfile.biology`), all tier 1
  (self-caching calls under 6MB, no separate setup-phase download needed).
- 3 baselines: Leiden clustering, K-Means, Agglomerative clustering — all using
  packages already present in `Dockerfile.biology` (`pip: []` throughout).

Names/sizes/sample counts were checked against current scanpy documentation
rather than assumed. One thing worth a reviewer's eye: despite the name,
`pbmc68k_reduced` ships only a ~700-cell reduced subsample, not the full 68k
cells — flagged inline in the YAML comment so it doesn't surprise anyone later.

## Why
`benchmark_knowledge.yaml` currently covers 16 ML/DL subfields but no non-ML
domain, even though `Dockerfile.biology` and the `biology_*` domain profiles
show biology is an actively sandboxed domain. This is a narrowly-scoped first
increment for single-cell analysis specifically (matching the existing
`biology_singlecell` profile). Happy to follow up with other biology
sub-domains or other domains as separate PRs per the one-concern-per-PR
guideline in CONTRIBUTING.md.

## Tests
- Added `TestBiologySingleCellDomain` (4 tests) to `tests/test_benchmark_agent.py`:
  domain presence, keyword matching, tier/API-prefix correctness, and that no
  baseline needs a pip package beyond what `Dockerfile.biology` installs.
- `pytest tests/` passes locally (2868 passed, 56 pre-existing/unrelated skips).

## Scope
Additive only — no existing domains, agents, or schemas touched.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
