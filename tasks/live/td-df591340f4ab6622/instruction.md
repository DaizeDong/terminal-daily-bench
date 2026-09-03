# v0.3.1 update

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

- new solvers
- (wip) new solver (cuts added model) for hitori, heyawake for worst case.

<!-- CURSOR_SUMMARY -->
---

> [!NOTE]
> **Medium Risk**
> Adds multiple new solvers and changes core solving infrastructure (new iterative MIP/cut loop) and the `hitori` implementation, which can affect correctness/performance and introduce new failure modes in solving/verification.
> 
> **Overview**
> Bumps [redacted-repo] to `0.3.1` and expands supported puzzle types by registering new parsers/verifiers/viz handlers and adding new solver implementations (e.g. `castle_wall`, `mejilink`, `mid_loop`, `kurotto`, `nurimisaki`, `aqre`, `canal_view`, plus `slitherlink_duality`).
> 
> Introduces an `IterativePuzzleSolver` base that uses OR-Tools MIP (`pywraplp`/SCIP) with cutting-plane iterations, adds MIP analytics and connectivity-cut utilities, and rewires `HitoriSolver` to the new iterative cut-based approach.
> 
> Updates tooling/docs: `scripts/benchmark.py` now consumes unified `{Puzzle}_dataset.json` assets and only verifies when a non-empty solution is present; adds `scripts/gen_mkdocs_nav.py` and nav markers in `mkdocs.yml`, tweaks plotting scaling, refreshes quick-start/README references, and adds a metadata-driven test harness with per-puzzle smoke tests.
> 
> <sup>Written by [Cursor Bugbot]([redacted-url]) for commit [redacted-sha]. This will update automatically on new commits. Configure [here]([redacted-url]).</sup>
<!-- /CURSOR_SUMMARY -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
