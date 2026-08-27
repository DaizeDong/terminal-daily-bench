"""Every glyph the site renders is drawn by the vendored face, or is a known
exception.

WHY THIS EXISTS. A `font-family` check cannot see this failure. When the face
lacks a glyph the browser does not fall back to another WEIGHT of the same
family -- it falls back to a different FAMILY, for that one character, and the
computed `fontFamily` still reports the site's own stack. So a page can pass
every "one font" assertion and still render two typefaces side by side.

Auditing character-by-character against the fonts' cmap found 125 uncovered
characters, and the worst was `→` in 73 files: every "full leaderboard ->"
arrow was being drawn by whatever font the OS happened to choose. Vendoring the
math/symbols subsets closed that; this test stops it reopening.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import pytest

fontTools = pytest.importorskip(
    "fontTools", reason="fonttools is needed to read the vendored woff2 cmaps")
from fontTools.ttLib import TTFont  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
FONTS = DOCS / "assets" / "fonts"

_SCRIPT = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S | re.I)
_STYLE = re.compile(r"<style\b[^>]*>.*?</style>", re.S | re.I)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_TAG = re.compile(r"<[^>]+>")
_DQ = re.compile(r'"((?:[^"\\]|\\.)*)"')
_SQ = re.compile(r"'((?:[^'\\]|\\.)*)'")

# Glyphs Google Sans Code does not contain AT ALL -- checked against the full
# 674-glyph font, not a subset, so no amount of extra subsetting fixes them.
# They fall back to the named tail of --td-font in site.css, by design.
#
#   math notation, /guide/quality-methods/ formula blocks
# CJK is handled by _cjk() rather than listed here -- see its docstring.
#
# Adding to this set is a DECISION, not a formality: it means accepting a
# second typeface for that character on every page that renders it.
KNOWN_FALLBACK = set("Σρσ₀↵√∞≈")


def _cjk(ch: str) -> bool:
    """CJK ideographs AND the punctuation that travels with them.

    A first pass listed the ideographs only, and the test immediately caught
    U+FF0C and U+FF1B -- the fullwidth comma and semicolon in the same title.
    Enumerating CJK punctuation one mark at a time is how the next one gets
    missed, so the ranges are declared instead.
    """
    cp = ord(ch)
    return (0x3000 <= cp <= 0x303F      # CJK symbols and punctuation
            or 0x3400 <= cp <= 0x9FFF   # ideographs (ext-A + unified)
            or 0xF900 <= cp <= 0xFAFF   # compatibility ideographs
            or 0xFF00 <= cp <= 0xFFEF)  # halfwidth and fullwidth forms


def _covered() -> set[int]:
    files = sorted(FONTS.glob("*.woff2"))
    assert files, f"no vendored woff2 under {FONTS}"
    cov: set[int] = set()
    for path in files:
        cov |= set(TTFont(path).getBestCmap().keys())
    return cov


def _rendered_chars() -> dict[str, set[str]]:
    """Every character that can reach the page, mapped to the files it is in.

    Static markup AND JavaScript string literals: half this site's text is
    built by `innerHTML` in an inline script, so scanning markup alone misses
    it -- the search modal's key hints live only in site.js.
    """
    seen: dict[str, set[str]] = {}

    def note(text: str, where: str) -> None:
        for ch in text:
            if ord(ch) > 31:
                seen.setdefault(ch, set()).add(where)

    for path in sorted(DOCS.rglob("*.html")):
        rel = str(path.relative_to(ROOT))
        raw = path.read_text(encoding="utf-8", errors="replace")
        for script in _SCRIPT.findall(raw):
            for pat in (_DQ, _SQ):
                for m in pat.finditer(script):
                    note(html.unescape(m.group(1)), rel)
        body = _COMMENT.sub(" ", _STYLE.sub(" ", _SCRIPT.sub(" ", raw)))
        note(html.unescape(_TAG.sub(" ", body)), rel)

    for name in ("site.js", "tdb-data.js"):
        path = DOCS / "assets" / name
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        for pat in (_DQ, _SQ):
            for m in pat.finditer(raw):
                note(html.unescape(m.group(1)), f"docs/assets/{name}")
    return seen


def test_every_rendered_glyph_is_in_the_vendored_face():
    cov = _covered()
    uncovered = {
        ch: files for ch, files in _rendered_chars().items()
        if ord(ch) not in cov and ch not in KNOWN_FALLBACK and not _cjk(ch)
    }
    if uncovered:
        lines = [
            f"  U+{ord(ch):04X} {ch!r} in {len(files)} file(s), e.g. {sorted(files)[0]}"
            for ch, files in sorted(uncovered.items(), key=lambda kv: ord(kv[0]))
        ]
        raise AssertionError(
            "these characters render in a DIFFERENT FAMILY, because the "
            "vendored face has no glyph for them:\n" + "\n".join(lines) +
            "\n\nEither vendor a subset that carries them (see the @font-face "
            "blocks in site.css), replace them with covered characters, or add "
            "them to KNOWN_FALLBACK and accept a second typeface there."
        )


def test_the_arrow_that_started_this_is_covered():
    """U+2192 was uncovered in 73 files -- one regression away from returning."""
    assert ord("→") in _covered()


def test_known_fallback_is_really_unfixable():
    """Nothing in KNOWN_FALLBACK may be sitting in a subset we already ship.

    If it is, the entry is stale: the glyph would render correctly and the
    exception is granting a second typeface that is not actually needed.
    """
    cov = _covered()
    stale = sorted(ch for ch in KNOWN_FALLBACK if ord(ch) in cov)
    assert not stale, (
        f"KNOWN_FALLBACK lists {stale!r}, but the vendored face covers them; "
        "drop the entry rather than documenting a fallback that never happens"
    )


def test_the_fallback_tail_is_named_not_left_to_the_os():
    """--td-font must name what draws the uncovered glyphs.

    Without this the fallback is whatever the OS picks, which differs per
    machine -- so the site's second typeface would be unspecified rather than
    chosen, and unreviewable.
    """
    css = (DOCS / "assets" / "site.css").read_text(encoding="utf-8")
    stack = re.search(r"--td-font:\s*([^;]+);", css)
    assert stack, "site.css no longer declares --td-font"
    value = " ".join(stack.group(1).split())
    assert value.startswith('"Google Sans Code"'), value
    assert "monospace" in value, "the stack must end in a generic family"
    for cjk_face in ("Sarasa Mono SC", "Noto Sans Mono CJK SC", "PingFang SC"):
        if cjk_face in value:
            break
    else:
        raise AssertionError(
            "no CJK face is named in --td-font, but the catalogue renders CJK "
            "from mined upstream PR titles; name the fallback or the OS picks it"
        )
