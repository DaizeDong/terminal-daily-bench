# fix(env): riichi requires 1000 points and 4 live tiles left

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

The after-draw mask misses two riichi preconditions (Tenhou rules, enforced by every mjai-compatible engine):

- No score check: a player below 1000 points can declare riichi, and `_accept_riichi` then drives the score negative.
- The 4-tiles-left rule in `red_mahjong` counts the wall with `next - last + 1`, but the mask is built before `_draw` decrements `next_deck_ix`, so the just-drawn tile is counted as still in the wall — riichi passes with 3 tiles left. Checked against libriichi on a real game: it reports `tiles left: 3` at the exact state where this formula gives 4. `no_red` has the normal-draw threshold right, but the same function serves its rinshan site, where the pointers are off by one in the other direction (stricter).

Fix: `_make_legal_action_mask_after_draw` takes `live_draws_left` explicitly — default derives the pre-decrement normal-draw count, rinshan sites pass the between-turns count — plus a `score[c_p] < 10` check (100-point units, matching `_accept_riichi`). Boundary tests (900/1000 points, 3/4 tiles) in `tests/red_mahjong/test_riichi_preconditions.py`.

The test failures on current main (`test_play.py`, `test_observe.py`) reproduce without this change.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
