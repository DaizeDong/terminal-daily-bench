# Score children of beam states through their parents

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Second PR of the series (base = `feat/score-children-contract`, [redacted-ref]). Draft until [redacted-ref] is merged.

[redacted-ref] added the `Predictor.score_children` contract; this PR gives it a consumer, so the contract is not dead code.

## What

New option `use_child_scores` (default `False`) for `beam_mode="simple"`. When set, states of the next layer are scored by applying `Predictor.score_children` to states of the *current* layer, instead of applying the predictor to the states of the next layer themselves.

Scores are identical, but the predictor is called once per state of the current layer instead of once per child. For a model with one output per generator (Q-model) that is one forward pass instead of `n_generators` passes.

## How

The next layer is built by `_expand_layer`, which deduplicates exactly as `CayleyGraph.get_unique_states` does (sort by hash, keep first occurrence), but additionally returns:

* `source_index` — index of each surviving state in the output of `get_neighbors`, used to look up its score;
* `moves` — id of the generator that produced each state.

`get_neighbors` writes children generator-major, while `score_children` returns them state-major, so scores are transposed before being flattened into `get_neighbors` order. Keeping this provenance is the point: today the next layer is deduplicated as a flat set of states, which destroys the parent → move link. That link is needed by the two follow-up PRs (canonical deduplication and non-backtracking for `search_simple`).

A model whose `score_children` returns something other than `[n_states, n_generators]` is reported with a clear error.

## Scope

Only `beam_mode="simple"`; `use_child_scores=True` with `"advanced"` raises. In "advanced" mode states are additionally filtered against hashes of previous levels (which would have to re-index the scores), and that loop is being rewritten in [redacted-ref] upstream. `search_simple` is also where the follow-up PRs need the provenance.

Default behaviour is unchanged: with `use_child_scores=False` the code path is exactly the old one, and existing tests are untouched.

## Tests

* `use_child_scores=True` with the default predictor gives exactly the same beam as the old path — the found path and the per-step best scores match, both on a successful search and on a 50-step unsuccessful one (Hamming distance is integer arithmetic, so equality is exact).
* Parity: a model with one output per generator (Hamming distances of all children in one call) and its scalar equivalent produce identical beams on `lrx(8)`.
* Provenance: for every state of the expanded layer, applying `moves[i]` to the parent it came from reproduces that state; states and hashes equal those of `get_unique_states`.
* Errors/edges: wrong number of model outputs; `use_child_scores` in "advanced" mode; empty layer.

`./lint.sh` and `RUN_SLOW_TESTS=1 pytest` are green (330 passed / 12 skipped / 3 xfailed) on Python 3.12 and on Python 3.9 (torch 2.8); `black --check .` and `docs/build_docs.sh` are green.


---

Based on [redacted-ref], which is the base branch of this PR, so this diff is only its own change. [redacted-ref] should be merged first.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
