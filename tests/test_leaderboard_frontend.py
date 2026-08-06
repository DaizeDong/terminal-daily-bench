"""Dependency-free structural fixtures for the static leaderboard JavaScript.

The release environment has no JavaScript runtime.  These tests pin the data
discovery, output escaping, and semantic-FA rendering paths in both inline
scripts so an unknown harness cannot silently disappear on the next edit.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOME = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
LEADERBOARD = (ROOT / "docs" / "leaderboard" / "index.html").read_text(
    encoding="utf-8"
)


def _fixture_harnesses(board: dict) -> list[str]:
    """Reference contract used only to make the structural fixture explicit."""
    reserved = {
        "model", "lead", "agent_org", "model_org", "effort",
        "date", "pr", "cost", "cost_usd",
    }
    seen: set[str] = set()
    out: list[str] = []

    def add(name: str, cell: object) -> None:
        if name in reserved or name in seen or not isinstance(cell, dict):
            return
        if not ({"n", "solved", "rate", "fa_n"} & set(cell)):
            return
        seen.add(name)
        out.append(name)

    for name, cell in (board.get("pooled") or {}).items():
        add(name, cell)
    for row in board.get("leaderboard") or []:
        for name, cell in row.items():
            add(name, cell)
    return out


def test_unknown_harness_fixture_requires_pooled_and_cell_union():
    hostile = '<vendor-agent data-x="&">'
    board = {
        "pooled": {
            "single_shot": {"n": 2, "solved": 1},
            hostile: {"n": 1, "solved": 1},
        },
        "leaderboard": [{
            "model": "fixture-model",
            "single_shot": {"n": 2, "solved": 1},
            hostile: {"n": 1, "solved": 1, "fa": 0, "fa_n": 3},
            "cell-only-harness": {"n": 1, "solved": 0, "fa": None, "fa_n": 0},
        }],
    }
    assert _fixture_harnesses(board) == [
        "single_shot", hostile, "cell-only-harness"
    ]

    for source in (HOME, LEADERBOARD):
        assert "function discoverHarnesses(" in source
        assert "Object.keys(pooled).forEach" in source
        assert "Object.keys(row || {}).forEach" in source
        assert "Object.create(null)" in source


def test_homepage_discovers_columns_and_escapes_unknown_harness_labels():
    assert "var harnesses = discoverHarnesses(board);" in HOME
    assert "esc(harnessLabel(key))" in HOME
    assert "rateCell(r[key])" in HOME
    assert "r.single_shot" not in HOME
    assert "r.terminus2" not in HOME


def test_full_board_discovers_rows_and_escapes_unknown_harness_labels():
    assert "var AGENTS =" not in LEADERBOARD
    assert "var harnesses = discoverHarnesses(b);" in LEADERBOARD
    assert "harnesses.forEach(function (key)" in LEADERBOARD
    assert "agent: harnessLabel(key)" in LEADERBOARD
    assert "td(textCell(e.agent))" in LEADERBOARD
    assert "' + esc(v) +" in LEADERBOARD
    assert "esc(label)" in LEADERBOARD  # unknown quality-card harness label


def test_semantic_false_accept_always_renders_as_fraction_or_dash():
    assert 'typeof board.total_fa === "number"' in HOME
    assert 'typeof board.total_fa_n === "number"' in HOME
    assert 'String(board.total_fa) + "/" + String(board.total_fa_n)' in HOME
    assert ': "\\u2014"' in HOME

    assert 'typeof s.fa === "number"' in LEADERBOARD
    assert 'typeof s.fa_n === "number" && s.fa_n > 0' in LEADERBOARD
    assert "hacks: measuredFa ? s.fa : null" in LEADERBOARD
    assert "hacks_n: measuredFa ? s.fa_n : null" in LEADERBOARD
    assert 'esc(e.hacks) + "/" + esc(e.hacks_n)' in LEADERBOARD
    assert "e.hacks == null" in LEADERBOARD
