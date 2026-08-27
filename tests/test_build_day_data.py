"""`validate_day` is the last gate between a malformed day and a rendered page.

The failure mode it exists for is not a crash: it is a page that renders
*plausibly* from bad data. A solve row shorter than the task axis puts every
cell after the gap under the wrong task id, and a cell that is neither 1, 0 nor
null is truthy-tested downstream and becomes a solve. Both ship as a normal
looking table, so both are refused here.
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import build_day_data as bdd


def _day(**over):
    day = {
        "schema": bdd.SCHEMA_DAY,
        "date": "2026-08-19",
        "leaderboard": [{"model": "alpha", "claude-code": {"n": 2, "solved": 1}}],
    }
    day.update(over)
    return day


def _matrix(rows, tasks=("t1", "t2")):
    return {"tasks": list(tasks), "scaffold": "claude-code", "rows": rows}


def test_a_day_with_no_grid_still_validates():
    """Every shipped day predates the grid; absence is not a defect."""
    bdd.validate_day(_day(), "fixture")


def test_tri_state_grid_is_accepted():
    day = _day(matrix=_matrix([
        {"model": "alpha", "g": [1, 0]},
        {"model": "beta", "g": [0, None]},     # never attempted, NOT a failure
    ]))
    bdd.validate_day(day, "fixture")


def test_short_row_is_refused():
    day = _day(matrix=_matrix([{"model": "alpha", "g": [1]}]))
    with pytest.raises(SystemExit) as e:
        bdd.validate_day(day, "fixture")
    assert "1 cells for 2 tasks" in str(e.value)


def test_long_row_is_refused():
    day = _day(matrix=_matrix([{"model": "alpha", "g": [1, 0, 1]}]))
    with pytest.raises(SystemExit):
        bdd.validate_day(day, "fixture")


@pytest.mark.parametrize("cell", [True, False, 2, -1, 1.0, "1", "", []])
def test_a_cell_that_is_not_one_zero_or_null_is_refused(cell):
    """`True` is the dangerous one: it IS an int in Python, so an isinstance
    check would pass it, and it serialises back out as a fourth state."""
    day = _day(matrix=_matrix([{"model": "alpha", "g": [1, cell]}]))
    with pytest.raises(SystemExit) as e:
        bdd.validate_day(day, "fixture")
    assert "1, 0 or null" in str(e.value)


def test_every_scaffold_in_matrices_is_checked_not_just_the_alias():
    """`matrix` is only an alias for the primary scaffold. A grid that is wrong
    in a non-primary scaffold is still a wrong grid."""
    day = _day(
        matrix=_matrix([{"model": "alpha", "g": [1, 0]}]),
        matrices={
            "claude-code": _matrix([{"model": "alpha", "g": [1, 0]}]),
            "terminus-2": _matrix([{"model": "alpha", "g": [1]}]),
        },
    )
    with pytest.raises(SystemExit) as e:
        bdd.validate_day(day, "fixture")
    assert "terminus-2" in str(e.value)


def _legacy_docs(tmp_path, board):
    """A minimal docs/ tree `from_legacy` can convert."""
    (tmp_path / "leaderboard_data.json").write_text(
        json.dumps(board), encoding="utf-8")
    return tmp_path


def test_from_legacy_forwards_the_solve_grid_so_the_guard_can_reach_it(tmp_path):
    """Every day file this repo can produce is built by `from_legacy`.

    It used to assemble the day from a fixed list of keys that did not include
    `matrix`, so no day ever carried a grid, so the tri-state checks above
    asserted nothing on any real file -- `test_the_shipped_day_files_still_validate`
    passed vacuously for the grid half. A validator nothing can reach is not a
    validator, so this pins the wiring, not just the rule.
    """
    docs = _legacy_docs(tmp_path, {
        "date": "2026-08-19",
        "leaderboard": [{"model": "alpha", "claude-code": {"n": 2, "solved": 1}}],
        "matrix": _matrix([{"model": "alpha", "g": [1, None]}]),
    })

    day = bdd.from_legacy(docs)

    assert day["matrix"]["tasks"] == ["t1", "t2"]
    assert day["matrix"]["rows"][0]["g"] == [1, None]
    # absent stays ABSENT, not JSON null: a reader has to interpret a null,
    # and `validate_day` skips a key that is not a dict either way
    assert "matrices" not in day


def test_from_legacy_refuses_a_malformed_grid_instead_of_publishing_it(tmp_path):
    """The forwarding is only worth anything if the guard then fires."""
    docs = _legacy_docs(tmp_path, {
        "date": "2026-08-19",
        "leaderboard": [{"model": "alpha", "claude-code": {"n": 2, "solved": 1}}],
        "matrix": _matrix([{"model": "alpha", "g": [1]}]),
    })

    with pytest.raises(SystemExit) as e:
        bdd.from_legacy(docs)
    assert "1 cells for 2 tasks" in str(e.value)


def test_the_shipped_day_files_still_validate():
    days = sorted((ROOT / "docs" / "data" / "days").glob("*.json"))
    assert days, "no published day to check"
    for path in days:
        bdd.validate_day(json.loads(path.read_text(encoding="utf-8")), str(path))
