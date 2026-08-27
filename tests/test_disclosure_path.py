"""The `why` pill beside the leaderboard must lead to the disclosure.

WHY THIS EXISTS. The home page was rebuilt to lead with results, which is
correct -- but it means the only thing standing between a reader and an
unqualified number is the `UNOFFICIAL` badge and its one-word `why` link. That
link is the whole disclosure path.

It cannot be checked by `verify_site.check_links`. That function reads
`markup_only()`, which blanks `<script>` bodies, and the badge is built by a JS
string concatenation in docs/index.html. So the site's most load-bearing link
is invisible to the link checker by construction: it was pointed at a
non-existent anchor during the rebuild and every gate stayed green.

These tests read the JS source directly.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# Both pages that render an UNOFFICIAL badge must answer the same question.
# They pointed at different anchors for a while: home at the integrity block,
# /leaderboard/ at "What enters the matrix" -- which explains how a row is
# SCORED, not why it is unranked. A `why` that answers a different question
# than the badge asks is a disclosure only in shape.
PAGES_WITH_BADGE = ("index.html", "leaderboard/index.html")

HOME = (DOCS / "index.html").read_text(encoding="utf-8")

# The sentence that carries the invariant. It lived on the home page, was lost
# entirely for one commit when home was rebuilt, and now lives on /benchmarks/.
INVARIANT = "Protected tests decide published scores"


def _why_href(rel: str = "index.html") -> str:
    src = (DOCS / rel).read_text(encoding="utf-8")
    m = re.search(r'class="tdb-badge-why"\s+href="([^"]+)"', src)
    assert m, (
        "the UNOFFICIAL badge's `why` link is gone from docs/index.html. It is "
        "the only route from an unqualified number to the reason it is "
        "unranked; the results-first home page has no other disclosure."
    )
    return m.group(1)


def _resolve(href: str, rel: str = "index.html") -> tuple[Path, str]:
    ref, _, frag = href.partition("#")
    ref = ref.split("?", 1)[0]
    base = (DOCS / rel).parent
    target = (base / ref).resolve() if ref else (DOCS / rel)
    if target.is_dir():
        target = target / "index.html"
    return target, frag


def test_the_why_link_resolves_to_a_real_page_and_anchor():
    target, frag = _resolve(_why_href())
    assert target.exists(), f"`why` points at {target}, which does not exist"
    assert frag, "`why` points at a page with no anchor; it must land ON the disclosure"
    body = target.read_text(encoding="utf-8")
    assert f'id="{frag}"' in body, (
        f"`why` points at #{frag} in {target.relative_to(ROOT)}, which has no "
        f"such id. verify_site.check_links cannot catch this: the link is built "
        f"in a <script> and markup_only() blanks script bodies."
    )


def test_the_page_the_why_link_reaches_actually_carries_the_invariant():
    """Landing on the right anchor is not enough if the sentence moved again."""
    target, _ = _resolve(_why_href())
    body = target.read_text(encoding="utf-8")
    assert INVARIANT in body, (
        f"{target.relative_to(ROOT)} is where `why` leads, but it no longer "
        f"contains {INVARIANT!r}. The badge would promise an explanation and "
        f"deliver a page that does not give one."
    )


def test_the_invariant_exists_exactly_once_site_wide():
    """Once, not zero -- and not twice, which is how the two copies drift."""
    hits = [
        p.relative_to(ROOT)
        for p in sorted(DOCS.rglob("*.html"))
        if INVARIANT in p.read_text(encoding="utf-8", errors="replace")
    ]
    assert hits, (
        "the scoring invariant is on no page under docs/. It was deleted, not "
        "relocated, when home was rebuilt to lead with results."
    )
    assert len(hits) == 1, f"the invariant is duplicated across {hits}"


def test_home_still_marks_the_claim_even_though_it_leads_with_results():
    """Concision may remove the explanation from home. It may not remove the flag."""
    assert "data-tdb-integrity" in HOME, (
        "home carries no data-tdb-integrity marker. frontierbench.ai omits an "
        "integrity block because its results are certified; ours are not, so "
        "the marker sits beside the number it qualifies."
    )
    assert "tdb-badge-why" in HOME


def test_every_unofficial_badge_answers_the_same_question():
    """Both badges must lead to the reason for `unranked`, not somewhere near it."""
    targets = set()
    for rel in PAGES_WITH_BADGE:
        href = _why_href(rel)
        target, frag = _resolve(href, rel)
        assert target.exists(), f"{rel}: `why` -> {href} does not resolve"
        body = target.read_text(encoding="utf-8")
        assert f'id="{frag}"' in body, f"{rel}: `why` -> #{frag} has no such id"
        assert INVARIANT in body, (
            f"{rel}: `why` leads to {target.relative_to(ROOT)}, which does not "
            f"state the invariant -- the badge asks why this is UNOFFICIAL and "
            f"the answer has to be on the page it opens"
        )
        targets.add((str(target.relative_to(DOCS)).replace("\\", "/"), frag))
    assert len(targets) == 1, (
        f"the UNOFFICIAL badges point at different places: {sorted(targets)}. "
        f"One question, one answer."
    )
