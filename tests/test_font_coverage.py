"""Every glyph the site renders is drawn by the family that is SUPPOSED to
draw it, or is a short, named, deliberate exception.

WHY THIS EXISTS. A `font-family` check cannot see this failure. When a face
lacks a glyph the browser does not fall back to another WEIGHT of the same
family -- it falls back to a different FAMILY, for that one character, and the
computed `fontFamily` still reports the site's own stack. So a page can pass
every "one font" assertion and still render two typefaces side by side.

Auditing character-by-character against the fonts' cmap found 125 uncovered
characters, and the worst was `→` in 73 files: every "full leaderboard ->"
arrow was being drawn by whatever font the OS happened to choose. Vendoring the
math/symbols subsets closed that.

WHY IT HAD TO BE REWRITTEN. The site now ships TWO families under one rule --
Geist for prose, headings and UI labels; Google Sans Code for code, numeric
cells and identifiers -- and `--td-font-sans` names `"Google Sans Code"` as its
IMMEDIATE fallback, so a glyph Geist lacks is drawn by the other vendored face
rather than by an OS pick. That is the right engineering call and it re-creates
the original trap by construction: "covered by SOME vendored face" and "covered
by the face that is supposed to render it" are now different questions, and
only the first is easy to ask. A version of this test that unions the two cmaps
would go green while `→` renders in mono inside a sans paragraph -- which is
the exact green-while-broken state the audit found the first time.

So every character is resolved to the family its element DECLARES first, and
the two outcomes are reported separately: covered by that family, versus
reaching the page only through the named fallback. That fallback list is seven
characters long, every one of them enumerated below, and adding to it is a
decision rather than a formality.
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
SITE_CSS = DOCS / "assets" / "site.css"

# The two vendored families, keyed by the filename prefix their subsets share.
# Not a hardcoded file list: a new subset of either face is picked up, and a
# face vendored under some third prefix fails test_exactly_two_vendored_families
# rather than being silently ignored here.
SANS_PREFIX = "geist-"
MONO_PREFIX = "google-sans-code-"

_SCRIPT = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S | re.I)
_STYLE = re.compile(r"<style\b[^>]*>.*?</style>", re.S | re.I)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_DQ = re.compile(r'"((?:[^"\\]|\\.)*)"')
_SQ = re.compile(r"'((?:[^'\\]|\\.)*)'")

# One open tag, one close tag, or a run of text. Deliberately not a real HTML
# parser: it only has to know which element a character sits inside, and the
# generated markup is well-formed because a generator emits it.
_TOKEN = re.compile(r"<(/?)([a-zA-Z][-\w]*)([^>]*)>|([^<]+)")
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
         "meta", "param", "source", "track", "wbr"}

# Glyphs Google Sans Code does not contain AT ALL -- checked against the full
# 674-glyph font, not a subset, so no amount of extra subsetting fixes them.
# They fall back to the named tail of --td-font-mono in site.css, by design.
#
#   math notation, /guide/quality-methods/ formula blocks
# CJK is handled by _cjk() rather than listed here -- see its docstring.
#
# Adding to this set is a DECISION, not a formality: it means accepting a
# second typeface for that character on every page that renders it.
KNOWN_FALLBACK = set("Σρσ₀↵√∞≈")

# Characters that render in SANS CONTEXT but are not in Geist, so they are
# drawn by "Google Sans Code" -- the second name in --td-font-sans, and the
# reason that name is there rather than a system face. Seven characters, each
# one argued:
#
#   U+2192 →  the "full leaderboard ->" arrow, 73 files. Rewriting it across
#             every page to suit a font choice is the tail wagging the dog.
#   U+2264 ≤  the two relations in the quality-report and quality-methods
#   U+2265 ≥  prose. Prose, so sans context, so listed here.
#   U+2596 ▖  the day-window block in the masthead, 76 files.
#   U+25B2 ▲  the leaderboard sort indicators, emitted from tdb-data.js.
#   U+25BC ▼
#   U+2318 ⌘  the search modal's shortcut hint, emitted from site.js.
#
# This list is a NAMED, CLOSED set, not a drain. Its whole purpose is that
# anything Geist happens to lack must be argued for one character at a time
# instead of being absorbed silently -- which is how 125 uncovered characters
# accumulated the first time. Every entry must also be covered by the mono, or
# it is an OS pick wearing a fallback's clothes; test_sans_fallback_is_a_closed
# _deliberate_list checks exactly that.
SANS_FALLBACK = set("→≤≥▖▲▼⌘")


def _cjk(ch: str) -> bool:
    """CJK ideographs AND the punctuation that travels with them.

    A first pass listed the ideographs only, and the test immediately caught
    U+FF0C and U+FF1B -- the fullwidth comma and semicolon in the same title.
    Enumerating CJK punctuation one mark at a time is how the next one gets
    missed, so the ranges are declared instead. Neither vendored face carries
    CJK; both stacks name the same CJK fallback chain, so the family a CJK
    character lands in does not depend on which context it is in.
    """
    cp = ord(ch)
    return (0x3000 <= cp <= 0x303F      # CJK symbols and punctuation
            or 0x3400 <= cp <= 0x9FFF   # ideographs (ext-A + unified)
            or 0xF900 <= cp <= 0xFAFF   # compatibility ideographs
            or 0xFF00 <= cp <= 0xFFEF)  # halfwidth and fullwidth forms


def _cmap(prefix: str) -> set[int]:
    files = sorted(FONTS.glob(f"{prefix}*.woff2"))
    assert files, f"no vendored woff2 named {prefix}*.woff2 under {FONTS}"
    cov: set[int] = set()
    for path in files:
        cov |= set(TTFont(path).getBestCmap().keys())
    return cov


def _sans() -> set[int]:
    return _cmap(SANS_PREFIX)


def _mono() -> set[int]:
    return _cmap(MONO_PREFIX)


def _mono_opt_in() -> tuple[set[str], set[str], set[str]]:
    """The mono opt-in list, read OUT OF site.css rather than restated here.

    If this test kept its own copy of the selector list, the stylesheet could
    add `.tdb-whatever` to the mono and the audit would go on classifying its
    contents as sans -- passing while checking the wrong family. So the list
    has exactly one home, and the test reads it.

    Returns (tags, classes, attributes).
    """
    css = SITE_CSS.read_text(encoding="utf-8")
    css = _CSS_COMMENT.sub(" ", css)
    rules = [m for m in _CSS_RULE.finditer(css)
             if "var(--td-font-mono)" in m.group(2)
             and "font-family" in m.group(2)]
    assert rules, (
        "site.css declares no rule applying var(--td-font-mono); either the "
        "mono opt-in is gone or it was renamed, and this audit would then be "
        "checking every character against the sans alone"
    )
    tags: set[str] = set()
    classes: set[str] = set()
    attrs: set[str] = set()
    for m in rules:
        for sel in m.group(1).split(","):
            sel = sel.strip()
            if not sel or " " in sel or sel.startswith(("#", ":", "@")):
                continue  # descendant/id/pseudo selectors: not a bare hook
            if sel.startswith("["):
                attrs.add(sel[1:-1].split("=")[0].strip())
            elif sel.startswith("."):
                classes.add(sel[1:])
            elif re.fullmatch(r"[a-zA-Z][-\w]*", sel):
                tags.add(sel)
    return tags, classes, attrs


_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")


def _rendered_chars() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Every character that can reach the page, split by the family that draws it.

    Static markup AND JavaScript string literals: half this site's text is
    built by `innerHTML` in an inline script, so scanning markup alone misses
    it -- the search modal's key hints and the header live only in site.js.

    JS literals are counted as SANS. That is the conservative side of the
    guess: the strings that JS injects are headings, labels and nav copy, and
    treating a genuinely-mono one as sans can only make this test stricter
    than reality, never laxer.
    """
    tags, classes, attrs = _mono_opt_in()
    class_re = re.compile(
        r'class\s*=\s*"[^"]*\b(?:%s)\b' % "|".join(re.escape(c) for c in sorted(classes))
    ) if classes else None
    attr_re = re.compile(
        r"\b(?:%s)\b" % "|".join(re.escape(a) for a in sorted(attrs))
    ) if attrs else None

    sans: dict[str, set[str]] = {}
    mono: dict[str, set[str]] = {}

    def note(bucket: dict[str, set[str]], text: str, where: str) -> None:
        for ch in text:
            if ord(ch) > 31:
                bucket.setdefault(ch, set()).add(where)

    for path in sorted(DOCS.rglob("*.html")):
        rel = str(path.relative_to(ROOT))
        raw = path.read_text(encoding="utf-8", errors="replace")
        for script in _SCRIPT.findall(raw):
            for pat in (_DQ, _SQ):
                for m in pat.finditer(script):
                    note(sans, html.unescape(m.group(1)), rel)

        body = _COMMENT.sub(" ", _STYLE.sub(" ", _SCRIPT.sub(" ", raw)))
        stack: list[tuple[str, bool]] = []
        depth = 0
        for m in _TOKEN.finditer(body):
            close, tag, attr_text, text = m.groups()
            if text is not None:
                note(mono if depth else sans, html.unescape(text), rel)
                continue
            tag = tag.lower()
            if close:
                while stack:
                    open_tag, was_mono = stack.pop()
                    if was_mono:
                        depth -= 1
                    if open_tag == tag:
                        break
                continue
            if tag in _VOID or attr_text.rstrip().endswith("/"):
                continue
            is_mono = (
                tag in tags
                or (class_re is not None and bool(class_re.search(attr_text)))
                or (attr_re is not None and bool(attr_re.search(attr_text)))
            )
            stack.append((tag, is_mono))
            if is_mono:
                depth += 1

    for name in ("site.js", "tdb-data.js"):
        path = DOCS / "assets" / name
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        for pat in (_DQ, _SQ):
            for m in pat.finditer(raw):
                note(sans, html.unescape(m.group(1)), f"docs/assets/{name}")
    return sans, mono


