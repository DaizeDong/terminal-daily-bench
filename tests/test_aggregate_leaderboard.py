import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import aggregate_leaderboard as aggregate

# An ABSENT dependency is the only thing allowed to exempt a quality test.
# `if card is None: return` used to do that job, and it also swallowed every
# way _quality can legitimately return None on data it should have scored --
# a reduction that leaves fewer than two columns reports as a pass.
requires_quality = pytest.mark.skipif(
    aggregate._q is None,
    reason="terminal_daily_bench.quality is not importable in this environment")


def _write_result(root, name, integrity, task="td-0123456789abcdef", solved=True):
    payload = {
        "model": name,
        "task": task,
        "reward": 1.0 if solved else 0.0,
        "solved": solved,
    }
    if integrity is not ...:
        payload["false_accept_check"] = integrity
    (root / f"{name}-{task}.json").write_text(json.dumps(payload))


def _g(payload, model):
    """The published grid's row for `model`. There is exactly one grid."""
    mx = payload["matrix"]
    return next(r["g"] for r in mx["rows"] if r["model"] == model)


def test_missing_or_legacy_integrity_never_defaults_semantic_fa_to_zero(tmp_path):
    _write_result(tmp_path, "missing", ...)
    _write_result(tmp_path, "legacy", {"false_accept": 0})

    rows = aggregate.load(str(tmp_path), "codex")

    assert len(rows) == 2
    assert all(row["fa"] is None for row in rows)
    payload = aggregate.build_payload(rows, "2026-08-05")
    assert payload["total_fa"] is None
    assert payload["total_fa_n"] == 0
    assert all(row["codex"]["fa"] is None for row in payload["leaderboard"])
    assert payload["community"] == payload["community_verified"] == []
    assert payload["community_pending"] == []
    assert payload["community_suite"]["ranking_requires_complete_roster"] is True
    assert payload["community_suite"]["official_results_included"] is False


def test_explicit_semantic_exploit_measurement_is_aggregated_with_denominator(tmp_path):
    _write_result(tmp_path, "caught", {"semantic_false_accept": 1})
    _write_result(tmp_path, "clean", {"semantic_false_accept": 0})
    _write_result(tmp_path, "unmeasured", {
        "scope": "protected_test_replay_integrity",
        "false_accept": 0,
        "semantic_false_accept": None,
    })

    rows = aggregate.load(str(tmp_path), "claude-code")
    payload = aggregate.build_payload(rows, "2026-08-05")

    assert payload["total_fa"] == 1
    assert payload["total_fa_n"] == 2
    by_model = {row["model"]: row["claude-code"] for row in payload["leaderboard"]}
    assert by_model["caught"]["fa"] == 1 and by_model["caught"]["fa_n"] == 1
    assert by_model["clean"]["fa"] == 0 and by_model["clean"]["fa_n"] == 1
    assert by_model["unmeasured"]["fa"] is None
    assert by_model["unmeasured"]["fa_n"] == 0


def test_never_attempted_cell_is_null_not_zero(tmp_path):
    """A cell no run produced must not be published as a failure.

    This is the whole point of the tri-state `g`. `alpha` ran both tasks and
    failed one; `beta` was only ever run against the first. Before this, both
    of beta's cells read 0 and nothing in the artifact could tell "beta failed
    task two" from "beta was never pointed at task two".
    """
    _write_result(tmp_path, "alpha", ..., task="td-aaaaaaaaaaaaaaaa", solved=True)
    _write_result(tmp_path, "alpha", ..., task="td-bbbbbbbbbbbbbbbb", solved=False)
    _write_result(tmp_path, "beta", ..., task="td-aaaaaaaaaaaaaaaa", solved=False)

    payload = aggregate.build_payload(
        aggregate.load(str(tmp_path), "claude-code"), "2026-08-05")

    mx = payload["matrix"]
    assert mx["tasks"] == ["td-aaaaaaaaaaaaaaaa", "td-bbbbbbbbbbbbbbbb"]
    assert _g(payload, "alpha") == [1, 0]
    assert _g(payload, "beta") == [0, None]
    # the three states stay three states through a JSON round trip
    assert json.loads(json.dumps(payload))["matrix"]["rows"][1]["g"] == [0, None]


def test_every_row_is_as_long_as_the_task_axis(tmp_path):
    """A short row silently re-attributes every cell after the gap."""
    _write_result(tmp_path, "alpha", ..., task="td-aaaaaaaaaaaaaaaa")
    _write_result(tmp_path, "alpha", ..., task="td-bbbbbbbbbbbbbbbb")
    _write_result(tmp_path, "beta", ..., task="td-cccccccccccccccc")

    payload = aggregate.build_payload(
        aggregate.load(str(tmp_path), "claude-code"), "2026-08-05")

    n = len(payload["matrix"]["tasks"])
    assert n == 3
    assert all(len(row["g"]) == n for row in payload["matrix"]["rows"])


