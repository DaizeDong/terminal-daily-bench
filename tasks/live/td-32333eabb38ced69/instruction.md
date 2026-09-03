# Basic dev

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

v0.2.0:

- fix matplotlib display error
- update 10+ solvers and automate the workflow
- remove dataset to [[redacted-repo]-dataset]([redacted-url])
- update statistics

<!-- CURSOR_SUMMARY -->
---

> [!NOTE]
> Release v0.2.0 with major functionality, data, and automation updates.
> 
> - Add 10+ new solvers (`bricks`, `corral`, `creek`, `diff_neighbors`, `dotchi_loop`, `hakoiri`, `hidoku`, `kuromasu`, `makaro`, `number_cross`, `skyscraper`, `snake`, `trinairo`, `yin_yang`) with corresponding parsers, verifiers, and visualization hooks
> - Introduce unified `[redacted-repo].solve()` API and extend parser registry (incl. Creek/Skyscraper formats)
> - Expand crawlers and register in `CrawlerFactory` (Battleship, Stitches, KenKen, Galaxies, Mathrax, CastleWall, DigitalBattleship, Putteria, Yajikabe, Koburin, Usoone, CocktailLamp, Nurimisaki, Nawabari, Tripletts, Doors)
> - Revamp benchmarking (`scripts/benchmark.py`): CLI flags, per-puzzle runs, new CSV/markdown outputs; add tests for new solvers
> - Update README: dataset moved to external repo, refreshed stats/table and quick start; ignore `assets/` and `benchmark_results/`
> - Bump package to `0.2.0` and add GitHub Actions workflow to test, build, and publish to PyPI on version tags
> 
> <sup>Written by [Cursor Bugbot]([redacted-url]) for commit [redacted-sha]. This will update automatically on new commits. Configure [here]([redacted-url]).</sup>
<!-- /CURSOR_SUMMARY -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
