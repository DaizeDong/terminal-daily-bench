#!/usr/bin/env python3
"""verify_site.py -- static invariants for the terminal-daily-bench site.

Run it after any edit under release/docs (and after web/gen_pages.py):

    python3 web/verify_site.py            # -> exit 0 when everything holds

It is deliberately dependency-free and fast, so it can sit in front of a
publish. It checks, for every docs/**/*.html:

  1. STYLESHEET CONTRACT  every page links exactly
         <depth>/assets/tw.css, <depth>/assets/tw-extra.css, <depth>/assets/site.css
     in that order, with <depth> derived from where the file sits. This is the
     invariant that three generated pages silently broke: they linked site.css
     alone and rendered as unstyled HTML.

  2. TAG BALANCE          no unclosed / stray end tags, doctype first, </html> last.

  3. SHELL                <main> carries id="nd-home-layout" and the pt-14 frame;
     the trailing <script src=".../site.js"> has a data-root matching the depth
     and a non-empty data-page.

  4. CLASS COVERAGE       every class token in a static class="..." attribute has
     a matching selector somewhere in the concatenated CSS. Tokens produced by
     JS string concatenation are skipped (they are checked by rendering), as are
     the framework marker classes that carry no CSS in the reference either.

  5. INTERNAL LINKS       every relative href/src resolves to a real file, or to a
     directory holding an index.html; every #fragment resolves to a real id.

  6. NO EXTERNAL REQUESTS no stylesheet, script, image or CSS url() may point at
     another host. Cross-origin <a href> links are allowed (and expected).

  7. UNIQUE IDS           no id appears twice in one document.

  8. site.css STAYS THIN  it may not define border-radius, and may not redefine a
     design token that the vendored build already owns.
"""

from __future__ import annotations

import html.parser
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent / "docs"

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}

# marker classes the framework emits with no CSS behind them; the reference does
# the same, so their absence from the stylesheet is faithful, not a bug
NO_CSS_MARKERS = re.compile(
    r"^(lucide(-[a-z0-9-]+)?|shiki|shiki-themes|github-light|github-dark|not-prose)$")