def test_payload_publishes_exactly_one_grid_for_the_best_covered_scaffold(tmp_path):
    """One grid, and no second copy of it under another key.

    `matrices` used to be emitted here as well: every scaffold's grid, keyed by
    scaffold. Nothing on the site read it, and because JSON has no references
    the primary grid was written into the payload a second time -- in a file
    `/`, `/quality/` and `/leaderboard/` all fetch before they can render.
    """
    _write_result(tmp_path, "alpha", ..., task="td-aaaaaaaaaaaaaaaa")
    rows = aggregate.load(str(tmp_path), "claude-code")
    (tmp_path / "t2").mkdir()
    _write_result(tmp_path / "t2", "alpha", ..., task="td-aaaaaaaaaaaaaaaa")
    _write_result(tmp_path / "t2", "beta", ..., task="td-bbbbbbbbbbbbbbbb")
    rows += aggregate.load(str(tmp_path / "t2"), "terminus-2")

    payload = aggregate.build_payload(rows, "2026-08-05")

    # primary is the best-covered scaffold -- a property of the data, not a name
    assert payload["matrix"]["scaffold"] == "terminus-2"
    assert "matrices" not in payload
    grids = [k for k, v in payload.items()
             if isinstance(v, dict) and "rows" in v and "tasks" in v]
    assert grids == ["matrix"]
    # and the non-primary scaffold is still fully described by `leaderboard`
    assert {e["model"] for e in payload["leaderboard"]} == {"alpha", "beta"}


@requires_quality
def test_quality_drops_unattempted_cells_instead_of_scoring_them_as_failures(tmp_path):
    """The MSQ card must not read a never-run cell as a solved=False.

    Two models, two tasks, one missing cell. Complete-case drops the task that
    carries the null; the card must then describe a 1x2 grid, and must say so.
    """
    _write_result(tmp_path, "alpha", ..., task="td-aaaaaaaaaaaaaaaa", solved=True)
    _write_result(tmp_path, "beta", ..., task="td-aaaaaaaaaaaaaaaa", solved=False)
    _write_result(tmp_path, "alpha", ..., task="td-bbbbbbbbbbbbbbbb", solved=True)

    rows = aggregate.load(str(tmp_path), "claude-code")
    card = aggregate._quality(rows, "claude-code")
    assert card is not None
    assert card["n_tasks"] == 1 and card["n_models"] == 2
    assert card["complete_case"] == {
        "unattempted_cells": 1, "tasks_dropped": 1, "models_dropped": 0}


@requires_quality
def test_the_complete_case_receipt_is_unconditional_not_only_when_it_reduced(tmp_path):
    """A page cannot guard on a key that only sometimes exists.

    The card's `n_tasks` / `n_models` are the axes of the REDUCED grid, and the
    site prints them beside the published matrix's own axes. The only field
    that can explain a difference is `complete_case`, so it has to be there on
    every card -- including the ones that dropped nothing. A receipt emitted
    only on the reducing path forces a consumer to treat "no reduction" and
    "old payload with no receipt at all" as the same state, and they are not:
    the second one cannot be trusted to have reduced.
    """
    for task in ("td-aaaaaaaaaaaaaaaa", "td-bbbbbbbbbbbbbbbb"):
        _write_result(tmp_path, "alpha", ..., task=task, solved=True)
        _write_result(tmp_path, "beta", ..., task=task, solved=False)

    card = aggregate._quality(
        aggregate.load(str(tmp_path), "claude-code"), "claude-code")

    assert card is not None
    assert card["complete_case"] == {
        "unattempted_cells": 0, "tasks_dropped": 0, "models_dropped": 0}
    # nothing dropped, so these ARE the published matrix's axes
    assert card["n_tasks"] == 2 and card["n_models"] == 2


def test_complete_case_prefers_dropping_the_axis_that_carries_the_nulls():
    """One model with a single run must not delete the whole task axis."""
    mx = {
        "tasks": ["t1", "t2", "t3"],
        "scaffold": "s",
        "rows": [
            {"model": "full-a", "g": [1, 0, 1]},
            {"model": "full-b", "g": [0, 0, 1]},
            {"model": "barely", "g": [1, None, None]},
        ],
    }
    matrix, t_drop, m_drop, unattempted = aggregate._complete_case(mx)

    assert unattempted == 2
    assert (t_drop, m_drop) == (0, 1)          # drop `barely`, keep all 3 tasks
    assert matrix == [[1, 0], [0, 0], [1, 1]]  # rows = tasks, cols = models
    assert all(cell is not None for row in matrix for cell in row)


def test_complete_case_breaks_a_tie_toward_dropping_the_task():
    """Equal null counts on both axes: the docstring promises the task loses.

    `_complete_case` says it prefers the task on a tie -- "an item run against
    only part of the field has no well-defined difficulty" -- and implements it
    as `worst_t[1] >= worst_m[1]`. Every other test in this file uses a fixture
    where one axis strictly outweighs the other, so flipping `>=` to `>` (the
    opposite of the documented rule, which silently changes which tasks are
    dropped from every published D / KR-20 / IRT number) left them all green.

    Here t2 carries one null and m1 carries the same one null: 1 vs 1. Under
    `>=` the task goes and a 1x2 grid survives; under `>` the model goes and a
    2x1 grid survives instead. Called directly, so no None-return can absorb it.
    """
    mx = {"tasks": ["t1", "t2"], "scaffold": "s",
          "rows": [{"model": "m1", "g": [1, None]},
                   {"model": "m2", "g": [0, 1]}]}

    matrix, t_drop, m_drop, unattempted = aggregate._complete_case(mx)

    assert (unattempted, t_drop, m_drop) == (1, 1, 0)
    assert matrix == [[1, 0]]        # rows = tasks: t1 kept, both models kept