def _report(uncovered: dict[str, set[str]]) -> str:
    return "\n".join(
        f"  U+{ord(ch):04X} {ch!r} in {len(files)} file(s), e.g. {sorted(files)[0]}"
        for ch, files in sorted(uncovered.items(), key=lambda kv: ord(kv[0]))
    )


def test_the_mono_opt_in_list_is_real_and_readable():
    """The audit is only family-aware if it can find the opt-in list.

    An empty list would silently reclassify every character on the site as
    sans, and the test would still print green -- a checker fed nothing prints
    the same colour as a checker that found nothing wrong.
    """
    tags, classes, attrs = _mono_opt_in()
    assert {"code", "pre", "kbd", "samp"} <= tags, tags
    assert classes, "the mono opt-in names no class hook"
    assert attrs, "the mono opt-in names no attribute hook"


def test_sans_context_glyphs_are_drawn_by_the_sans():
    """Prose, headings and UI labels must be drawn by Geist, or by a listed few.

    This is the assertion the union-of-cmaps version could not make.
    """
    sans_chars, _ = _rendered_chars()
    cov = _sans()
    escaped = {
        ch: files for ch, files in sans_chars.items()
        if ord(ch) not in cov
        and ch not in SANS_FALLBACK
        # KNOWN_FALLBACK is exempt in BOTH contexts, not just mono: those are
        # the characters NEITHER vendored face carries, so which context they
        # sit in cannot change what draws them. `↵` in the search modal is the
        # live example -- listing it under SANS_FALLBACK would claim the mono
        # draws it, and the mono does not.
        and ch not in KNOWN_FALLBACK
        and not _cjk(ch)
    }
    if escaped:
        raise AssertionError(
            "these characters sit in SANS context but the vendored sans has "
            "no glyph for them, so they render in a different family:\n"
            + _report(escaped) +
            "\n\nEither vendor a Geist subset that carries them, replace them "
            "with covered characters, or add them to SANS_FALLBACK -- which "
            "means accepting that they are drawn by the mono, beside sans text."
        )