class Balance(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append((tag, self.getpos()))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for t, pos in self.stack[i + 1:]:
                    self.errors.append(f"unclosed <{t}> at line {pos[0]}")
                del self.stack[i:]
                return
        self.errors.append(f"stray </{tag}> at line {self.getpos()[0]}")


def css_selectors() -> set[str]:
    text = ""
    for name in ("tw.css", "tw-extra.css", "site.css"):
        text += (DOCS / "assets" / name).read_text(encoding="utf-8", errors="replace")
    out = set()
    for m in re.finditer(r"\.((?:\\.|[^\s,{>+~)\[\]:.'\"])+)", text):
        out.add(re.sub(r"\\(.)", r"\1", m.group(1)))
    return out


_SCRIPT_BODY = re.compile(r"(<script\b[^>]*>)(.*?)(</script>)", re.S | re.I)
_STYLE_BODY = re.compile(r"(<style\b[^>]*>)(.*?)(</style>)", re.S | re.I)


def markup_only(raw: str) -> str:
    """The document with <script>/<style> BODIES blanked (their opening tags kept).

    Everything inside a script is JavaScript, not markup: a `class="' + CARD + '"`
    or an `href="' + url + '"` in there is a string being built at runtime, and
    scanning it as if it were an attribute produces nothing but false positives.
    Line count is preserved so reported line numbers stay meaningful.
    """
    def blank(m):
        return m.group(1) + re.sub(r"[^\n]", " ", m.group(2)) + m.group(3)
    return _STYLE_BODY.sub(blank, _SCRIPT_BODY.sub(blank, raw))


def depth_of(page: Path) -> int:
    return len(page.relative_to(DOCS).parts) - 1


def root_for(depth: int) -> str:
    return "/".join([".."] * depth) if depth else "."


def check(page: Path, sel: set[str], all_ids: dict) -> list[str]:
    source = page.read_text(encoding="utf-8", errors="replace")
    raw = markup_only(source)
    rel = page.relative_to(DOCS)
    bad: list[str] = []
    depth = depth_of(page)
    root = root_for(depth)

    # --- 2. structure ------------------------------------------------------
    if not raw.lstrip().lower().startswith("<!doctype html>"):
        bad.append("missing <!doctype html> on the first line")
    if not raw.rstrip().endswith("</html>"):
        bad.append("does not end with </html>")
    b = Balance()
    b.feed(source)
    b.close()
    for t, pos in b.stack:
        b.errors.append(f"unclosed <{t}> at line {pos[0]}")
    bad += b.errors

    # --- 1. stylesheet contract -------------------------------------------
    sheets = re.findall(r'<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"', raw)
    want = [f"{root}/assets/{n}" for n in ("tw.css", "tw-extra.css", "site.css")]
    if sheets != want:
        bad.append(f"stylesheets {sheets} != {want}")

    # --- 3. shell ----------------------------------------------------------
    if not re.search(r'<main id="nd-home-layout" class="flex flex-1 flex-col pt-14">', raw):
        bad.append('<main id="nd-home-layout" class="flex flex-1 flex-col pt-14"> missing')
    m = re.search(r'<script src="([^"]*assets/site\.js)" data-root="([^"]*)" data-page="([^"]*)"',
                  raw)
    if not m:
        bad.append("site.js tag with data-root/data-page missing")
    else:
        if m.group(1) != f"{root}/assets/site.js":
            bad.append(f"site.js src {m.group(1)!r} != {root}/assets/site.js")
        if m.group(2) != root:
            bad.append(f"data-root {m.group(2)!r} != {root!r}")
        if not m.group(3):
            bad.append("data-page is empty")

    # --- 4. class coverage -------------------------------------------------
    for attr in re.finditer(r'\sclass="([^"]*)"', raw):
        for tok in attr.group(1).split():
            tok = (tok.replace("&amp;", "&").replace("&gt;", ">").replace("&lt;", "<"))
            if tok in sel or NO_CSS_MARKERS.match(tok):
                continue
            bad.append(f"class {tok!r} has no rule in tw.css / tw-extra.css / site.css")

    # --- 7. unique ids -----------------------------------------------------
    ids = re.findall(r'\sid="([^"]+)"', raw)
    for i in sorted({x for x in ids if ids.count(x) > 1}):
        bad.append(f'duplicate id="{i}"')
    all_ids[str(rel)] = set(ids)

    return bad


def check_links(pages: list[Path], all_ids: dict) -> list[str]:
    bad = []
    for page in pages:
        raw = markup_only(page.read_text(encoding="utf-8", errors="replace"))
        rel = str(page.relative_to(DOCS))
        for m in re.finditer(r'\s(?:href|src)="([^"]+)"', raw):
            ref = m.group(1)
            if ref.startswith(("http://", "https://", "mailto:", "data:", "//")):
                continue
            frag = ""
            if "#" in ref:
                ref, frag = ref.split("#", 1)
            if not ref:                                   # same-page fragment
                if frag and frag not in all_ids[rel]:
                    bad.append(f"{rel}: dead same-page fragment #{frag}")
                continue
            target = (page.parent / ref).resolve()
            if target.is_dir():
                target = target / "index.html"
            if not target.exists():
                bad.append(f"{rel}: dead link {m.group(1)!r}")
                continue
            if frag:
                key = str(target.relative_to(DOCS))
                if key in all_ids and frag not in all_ids[key]:
                    bad.append(f"{rel}: dead fragment {m.group(1)!r} (no id={frag!r})")
    return bad


def check_no_external(pages: list[Path]) -> list[str]:
    """Only <a href> may leave the origin. Everything fetched must be local."""
    bad = []
    for page in pages:
        raw = markup_only(page.read_text(encoding="utf-8", errors="replace"))
        for m in re.finditer(r'<(link|script|img|iframe|source|video|audio)\b[^>]*?'
                             r'\s(?:href|src)="(https?:)?//([^"]+)"', raw, re.I):
            bad.append(f"{page.relative_to(DOCS)}: external <{m.group(1)}> -> //{m.group(3)}")
    for name in ("tw.css", "tw-extra.css", "site.css"):
        css = (DOCS / "assets" / name).read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"url\(\s*['\"]?([^)'\"]+)", css):
            u = m.group(1).strip()
            if u.startswith("data:"):
                continue
            if u.startswith(("http://", "https://", "//")):
                bad.append(f"assets/{name}: external url({u})")
                continue
            target = (DOCS / "assets" / u).resolve()
            if not target.exists():
                bad.append(f"assets/{name}: url({u}) does not exist")
    return bad


