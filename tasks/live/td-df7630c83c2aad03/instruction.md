# refactor: share one repository walk so the C++ qn map cannot drift from the indexer

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Closes the last open acceptance criterion of [redacted-ref] for the `_eligible_rel_files` half of `qn.py`, and removes the duplication behind the [redacted-ref] coupling.

## The problem

`cpp_frontend/qn.py` carried its own copy of `GraphUpdater._collect_eligible_files`' walk. Its comment states the requirement plainly: *"Reproduce `GraphUpdater._collect_eligible_files`' ordering exactly"* — because the module-qn disambiguation rule hands the base qn to whichever file is seen **first** and appends an extension to the loser (`foo.cpp` -> `proj.foo`, `foo.h` -> `proj.foo.h`). A divergence in walk **order**, not just in which files are eligible, silently reassigns qualified names across the graph. Nothing raises. That is what [redacted-ref] was, twice.

The two copies shared their filter predicates (the [redacted-ref] fix) but not the loop, so nothing forced the orderings to stay equal.

## Why the existing tests did not cover it

`test_cpp_qn_map_exclude_unignore.py::TestParityWithTheIndexerWalk` compares `set(qn_map)` against the indexer's keys. A set comparison cannot see order, so a walk yielding the same files in a different order satisfies every one of those assertions.

Measured, not assumed. Reversing the `dirnames` sort in `qn.py` on `main`:

| mutation | existing suite | order guard added here |
|---|---|---|
| `dirnames` reversed | 9 passed | 3 failed |
| `os.walk(topdown=False)` | 9 passed | 3 failed |

Under the first mutation the two walks genuinely disagree (`ORDERS AGREE: False`, `SETS AGREE: True`).

To be precise about severity: that divergence is **latent today, not an active defect**. A basename collision needs an identical relative path minus suffix, hence the same directory, and within a directory the filename order is pinned by a hardcoded expectation in the existing suite. It stops being latent if the disambiguation rule ever widens, or if a caller starts depending on map insertion order.

## The change

One `walk_eligible_files` generator in `utils/path_utils.py`, next to the predicates it already shares. Both `_collect_eligible_files` and `build_module_qn_map` consume it, so they cannot drift by construction. The indexer's `_collected_dir_mtimes` bookkeeping is preserved through an `on_dir` hook. Net 72 lines of duplicated walk removed.

## Tests

`test_qn_walk_order_parity.py`, five tests in two classes:

- **`TestTheQnMapWalksInIndexerOrder`** — the qn map's key order equals the indexer's file order, under no filters, `--exclude`, and `.cgrignore` rescue.
- **`TestTheSharedWalkOrderIsPinnedAbsolutely`** — pins the order against a literal expectation.

The second class exists because of something the mutation testing showed: once both callers share one walk, **parity alone stops being a guard**. Mutating the shared definition moves both consumers together, so they keep agreeing and every parity assertion stays green. Verified: the `dirnames`-reversed mutation applied to the shared walk leaves all three parity tests passing. The absolute-order tests catch all three mutations (`dirnames` reversed, `filenames` reversed, `topdown=False`), each failing on the assertion that owns that property.

## Verification

- `8499 passed, 49 skipped` (full unit suite)
- 514 passed across the walk/ignore/exclude/incremental subset
- `ruff check` clean; `ty check` shows the same 2 pre-existing warnings as `main` (both at `graph_updater.py:2808`, unrelated)


<!-- This is an auto-generated comment: release notes by coderabbit.ai -->
## Summary by CodeRabbit

* **Bug Fixes**
  * Improved consistency between repository indexing and C++ module mapping.
  * Preserved deterministic, top-down file traversal order across supported operations.
  * Ensured exclusions, unignored paths, and skipped files are handled consistently.
  * Standardized module naming for regular files and package entry points.

* **Tests**
  * Added coverage verifying traversal order and parity under exclusion and unignore configurations.
  * Added checks for consistent module naming across supported file types.
<!-- end of auto-generated comment: release notes by coderabbit.ai -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