def test_mono_context_glyphs_are_drawn_by_the_mono():
    """Code, numeric cells and identifiers must be drawn by Google Sans Code."""
    _, mono_chars = _rendered_chars()
    cov = _mono()
    escaped = {
        ch: files for ch, files in mono_chars.items()
        if ord(ch) not in cov and ch not in KNOWN_FALLBACK and not _cjk(ch)
    }
    if escaped:
        raise AssertionError(
            "these characters sit in MONO context but the vendored mono has "
            "no glyph for them:\n" + _report(escaped) +
            "\n\nVendor a subset that carries them (see the @font-face blocks "
            "in site.css), replace them, or add them to KNOWN_FALLBACK."
        )


def test_the_arrow_that_started_this_is_covered():
    """U+2192 was uncovered in 73 files -- one regression away from returning.

    It is now a SANS_FALLBACK entry rather than a plain pass: Geist has no
    arrow, so the check is that the mono still does and that the fallback is
    the one that names it.
    """
    assert ord("→") in _mono()
    assert "→" in SANS_FALLBACK


def test_sans_fallback_is_a_closed_deliberate_list():
    """Every SANS_FALLBACK entry must be genuinely absent from the sans and
    genuinely present in the mono.

    Both halves matter. An entry the sans DOES carry is stale -- it grants a
    second typeface that never happens, and it hides a real regression behind
    a stale exception. An entry the MONO does not carry is worse: it reads as
    a decision to use the other vendored face, while the character actually
    falls through to whatever the OS supplies.
    """
    sans, mono = _sans(), _mono()
    stale = sorted(ch for ch in SANS_FALLBACK if ord(ch) in sans)
    assert not stale, (
        f"SANS_FALLBACK lists {stale!r}, but Geist covers them; drop the entry "
        "rather than documenting a fallback that never happens"
    )
    unvendored = sorted(ch for ch in SANS_FALLBACK if ord(ch) not in mono)
    assert not unvendored, (
        f"SANS_FALLBACK lists {unvendored!r} as drawn by the mono, but the "
        "vendored mono has no glyph for them either -- these are OS picks"
    )
    assert len(SANS_FALLBACK) <= 8, (
        f"SANS_FALLBACK has grown to {len(SANS_FALLBACK)} characters. It is "
        "meant to be a short argued list, not a drain for whatever Geist "
        "lacks; past about eight, subset the sans instead"
    )


