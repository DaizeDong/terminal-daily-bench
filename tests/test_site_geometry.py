"""The square-geometry gate must actually fail when the geometry is reversed.

`verify_site.check_square_geometry` replaced a gate that asserted the exact
opposite (a non-zero `--radius`, and at least eight `border-radius`
declarations). A flipped decision is the moment a check is most likely to be
quietly turned into a no-op -- deleted, or rewritten into something every
stylesheet satisfies. These tests pin the failure cases, so the gate cannot go
vacuous without a red test.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import verify_site  # noqa: E402

# A minimal stylesheet that satisfies every clause: --radius pinned to zero,
# the vendored .rounded-full utility squared (tw.css hardcodes it, so the
# token does not reach it), and the two drawn circles still round.
SQUARE = """
:root { --radius: 0; }
.tdb-card { border-radius: 0; }
.tdb-plain-table { border-radius: var(--radius); }
.rounded-full { border-radius: 0 !important; }
.tdb-brand-mark::before { border-radius: 999px; }
.tdb-brand-mark::after { border-radius: 999px; }
.tdb-ci-dot { border-radius: 999px; }
"""


def _check(body: str) -> list[str]:
    return verify_site.check_square_geometry(body)


def test_square_stylesheet_passes():
    assert _check(SQUARE) == []


def test_shipped_site_css_is_square():
    text = (verify_site.DOCS / "assets" / "site.css").read_text(encoding="utf-8")
    body = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    assert _check(body) == []


def test_non_zero_radius_token_fails():
    problems = _check(SQUARE.replace("--radius: 0;", "--radius: 0.9rem;"))
    assert any("--radius: 0.9rem" in p for p in problems)


def test_deleting_the_radius_token_fails():
    # Not the same as zeroing it: tw.css declares its own --radius, so an
    # absent declaration hands every .rounded-* utility back to the vendor.
    problems = _check(SQUARE.replace("--radius: 0;", ""))
    assert any("does not declare --radius" in p for p in problems)


def test_a_rounded_corner_anywhere_fails():
    problems = _check(SQUARE + ".tdb-panel { border-radius: 0.5rem; }\n")
    assert any(".tdb-panel" in p for p in problems)


def test_a_partially_rounded_corner_fails():
    # `border-radius: 0 0 6px 6px` contains the substring "border-radius: 0"
    # and is not square. A substring test would pass it.
    problems = _check(SQUARE + ".tdb-panel { border-radius: 0 0 6px 6px; }\n")
    assert any(".tdb-panel" in p for p in problems)


def test_a_stray_pill_outside_the_exceptions_fails():
    problems = _check(SQUARE + ".tdb-tag { border-radius: 999px; }\n")
    assert any(".tdb-tag" in p for p in problems)


def test_squaring_the_ci_point_estimate_fails():
    # The CI dot and the brand mark's discs are drawn geometry, not chrome.
    problems = _check(SQUARE.replace(
        ".tdb-ci-dot { border-radius: 999px; }",
        ".tdb-ci-dot { border-radius: 0; }"))
    assert any(".tdb-ci-dot" in p for p in problems)


def test_deleting_a_brand_mark_disc_fails():
    problems = _check(SQUARE.replace(
        ".tdb-brand-mark::after { border-radius: 999px; }", ""))
    assert any(".tdb-brand-mark::after" in p for p in problems)


def test_unsquared_rounded_full_utility_fails():
    # tw.css hardcodes .rounded-full to 3.40282e38px rather than deriving it
    # from --radius, and site.js still ships the class on the theme switch.
    problems = _check(SQUARE.replace(
        ".rounded-full { border-radius: 0 !important; }", ""))
    assert any("rounded-full" in p for p in problems)
