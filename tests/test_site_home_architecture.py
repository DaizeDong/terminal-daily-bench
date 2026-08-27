"""The home-page gates must fail when the home page stops leading with results.

Two checks in `verify_site.check_public_frontend` used to encode the previous
home architecture directly: a literal `data-tdb-section` list, and a caveat
loop that required ten integrity substrings to be present in `index.html`
specifically. Both were rewritten when the home page was rebuilt to put the
leaderboard first.

A rewritten gate is exactly where a gate goes vacuous -- the cheapest way to
make a red check green is to loosen it until nothing can fail it, and this
repo has been bitten by that before. So every clause below is pinned by a
mutation: break the thing the gate exists to catch, and assert the gate fires.

The third group pins a RELOCATION. The scoring invariant ("protected tests
decide published scores; a submitted reward is only a claim") lived on the home
page only. Concision moved the detail off home, so the assertion is written as
presence somewhere under `docs/` rather than on a named page: moving the home
of a statement again stays legal, losing it does not.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import verify_site  # noqa: E402

# The load-bearing halves of the scoring invariant. Not the whole sentence:
# pinning the full prose would forbid copy-editing, and the point is that the
# STATEMENT survives, not that one wording does. Both fragments are lowercase
# because the scan folds case.
SCORING_INVARIANT_FRAGMENTS = (
    "scoring invariant",
    "protected tests decide published scores",
)


def _published_html(root: Path) -> str:
    """Every published page, lowercased, as one haystack."""
    return "\n".join(
        page.read_text(encoding="utf-8", errors="replace").lower()
        for page in sorted(root.rglob("*.html"))
    )


def _missing_invariant(root: Path) -> list[str]:
    return [f for f in SCORING_INVARIANT_FRAGMENTS if f not in _published_html(root)]


# --------------------------------------------------------------------------
# results-first section order
# --------------------------------------------------------------------------

def test_results_first_layout_passes():
    # The masthead may sit above the table; nothing else may.
    assert verify_site.check_home_section_order(["leaderboard", "tasks"]) == []
    assert verify_site.check_home_section_order(["intro", "leaderboard"]) == []
    assert verify_site.check_home_section_order(
        ["intro", "leaderboard", "tasks", "status"]) == []


def test_the_layout_this_gate_replaced_now_fails():
    # The exact list the gate used to REQUIRE: intro, status, leaderboard,
    # tasks. If this passes, the rewrite changed nothing.
    problems = verify_site.check_home_section_order(
        ["intro", "status", "leaderboard", "tasks"])
    assert any("results are not first" in p for p in problems)


def test_pushing_the_table_below_an_explainer_fails():
    problems = verify_site.check_home_section_order(
        ["intro", "methodology", "leaderboard"])
    assert any("results are not first" in p for p in problems)


def test_renaming_the_explainer_does_not_buy_a_pass():
    # A name-based ban ("status may not precede") would be defeated by a
    # rename. The check is positional, so an invented name fails too.
    problems = verify_site.check_home_section_order(
        ["intro", "brand-new-block-name", "leaderboard"])
    assert any("results are not first" in p for p in problems)


def test_deleting_the_leaderboard_fails():
    problems = verify_site.check_home_section_order(["intro", "status", "tasks"])
    assert any("exactly one" in p for p in problems)


def test_two_leaderboards_fail():
    problems = verify_site.check_home_section_order(["leaderboard", "leaderboard"])
    assert any("exactly one" in p for p in problems)


def test_empty_home_fails():
    # A markup change that drops every data-tdb-section attribute would
    # otherwise satisfy an order check trivially -- vacuously green.
    problems = verify_site.check_home_section_order([])
    assert any("no data-tdb-section blocks" in p for p in problems)


def test_duplicate_section_names_fail():
    problems = verify_site.check_home_section_order(
        ["intro", "leaderboard", "tasks", "tasks"])
    assert any("duplicate" in p for p in problems)


def test_max_index_leaves_room_for_a_masthead_only():
    # Guards the constant itself: raising it is how this gate would be
    # loosened back into meaninglessness.
    assert verify_site.HOME_LEADERBOARD_MAX_INDEX == 1


# --------------------------------------------------------------------------
# retired marketing copy
# --------------------------------------------------------------------------

def test_clean_home_copy_passes():
    assert verify_site.check_retired_home_copy("leaderboard\nrank model score") == []


def test_ban_list_is_not_empty():
    assert verify_site.RETIRED_HOME_PHRASES


@pytest.mark.parametrize("phrase", verify_site.RETIRED_HOME_PHRASES)
def test_each_retired_phrase_fires(phrase):
    problems = verify_site.check_retired_home_copy(f"<p>{phrase}</p>")
    assert any(phrase in p for p in problems)


@pytest.mark.parametrize("phrase", verify_site.RETIRED_HOME_PHRASES)
def test_each_retired_phrase_is_genuinely_gone(phrase):
    # A ban on copy that is still shipped is a gate that fails on day one; a
    # ban on copy that never existed catches nothing. Either way the list must
    # be audited against the real site, not guessed.
    assert phrase not in _published_html(verify_site.DOCS)


# --------------------------------------------------------------------------
# integrity caveats: relocated off home, not dropped
# --------------------------------------------------------------------------

def test_shipped_site_still_publishes_every_integrity_caveat():
    assert verify_site.check_integrity_caveats(_published_html(verify_site.DOCS)) == []


@pytest.mark.parametrize("phrase", verify_site.INTEGRITY_CAVEATS)
def test_losing_any_integrity_caveat_fires(phrase):
    haystack = _published_html(verify_site.DOCS).replace(phrase, "")
    problems = verify_site.check_integrity_caveats(haystack)
    assert any(phrase in p for p in problems)


def test_integrity_caveat_list_did_not_shrink():
    # The relocation moved these ten phrases from index.html to the whole
    # site. Widening WHERE they may live is the change; dropping any of them
    # is not, and would be invisible without this count.
    assert len(verify_site.INTEGRITY_CAVEATS) == 10


# --------------------------------------------------------------------------
# the scoring invariant must survive somewhere
# --------------------------------------------------------------------------

def test_scoring_invariant_is_published_somewhere():
    missing = _missing_invariant(verify_site.DOCS)
    assert not missing, (
        "the scoring invariant is published on no page under docs/: "
        f"missing {missing}. Protected tests decide published scores; a "
        "submitted reward is only a claim. This site's results are not "
        "certified, so that disclosure is load-bearing. It may live on any "
        "page -- it may not live on none."
    )


def test_scoring_invariant_check_fires_when_the_site_loses_it(tmp_path):
    # Mutation: a whole site that never states the invariant.
    (tmp_path / "index.html").write_text(
        "<h1>Terminal Daily</h1><table></table>", encoding="utf-8")
    assert _missing_invariant(tmp_path) == list(SCORING_INVARIANT_FRAGMENTS)


def test_scoring_invariant_may_move_between_pages(tmp_path):
    # Mutation in the other direction: home says nothing, a second page carries
    # it, and the assertion still passes. Relocation is legal by construction.
    (tmp_path / "index.html").write_text(
        "<h1>Terminal Daily</h1><table></table>", encoding="utf-8")
    deep = tmp_path / "benchmarks"
    deep.mkdir()
    (deep / "index.html").write_text(
        "<p>Scoring invariant. Protected tests decide published scores: "
        "deterministic code re-lays and executes them; a claimed reward "
        "never is.</p>",
        encoding="utf-8",
    )
    assert _missing_invariant(tmp_path) == []


def test_partial_loss_of_the_invariant_fires(tmp_path):
    # Keeping the heading while deleting the sentence would read as compliant
    # to a one-fragment check.
    (tmp_path / "index.html").write_text(
        "<p>Scoring invariant.</p>", encoding="utf-8")
    assert _missing_invariant(tmp_path) == ["protected tests decide published scores"]


# --------------------------------------------------------------------------
# the gates must still be WIRED
# --------------------------------------------------------------------------
#
# Every test above exercises a pure function. A pure function whose call site
# has been deleted passes all of them and guards nothing -- that is the precise
# shape of a vacuous gate. These three drive `check_public_frontend`, the
# function the site check actually runs, with a mutation planted in the
# constant, and require the complaint to come out the far end.

def test_section_order_gate_is_wired(monkeypatch):
    # Force the property to be unsatisfiable: no index may be <= -1.
    monkeypatch.setattr(verify_site, "HOME_LEADERBOARD_MAX_INDEX", -1)
    assert any("results are not first" in p
               for p in verify_site.check_public_frontend())


def test_retired_copy_gate_is_wired(monkeypatch):
    # "terminal" appears on the home page, so a ban on it must be reported.
    monkeypatch.setattr(verify_site, "RETIRED_HOME_PHRASES", ("terminal",))
    assert any("retired marketing panel returned" in p
               for p in verify_site.check_public_frontend())


def test_integrity_caveat_gate_is_wired(monkeypatch):
    monkeypatch.setattr(
        verify_site, "INTEGRITY_CAVEATS",
        ("a caveat no page under docs has ever published",))
    assert any("integrity caveat lost from the whole site" in p
               for p in verify_site.check_public_frontend())


# --------------------------------------------------------------------------
# nothing explanatory above the table
# --------------------------------------------------------------------------
#
# `check_home_section_order` counts sections, so a home page whose single
# pre-table block is an explainer rather than a masthead still keeps the
# leaderboard at index 1 and passes. `check_home_results_above_the_fold` closes
# that gap structurally -- the masthead is the h1 block, every explanatory
# block opens with an h2 -- which is why it cannot be defeated by a rename.

MASTHEAD = (
    '<section data-tdb-section="intro"><h1>Terminal Daily</h1>'
    "<p>tagline</p></section>"
)
BOARD = '<section data-tdb-section="leaderboard"><h2>leaderboard</h2></section>'
EXPLAINER = '<section data-tdb-section="status"><h2>status</h2><p>prose</p></section>'


def test_masthead_then_table_passes():
    assert verify_site.check_home_results_above_the_fold(MASTHEAD + BOARD) == []


def test_table_with_no_masthead_passes():
    assert verify_site.check_home_results_above_the_fold(BOARD + EXPLAINER) == []


def test_a_lone_explainer_above_the_table_fails():
    # The exact case the section-order gate cannot see: one block, index 1.
    assert verify_site.check_home_section_order(["status", "leaderboard"]) == []
    problems = verify_site.check_home_results_above_the_fold(EXPLAINER + BOARD)
    assert any("results are not first" in p and "status" in p for p in problems)


def test_the_old_home_markup_fails_above_the_fold():
    problems = verify_site.check_home_results_above_the_fold(
        MASTHEAD + EXPLAINER + BOARD
    )
    assert any("status" in p for p in problems)


def test_renaming_the_explainer_does_not_buy_a_pass_above_the_fold():
    renamed = EXPLAINER.replace("status", "highlights")
    problems = verify_site.check_home_results_above_the_fold(renamed + BOARD)
    assert any("highlights" in p for p in problems)


def test_missing_leaderboard_marker_fails_above_the_fold():
    problems = verify_site.check_home_results_above_the_fold(MASTHEAD + EXPLAINER)
    assert any("no data-tdb-section" in p for p in problems)


def test_above_the_fold_gate_is_wired(monkeypatch):
    # Same wiring proof as the three below: a pure function whose call site was
    # deleted passes every test above and guards nothing.
    monkeypatch.setattr(
        verify_site, "check_home_results_above_the_fold",
        lambda markup: ["SENTINEL above-the-fold"])
    assert any("SENTINEL above-the-fold" in p
               for p in verify_site.check_public_frontend())


# --------------------------------------------------------------------------
# the shipped pages, not just the pure functions
# --------------------------------------------------------------------------

def _home_markup() -> str:
    return verify_site.markup_only(
        (verify_site.DOCS / "index.html").read_text(encoding="utf-8"))


def test_shipped_home_leads_with_the_leaderboard():
    import re
    sections = re.findall(r'data-tdb-section="([^"]+)"', _home_markup())
    assert verify_site.check_home_section_order(sections) == []
    assert verify_site.check_home_results_above_the_fold(_home_markup()) == []


def test_shipped_home_carries_no_retired_copy():
    home = (verify_site.DOCS / "index.html").read_text(encoding="utf-8").lower()
    assert verify_site.check_retired_home_copy(home) == []


def test_the_invariant_is_stated_whole_on_a_single_page():
    # `_missing_invariant` searches the site as one haystack, so fragments
    # scattered across unrelated pages would satisfy it while leaving no page
    # that actually states the disclosure a reader is sent to.
    whole = [
        page.relative_to(verify_site.DOCS).as_posix()
        for page in sorted(verify_site.DOCS.rglob("*.html"))
        if all(f in page.read_text(encoding="utf-8", errors="replace").lower()
               for f in SCORING_INVARIANT_FRAGMENTS)
    ]
    assert whole, (
        "the invariant's fragments survive on docs/ but no single page states "
        "it; a reader following the UNOFFICIAL pill's `why` link finds half a "
        "sentence"
    )