def check_site_css() -> list[str]:
    bad = []
    text = (DOCS / "assets" / "site.css").read_text(encoding="utf-8")
    body = re.sub(r"/\*.*?\*/", "", text, flags=re.S)      # drop the header comment
    if "border-radius" in body:
        bad.append("site.css defines border-radius (radius belongs to the vendored build)")
    owned = ("--background", "--foreground", "--primary", "--secondary", "--border",
             "--card", "--muted", "--accent", "--radius", "--ring", "--input",
             "--destructive", "--popover", "--chart", "--sidebar")
    for tok in owned:
        if re.search(re.escape(tok) + r"\s*:", body):
            bad.append(f"site.css redefines the vendored design token {tok}")
    return bad


def check_data_consistency() -> list[str]:
    """Cross-check the two published JSON files. WARNINGS, not failures.

    The shipped bundle deliberately carries one sample task per split while
    leaderboard_data.json holds a real scored day, so the two do not have to
    agree here. On a real publish they must: every id in the board's matrix
    should have a task page, and the board's date should name a suite. The site
    degrades correctly either way (an unpublished id renders as plain text
    rather than a dead link) -- this only tells you what is missing.
    """
    def load(name):
        try:
            return json.loads((DOCS / name).read_text(encoding="utf-8"))
        except Exception:
            return None

    site, board = load("site_data.json"), load("leaderboard_data.json")
    if not site or not board:
        return []
    out = []
    published = {t.get("id") for t in site.get("tasks") or []}
    suites = {s.get("id") for s in site.get("suites") or []}
    matrix = (board.get("matrix") or {}).get("tasks") or []
    missing = [t for t in matrix if t not in published]
    if missing:
        out.append(f"{len(missing)}/{len(matrix)} leaderboard matrix task ids have no page in "
                   f"site_data.json (they render as plain text): {', '.join(missing[:4])}"
                   + (" …" if len(missing) > 4 else ""))
    if board.get("date") and board["date"] not in suites:
        out.append(f'leaderboard_data.date "{board["date"]}" names no suite in site_data.json '
                   f'(suites: {", ".join(sorted(map(str, suites)))}) -- the "today" badge on '
                   "/benchmarks/ can never light up")
    return out


def main() -> int:
    pages = sorted(DOCS.rglob("*.html"))
    sel = css_selectors()
    all_ids: dict[str, set] = {}
    failures = 0

    for page in pages:
        errs = check(page, sel, all_ids)
        if errs:
            failures += len(errs)
            print(f"FAIL {page.relative_to(DOCS)}")
            for e in errs:
                print("     " + e)

    for group in (check_links(pages, all_ids), check_no_external(pages), check_site_css()):
        for e in group:
            failures += 1
            print("FAIL " + e)

    warnings = check_data_consistency()
    for w in warnings:
        print("WARN " + w)

    print(f"\n{len(pages)} pages checked, {failures} problem(s), {len(warnings)} warning(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
