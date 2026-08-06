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
SHELL = (ROOT / "docs" / "assets" / "site.js").read_text(encoding="utf-8")
GENERATOR = (ROOT / "web" / "gen_pages.py").read_text(encoding="utf-8")


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


def test_stat_values_are_not_document_headings():
    assert "<p data-tdb-stat-value" in HOME
    assert "<p data-tdb-stat-value" in GENERATOR
    assert '<h2 class="mt-2 line-clamp-1 font-mono text-xl' not in HOME
    assert (
        '<h2 class="line-clamp-1 font-mono text-xl font-medium tabular-nums"'
        not in GENERATOR
    )

    generated = sorted((ROOT / "docs" / "benchmarks").glob("*/index.html"))
    generated += sorted((ROOT / "docs" / "registry").glob("*/index.html"))
    assert generated
    for page in generated:
        source = page.read_text(encoding="utf-8")
        assert "<p data-tdb-stat-value" in source, page
        assert (
            '<h2 class="line-clamp-1 font-mono text-xl font-medium tabular-nums"'
            not in source
        ), page


def test_mobile_menu_is_opaque_non_overlapping_and_accessible():
    assert "bg-fd-background px-4 py-3 lg:hidden" in SHELL
    assert 'menu.setAttribute("aria-hidden", open ? "false" : "true")' in SHELL
    assert 'pageMain.style.paddingTop = open ? head.offsetHeight + "px" : ""' in SHELL
    assert 'ev.key === "Escape"' in SHELL


def test_shell_mounts_a_real_footer_landmark():
    assert 'document.createElement("footer")' in SHELL
    assert 'footer.id = "tdb-footer"' in SHELL
    assert 'footer.setAttribute("aria-label", "Site footer")' in SHELL
    assert "document.body.appendChild(footer)" in SHELL


def test_homepage_integrity_limits_use_progressive_disclosure():
    assert "data-tdb-integrity-details" in HOME
    assert "integrity limits and current blockers" in HOME
    assert "Protected tests decide published scores" in HOME
    assert "deployment egress canary is still pending" in HOME
    assert "unpublished patched Harbor fork" in HOME
    assert "stock Harbor 0.13.1 is insufficient" in HOME
    assert "completed gate decisions only" in HOME


def test_homepage_previews_stay_short_and_link_to_full_views():
    assert "var BOARD_PREVIEW_LIMIT = 5;" in HOME
    assert "rows.slice(0, BOARD_PREVIEW_LIMIT)" in HOME
    assert "var TASK_PREVIEW_LIMIT = 3;" in HOME
    assert "scoped.slice(0, TASK_PREVIEW_LIMIT)" in HOME
    assert 'href="./leaderboard/">full leaderboard' in HOME
    assert 'href="./registry/">all tasks' in HOME
