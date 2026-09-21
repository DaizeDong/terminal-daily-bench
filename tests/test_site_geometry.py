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

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import verify_site  # noqa: E402

# A minimal stylesheet that satisfies every clause: --radius pinned to zero,
# the vendored .rounded-full utility squared (tw.css hardcodes it, so the
# token does not reach it), and the plotted point estimate still round.
SQUARE = """
:root { --radius: 0; }
.tdb-card { border-radius: 0; }
.tdb-plain-table { border-radius: var(--radius); }
.rounded-full { border-radius: 0 !important; }
.tdb-ci-dot { border-radius: 999px; }
"""

SQUARE_BRAND = """
<a class="tdb-brand" href="/" aria-label="Sample site home">
  <svg class="tdb-brand-mark" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
    <rect x="1" y="2" width="30" height="28"/>
    <path d="M5 7 L12 16 L5 25 M17 25 H26"/>
  </svg>
</a>
"""
SHIPPED_SCRIPT = (ROOT / "docs" / "assets" / "site.js").read_text(encoding="utf-8")
BRAND = re.search(r'<a class="tdb-brand\b.*?</a>', SHIPPED_SCRIPT, re.S).group(0)


@pytest.fixture
def check_brand(tmp_path, monkeypatch):
    """Exercise the publish gate with mutations of the shipped brand emitter."""
    assets = tmp_path / "assets"
    assets.mkdir()
    monkeypatch.setattr(verify_site, "DOCS", tmp_path)

    def check(source=BRAND, css=SQUARE):
        (assets / "site.js").write_text(
            "function headerHTML() { return '" + source + "'; }",
            encoding="utf-8")
        return _check(css)

    return check


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
    # The CI dot is drawn geometry, not chrome.
    problems = _check(SQUARE.replace(
        ".tdb-ci-dot { border-radius: 999px; }",
        ".tdb-ci-dot { border-radius: 0; }"))
    assert any(".tdb-ci-dot" in p for p in problems)


def test_deleting_the_ci_point_estimate_radius_fails():
    problems = _check(SQUARE.replace(
        ".tdb-ci-dot { border-radius: 999px; }", ""))
    assert any(".tdb-ci-dot" in p for p in problems)


def test_legacy_brand_discs_are_no_longer_circle_exceptions():
    problems = _check(SQUARE + ".tdb-brand-mark::after { border-radius: 999px; }")
    assert any(".tdb-brand-mark::after" in p for p in problems)


def test_square_svg_brand_passes_without_pinning_path_coordinates(check_brand):
    assert check_brand(SQUARE_BRAND) == []


def test_shipped_svg_brand_passes(check_brand):
    assert check_brand() == []


def test_deleting_the_svg_brand_fails(check_brand):
    problems = check_brand(BRAND.replace('class="tdb-brand-mark"', 'class="other"'))
    assert any("svg.tdb-brand-mark" in p for p in problems)


@pytest.mark.parametrize("attribute", ['rx="3"', 'ry="10%"', 'style="rx: 2px"'])
def test_rounding_the_svg_terminal_frame_fails(check_brand, attribute):
    problems = check_brand(BRAND.replace("<rect ", f"<rect {attribute} "))
    assert any("svg.tdb-brand-mark" in p and "rect" in p for p in problems)


@pytest.mark.parametrize("shape", [
    '<circle cx="16" cy="16" r="4"/>',
    '<ellipse cx="16" cy="16" rx="4" ry="2"/>',
    '<path d="M1 1 Q5 8 10 10"/>',
    '<path d="M1 1 A4 4 0 0 1 8 8"/>',
])
def test_adding_curved_svg_geometry_fails(check_brand, shape):
    problems = check_brand(BRAND.replace("</svg>", shape + "</svg>"))
    assert any("svg.tdb-brand-mark" in p and "round" in p for p in problems)


@pytest.mark.parametrize("attribute", [
    'stroke-linecap="round"', 'stroke-linejoin="round"',
    'style="stroke-linejoin: round"',
])
def test_rounding_svg_strokes_fails(check_brand, attribute):
    problems = check_brand(BRAND.replace("<svg ", f"<svg {attribute} "))
    assert any("svg.tdb-brand-mark" in p and "round" in p for p in problems)


@pytest.mark.parametrize("declaration", ["rx: 3px", "ry: 10%", "stroke-linejoin: round"])
def test_rounding_svg_from_stylesheet_fails(check_brand, declaration):
    problems = check_brand(css=SQUARE + f".tdb-brand-mark rect {{ {declaration}; }}")
    assert any("svg.tdb-brand-mark" in p and "round" in p for p in problems)


@pytest.mark.parametrize("attribute, replacement", [
    ('aria-hidden="true"', ''),
    ('aria-hidden="true"', 'aria-hidden="false"'),
    ('focusable="false"', ''),
    ('focusable="false"', 'focusable="true"'),
])
def test_svg_must_remain_decorative(check_brand, attribute, replacement):
    problems = check_brand(BRAND.replace(attribute, replacement))
    assert any("tdb-brand-mark" in p and attribute.split("=")[0] in p for p in problems)


def test_hidden_svg_cannot_join_keyboard_tab_order(check_brand):
    problems = check_brand(BRAND.replace("<svg ", '<svg tabindex="0" '))
    assert any("tdb-brand-mark" in p and "focus" in p for p in problems)


def test_decorative_svg_requires_a_labelled_brand_link(check_brand):
    problems = check_brand(re.sub(r'aria-label="[^"]*"', 'aria-label=""', BRAND))
    assert any("brand link" in p and "label" in p for p in problems)


def test_decorative_svg_requires_an_enclosing_brand_link(check_brand):
    problems = check_brand(BRAND.replace('<a ', '<span ').replace('</a>', '</span>'))
    assert any("brand link" in p for p in problems)


@pytest.mark.parametrize("viewbox", ["0 0 0 24", "0 0 24 NaN", "0 0 inf 24", "0 0 24"])
def test_svg_viewbox_requires_finite_positive_dimensions(check_brand, viewbox):
    problems = check_brand(re.sub(r'viewBox="[^"]*"', f'viewBox="{viewbox}"', BRAND))
    assert any("svg.tdb-brand-mark" in p and "viewBox" in p for p in problems)


@pytest.mark.parametrize("attribute", ['width="0"', 'height="NaN"', 'x="Infinity"'])
def test_svg_frame_requires_visible_finite_geometry(check_brand, attribute):
    name = attribute.split("=")[0]
    source = re.sub(r'<rect\b[^>]*',
                    lambda m: re.sub(name + r'="[^"]*"', attribute, m.group(0)), BRAND)
    assert source != BRAND
    problems = check_brand(source)
    assert any("svg.tdb-brand-mark" in p and "rect" in p for p in problems)


def test_unsquared_rounded_full_utility_fails():
    # tw.css hardcodes .rounded-full to 3.40282e38px rather than deriving it
    # from --radius, and site.js still ships the class on the theme switch.
    problems = _check(SQUARE.replace(
        ".rounded-full { border-radius: 0 !important; }", ""))
    assert any("rounded-full" in p for p in problems)