def test_known_fallback_is_really_unfixable():
    """Nothing in KNOWN_FALLBACK may be sitting in a subset we already ship."""
    cov = _mono()
    stale = sorted(ch for ch in KNOWN_FALLBACK if ord(ch) in cov)
    assert not stale, (
        f"KNOWN_FALLBACK lists {stale!r}, but the vendored face covers them; "
        "drop the entry rather than documenting a fallback that never happens"
    )


def test_exactly_two_vendored_families():
    """A third face under a third filename prefix would be invisible to the
    audit above -- its glyphs would be checked against a family that is not
    drawing them."""
    prefixes = {p.name.rsplit("-", 1)[0] for p in FONTS.glob("*.woff2")}
    families = {SANS_PREFIX.rstrip("-"), MONO_PREFIX.rstrip("-")}
    stray = {p for p in prefixes if not any(p.startswith(f) for f in families)}
    assert not stray, f"unaudited vendored faces: {sorted(stray)}"


def test_both_fallback_tails_are_named_not_left_to_the_os():
    """Each token must name what draws the glyphs its lead face lacks.

    Without this the fallback is whatever the OS picks, which differs per
    machine -- so the site's second typeface would be unspecified rather than
    chosen, and unreviewable.
    """
    css = SITE_CSS.read_text(encoding="utf-8")

    def stack(token: str) -> str:
        m = re.search(rf"{token}:\s*([^;]+);", css)
        assert m, f"site.css no longer declares {token}"
        return " ".join(m.group(1).split())

    mono = stack("--td-font-mono")
    assert mono.startswith('"Google Sans Code"'), mono
    assert "monospace" in mono, "the mono stack must end in a generic family"

    sans = stack("--td-font-sans")
    assert sans.startswith('"Geist"'), sans
    assert sans.split(",")[1].strip() == '"Google Sans Code"', (
        "--td-font-sans must name the OTHER VENDORED FACE second: Geist has no "
        f"{sorted(SANS_FALLBACK)}, and anything else there is an OS pick. Got: {sans}"
    )
    assert "sans-serif" in sans, "the sans stack must end in a generic family"

    # --td-font is the mono token's old name. verify_site.py and
    # test_leaderboard_frontend.py both spell it, so it stays a live alias.
    assert stack("--td-font") == "var(--td-font-mono)", stack("--td-font")

    for cjk_face in ("Sarasa Mono SC", "Noto Sans Mono CJK SC", "PingFang SC"):
        if cjk_face in mono:
            break
    else:
        raise AssertionError(
            "no CJK face is named in --td-font-mono, but the catalogue renders "
            "CJK from mined upstream PR titles; name it or the OS picks it"
        )
    for cjk_face in ("Source Han Sans SC", "Noto Sans CJK SC", "PingFang SC"):
        if cjk_face in sans:
            break
    else:
        raise AssertionError(
            "no CJK face is named in --td-font-sans; the same mined titles "
            "render in prose context, where the sans is what draws them"
        )
