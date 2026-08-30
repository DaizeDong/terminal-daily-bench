#!/usr/bin/env python3
"""verify_site.py -- static invariants for the terminal-daily-bench site.

Run it after any edit under release/docs (and after web/gen_pages.py):

    python3 web/verify_site.py            # -> exit 0 when everything holds

It is deliberately dependency-free and fast, so it can sit in front of a
publish. It checks, for every docs/**/*.html:

  1. STYLESHEET CONTRACT  every page links exactly
         <depth>/assets/tw.css, <depth>/assets/site.css
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
     framework marker classes that intentionally carry no standalone rule.

  5. INTERNAL LINKS       every relative href/src resolves to a real file, or to a
     directory holding an index.html; every #fragment resolves to a real id.

  6. NO EXTERNAL REQUESTS no stylesheet, script, image or CSS url() may point at
     another host. Cross-origin <a href> links are allowed (and expected).

  7. UNIQUE IDS           no id appears twice in one document.

  8. TERMINAL DAILY IDENTITY  site.css must own a complete, self-contained brand
     layer (day-window palette, type hierarchy, flush shell, square component
     geometry, data surfaces, responsive hero, and reduced-motion handling).
     It must not regress to being a verbatim copy of the vendored reference
     stylesheet, and its geometry must stay square: --radius pinned to 0, no
     rounded corner anywhere, and the two drawn circles -- the brand mark's
     discs and the confidence-interval point estimate -- still round. That
     last rule used to be its own opposite; see check_square_geometry.

  9. PUBLIC INFORMATION ARCHITECTURE  the home page presents status, leaderboard,
     then tasks; core catalogue pages put published data ahead of explanation;
     integrity and current reproducibility limits stay visible; retired marketing
     panels and a previously shipped duplicate-JavaScript declaration stay gone.

 10. SUITE MEMBERSHIP     registry counts, per-suite ledgers, the published
     bidirectional task index, and fresh/carried provenance agree exactly.
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

# Marker classes emitted by framework integrations with no standalone CSS rule.
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
    for name in ("tw.css", "site.css"):
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
    sheets = [h.split("?", 1)[0] for h in
              re.findall(r'<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"', raw)]
    want = [f"{root}/assets/{n}" for n in ("tw.css", "site.css")]
    if sheets != want:
        bad.append(f"stylesheets {sheets} != {want}")

    # --- 3. shell ----------------------------------------------------------
    if not re.search(r'<main id="nd-home-layout" class="flex flex-1 flex-col pt-14">', raw):
        bad.append('<main id="nd-home-layout" class="flex flex-1 flex-col pt-14"> missing')
    # "?v=<token>" is a cache-buster, not part of the path -- see check_links.
    m = re.search(r'<script src="([^"]*assets/site\.js)(?:\?[^"]*)?" '
                  r'data-root="([^"]*)" data-page="([^"]*)"', raw)
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
            bad.append(f"class {tok!r} has no rule in tw.css / site.css")

    # --- 7. unique ids -----------------------------------------------------
    ids = re.findall(r'\sid="([^"]+)"', raw)
    for i in sorted({x for x in ids if ids.count(x) > 1}):
        bad.append(f'duplicate id="{i}"')
    all_ids[str(rel)] = set(ids)

    return bad


def _visible_text(raw: str) -> str:
    """The page minus its comments.

    A command inside a JS or HTML comment is not an instruction to anybody, and
    counting it means a comment that EXPLAINS a bad command gets reported as the
    bad command. Script bodies themselves stay in: pages build their command
    strings in JS, and those are exactly what a reader ends up copying.
    """
    raw = re.sub(r"<!--.*?-->", " ", raw, flags=re.S)
    raw = re.sub(r"/\*.*?\*/", " ", raw, flags=re.S)
    return re.sub(r"(?m)(^|\s)//[^\n]*", " ", raw)


def _cli_surface() -> dict:
    """The real `tdb` command surface, read out of argparse itself.

    Parsed from the source rather than imported: verify_site runs in CI where
    the package need not be installed, and an ImportError here would turn this
    check into a no-op that still prints green.
    """
    src = (HERE.parent / "terminal_daily_bench" / "cli.py").read_text(
        encoding="utf-8", errors="replace")
    if "add_subparsers" not in src:
        raise GitError("cli.py has no add_subparsers -- cannot read the command "
                       "surface, so command claims on the site cannot be checked")
    surface: dict = {}
    # sub.add_parser("run", ...) assigned to a local, then <local>.add_argument("--x")
    var_for = {}
    for m in re.finditer(r"(\w+)\s*=\s*sub\.add_parser\(\s*[\"'](\w[\w-]*)[\"']", src):
        var_for[m.group(1)] = m.group(2)
        surface[m.group(2)] = set()
    for m in re.finditer(r"(\w+)\.add_argument\(\s*[\"']([^\"']+)[\"']"
                         r"(?:\s*,\s*[\"']([^\"']+)[\"'])?", src):
        name = var_for.get(m.group(1))
        if not name:
            continue
        for opt in (m.group(2), m.group(3)):
            if opt and opt.startswith("-"):
                surface[name].add(opt)
    if not surface:
        raise GitError("no subcommands parsed out of cli.py -- refusing to report "
                       "a clean command check that examined nothing")
    return surface


def check_commands(pages: list[Path]) -> list[str]:
    """Every `tdb ...` the site tells a reader to run must actually be runnable.

    The leaderboard once shipped `tdb run --suite <date> -a <agent> -m <model>`
    behind a COPY BUTTON. None of those three flags exist; `tdb run` takes a
    positional model and task. It was invented by analogy with the reference
    site and no check on the site could see it, because a command is just text.
    """
    surface = _cli_surface()
    bad: list[str] = []
    seen: set = set()
    # a command run, up to the end of the line/tag/quote it lives in
    cmd = re.compile(r"tdb\s+([a-z][a-z-]*)((?:\s+(?:--?[\w-]+|&lt;[^&]*&gt;|[^<\"'\s])+)*)")
    for page in pages:
        raw = _visible_text(page.read_text(encoding="utf-8", errors="replace"))
        rel = page.relative_to(DOCS)
        for m in cmd.finditer(raw):
            sub, rest = m.group(1), m.group(2) or ""
            key = (str(rel), sub, rest.strip())
            if key in seen:
                continue
            seen.add(key)
            if sub not in surface:
                bad.append(f"{rel}: `tdb {sub}` is not a subcommand "
                           f"(have: {', '.join(sorted(surface))})")
                continue
            for flag in re.findall(r"(?<![\w-])(--?[A-Za-z][\w-]*)", rest):
                if flag not in surface[sub]:
                    bad.append(f"{rel}: `tdb {sub}` has no option {flag} "
                               f"(has: {', '.join(sorted(surface[sub])) or 'none'})")
    return bad


def check_silent_catches(pages: list[Path]) -> list[str]:
    """A rejected fetch must never be rendered as an empty result.

    Fourteen call sites used `.catch(function () { return null; })`. Downstream
    code then drew its empty state, so a broken deploy, a 404 and a genuinely
    empty catalogue all produced the same page -- "No suites are published."
    Nobody, inside or outside, could tell which had happened.

    `T.fetchFailed(what)` is the replacement: same null, plus a console error
    and a banner that says the data could not be READ. This check bans the bare
    form coming back, in the pages and in the generator that writes them.
    """
    bad: list[str] = []
    silent = re.compile(
        r"\.catch\(\s*function\s*\([^)]*\)\s*\{\s*return\s*(null|\[\]|\{\}|)\s*;?\s*\}\s*\)")
    sources = list(pages) + sorted((DOCS / "assets").glob("*.js"))
    sources += [HERE / "gen_pages.py"]
    for src in sources:
        raw = _visible_text(src.read_text(encoding="utf-8", errors="replace"))
        try:
            rel = src.relative_to(DOCS)
        except ValueError:
            rel = src.name
        for m in silent.finditer(raw):
            line = raw.count("\n", 0, m.start()) + 1
            bad.append(f"{rel}:{line}: a rejected fetch is swallowed into "
                       "an empty result -- use T.fetchFailed(<what>) instead")
    return bad


def check_asset_versions(pages: list[Path]) -> list[str]:
    """Every ?v= on the site must match the assets that are actually shipped.

    The token used to be a hand-typed literal in two unrelated places: the
    generator, and every hand-written page. Change an asset, forget one, and the
    browser serves a stale stylesheet against fresh markup -- which is
    indistinguishable from the CSS edit not having worked. It happened the first
    time it could.

    Run `python web/asset_version.py --stamp` to fix.
    """
    sys.path.insert(0, str(HERE))
    try:
        from asset_version import current, stale          # noqa: PLC0415
    except Exception as exc:                              # noqa: BLE001
        # An import failure here would otherwise silently retire the check.
        return [f"cannot read the asset version ({exc}) -- the ?v= stamps are unchecked"]
    return stale(current())


def check_published_days() -> list[str]:
    """Every published day must say where it came from, and match the index.

    While the results bridge was being tested, two SYNTHETIC days sat in
    docs/data/days/ and rendered on the leaderboard as measured results. Nothing
    on the page or in the file distinguished them from a real campaign, because
    the emitter stamped no provenance at all. A day file must now carry
    source/source_files/source_digest, and this refuses one without them.

    It also checks the index against the directory in both directions: an index
    naming a missing day is a 404 the reader sees as a broken page, and a day
    file missing from the index is data nobody can reach.
    """
    days_dir = DOCS / "data" / "days"
    index_path = DOCS / "data" / "index.json"
    if not days_dir.is_dir():
        return [] if not index_path.is_file() else [
            "data/index.json exists but data/days/ does not"]

    bad: list[str] = []
    on_disk = set()
    for path in sorted(days_dir.glob("*.json")):
        on_disk.add(path.stem)
        try:
            day = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:                              # noqa: BLE001
            bad.append(f"data/days/{path.name}: unreadable ({exc})")
            continue
        if not day.get("source"):
            bad.append(f"data/days/{path.name}: no `source` -- a day with no "
                       "provenance cannot be told from one assembled by hand")
        if day.get("date") != path.stem:
            bad.append(f"data/days/{path.name}: date is {day.get('date')!r}")
        if day.get("official_ranking") is True and not day.get("source_digest"):
            bad.append(f"data/days/{path.name}: claims official_ranking with no "
                       "source_digest to bind it to its inputs")

    try:
        listed = set(json.loads(index_path.read_text(encoding="utf-8")).get("days") or [])
    except Exception as exc:                                  # noqa: BLE001
        return bad + [f"data/index.json: unreadable ({exc})"]
    for missing in sorted(listed - on_disk):
        bad.append(f"data/index.json lists {missing} but data/days/{missing}.json is absent")
    for orphan in sorted(on_disk - listed):
        bad.append(f"data/days/{orphan}.json exists but the index does not list it")
    return bad


_JS_STRING = re.compile(
    r'"(?:[^"\\\n]|\\.)*"'      # double quoted, escapes allowed
    r"|'(?:[^'\\\n]|\\.)*'"     # single quoted
    r"|`(?:[^`\\]|\\.)*`",         # template, may span lines
)


def _strip_js_strings(src: str) -> str:
    """Replace string-literal contents with spaces, character for character.

    Tailwind class names live in JS strings and are full of things that parse
    as calls -- "[&:has([role=checkbox])]", ":not([class*='size-'])" -- so a
    scan for calls has to blank them first.

    A hand-rolled state machine was tried and got this exactly backwards: one
    unbalanced quote earlier in the file left it permanently "inside a string",
    so it blanked the CODE and preserved the STRINGS, and then reported half
    the file's own functions as undefined. Matching whole literals cannot drift
    that way -- an unterminated quote simply fails to match and is left alone.
    Length and newlines are preserved so line numbers still line up.
    """
    def blank(m: "re.Match[str]") -> str:
        return "".join("\n" if c == "\n" else " " for c in m.group(0))
    return _JS_STRING.sub(blank, src)

def check_js_definitions(pages: list[Path]) -> list[str]:
    """Nothing may be called or exported that is not defined.

    `node --check` only parses; it never resolves a name. Twice in one session
    an edit that replaced a function by slicing "from here to there" also ate
    the function that happened to sit in between -- once `taskCard`, once
    `fetchFailed` -- and both times the file still parsed, still shipped, and
    only threw in a browser on a page nobody had reopened.

    Two cheap resolutions catch that class:
      * every name a runtime exports on `window.TDB` must be defined in the
        same file;
      * every bare call `name(...)` in a page's inline script must be defined
        in that script, reached through `T.`/`TDB.`, or be a browser global.
    """
    KNOWN = {
        "Array", "Boolean", "Date", "Error", "JSON", "Math", "Number", "Object",
        "Promise", "RegExp", "String", "Set", "Map", "parseInt", "parseFloat",
        "isNaN", "isFinite", "encodeURIComponent", "decodeURIComponent",
        "setTimeout", "clearTimeout", "setInterval", "fetch", "alert",
        "requestAnimationFrame", "console", "document", "window", "history",
        "location", "navigator", "if", "for", "while", "switch", "catch",
        "function", "return", "typeof", "new",
    }
    define = re.compile(r"function\s+([A-Za-z_$][\w$]*)\s*\(|"
                        r"var\s+([A-Za-z_$][\w$]*)\s*=\s*function|"
                        r"var\s+([A-Za-z_$][\w$]*)\s*=")
    call = re.compile(r"(?<![\w.$])([A-Za-z_$][\w$]*)\s*\(")

    bad: list[str] = []

    for js in sorted((DOCS / "assets").glob("*.js")):
        src = _visible_text(js.read_text(encoding="utf-8", errors="replace"))
        scan = _strip_js_strings(src)
        defined = {g for m in define.finditer(src) for g in m.groups() if g}
        # the LAST window.TDB literal is the export; an earlier one is the
        # file's own docstring describing it
        starts = [m.start() for m in re.finditer(r"window\.TDB\s*=\s*\{", src)]
        if not starts:
            continue
        chunk = src[starts[-1]:]
        chunk = chunk[:chunk.index("}") + 1]
        for name in sorted(set(re.findall(r"([A-Za-z_$][\w$]*)\s*[:,}]", chunk))):
            if name and name not in defined and name not in KNOWN:
                bad.append(f"assets/{js.name}: window.TDB exports {name!r}, "
                           "which is not defined in this file")

    for page in pages:
        raw = page.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"<script>\n(.*?)</script>", raw, re.S)
        if not m:
            continue
        src = _visible_text(m.group(1))
        defined = {g for mm in define.finditer(src) for g in mm.groups() if g}
        for name in set(call.findall(_strip_js_strings(src))):
            if name in defined or name in KNOWN:
                continue
            if re.search(r"[\w$]\.\s*" + re.escape(name) + r"\s*\(", src):
                continue          # a method call, e.g. T.dayNav(...)
            bad.append(f"{page.relative_to(DOCS)}: calls {name}(), which is not "
                       "defined in this script")
    return bad


def check_entities_in_text_nodes(pages: list[Path]) -> list[str]:
    """An HTML entity assigned through textContent renders as its own source.

    `el.textContent = "loading&hellip;"` puts the eight characters "&hellip;"
    on the screen, because textContent does not parse markup. The same string
    in the static HTML is correct, so this cannot be a plain grep for the
    entity -- it has to be a grep for the entity ON THE ASSIGNMENT.

    Found in registry/index.html, where the same line was also claiming to be
    "loading" inside the branch that runs after loading has finished and found
    nothing. Both halves were invisible to every other check the site has.
    """
    bad: list[str] = []
    # Capture to end of LINE, not to the next ";". An entity ENDS in a
    # semicolon, so a "[^;]" capture stops at the "&hellip;" it is hunting
    # for and the check silently finds nothing. It was written that way
    # first, and a mutation test caught it printing a clean zero with the
    # bug put back in.
    assign = re.compile(r"\.(?:textContent|nodeValue)\s*=\s*([^\n]+)")
    entity = re.compile(r"&(?:[A-Za-z][A-Za-z0-9]{1,31}|#\d{1,7}|#[Xx][0-9A-Fa-f]{1,6});")
    for page in pages + sorted((DOCS / "assets").glob("*.js")):
        raw = page.read_text(encoding="utf-8", errors="replace")
        try:
            rel = page.relative_to(DOCS)
        except ValueError:
            rel = page
        for m in assign.finditer(raw):
            hit = entity.search(m.group(1))
            if hit:
                line = raw.count("\n", 0, m.start()) + 1
                bad.append(f"{rel}:{line}: {hit.group(0)!r} assigned through "
                           "textContent renders literally")
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
            # A query string is not part of the path. Assets carry a cache-busting
            # "?v=<token>" so a reader with a tab open across a deploy does not
            # keep the old CSS against the new data; without this the checker read
            # "site.css?v=20260822b" as a filename and reported 101 dead links for
            # files that were all present. A link checker that cannot resolve a
            # URL the browser resolves is reporting on itself, not on the site.
            if "?" in ref:
                ref = ref.split("?", 1)[0]
            if not ref:
                # Same-page: "#frag" or "?query#frag". This used to sit behind
                # an IDENTICAL `if not ref: continue` one line above, so the
                # branch was unreachable and no same-page fragment on the site
                # was ever checked -- a dead check that read as a live one.
                if frag and frag not in all_ids.get(rel, ()):
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
    for name in ("tw.css", "site.css"):
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
    body = re.sub(r"/\*.*?\*/", "", text, flags=re.S)

    # WHAT THIS GATE IS FOR, and what it is not for.
    #
    # Its purpose -- visible in the banned phrases below -- is that this site
    # must not become a verbatim copy of the reference benchmark's stylesheet.
    # That is a real constraint and it stays.
    #
    # It used to enforce that by requiring SPECIFIC DECORATIONS to exist: a
    # conic-gradient blob behind the home masthead, and a bordered card rail of
    # published suites. Those are one designer's answer to the constraint, not
    # the constraint. When the brief changed to a dense status page -- label,
    # value, note, hairline rules, no card -- the gate failed the new design
    # while the old rules sat in the stylesheet applying to nothing, and it
    # would have gone on printing green for exactly that dead code.
    #
    # So: assert the identity (own palette, own type hierarchy, own brand mark,
    # own controls), assert the anti-clone bans, and let the decoration be a
    # design decision. Each marker below must be a selector or token this site
    # actually SHIPS, so a rule deleted as dead code fails here rather than
    # being quietly preserved to satisfy a checker.
    required = {
        "day-window palette": ("--td-paper", "--td-night", "--td-coral", "--td-sun"),
        # WAS ("--td-font-body", "--td-font-display", "--td-font-data") under
        # the label "humanist/display/data type hierarchy". The site now ships
        # ONE physical family and keeps those three names as aliases of it, so
        # that marker would have gone on printing green while the hierarchy it
        # named no longer existed -- the same vacuous-marker failure the
        # "own metric treatment" comment below records. What is actually load
        # bearing after the unification is that the one family is DECLARED and
        # that the legacy names still resolve, so that is what is asserted.
        "single type family with legacy aliases": (
            "--td-font", "--td-font-body", "--td-font-display", "--td-font-data"
        ),
        "five-step type scale": ("--ts-micro", "--ts-body", "--ts-lead",
                                 "--ts-sub", "--ts-title"),
        "nine-step spacing scale": ("--sp-0", "--sp-4", "--sp-7", "--sp-8",
                                    "--chrome-h"),
        "branded shell": ("#nd-nav", ".tdb-brand", ".tdb-brand-mark"),
        "own day navigation": (".tdb-daynav", ".tdb-daynav-arrow", ".tdb-suiterail"),
        "own status treatment": (".tdb-statrow", ".tdb-block-head"),
        # was ("border-radius") when a metric was a rounded card. The cards
        # are flat now -- and site-wide the geometry is square, so
        # "border-radius" still appeared in the file only in the rules setting
        # it to 0. A marker satisfied by the code that removes the thing it
        # names is not a check. (The geometry itself is asserted by
        # check_square_geometry, not by any substring marker here.)
        "own metric treatment": ('[data-slot="card"]', "[data-tdb-stat-value]"),
        "data-table surface": ('[data-slot="table-container"]', "border-collapse"),
        "mobile layout": ("@media (max-width: 639px)",),
        "reduced motion": ("@media (prefers-reduced-motion: reduce)",),
    }
    for label, markers in required.items():
        missing = []
        for marker in markers:
            # Two ways a bare substring test passed on a stylesheet that no
            # longer had the thing:
            #   * a custom property REFERENCED but not declared -- delete
            #     "--td-coral: #..." and every "var(--td-coral)" still spells it;
            #   * a class matched by a longer sibling -- delete ".tdb-daynav {"
            #     and ".tdb-daynav-arrow" still contains ".tdb-daynav".
            # So: a property must be declared, and a class must appear as a
            # whole selector rather than as somebody else's prefix.
            if marker.startswith("--"):
                found = f"{marker}:" in body
            elif marker.startswith((".", "#")):
                found = bool(re.search(re.escape(marker) + r"(?![\w-])", body))
            else:
                found = marker in body
            if not found:
                missing.append(marker)
        if missing:
            bad.append(f"site.css missing {label}: {', '.join(missing)}")

    retired = (
        "square, hairline, mono, no shadow",
        "copied verbatim from the reference",
        "byte-equality with the reference",
        "everything visual comes from the vendored",
    )
    lower = text.lower()
    for phrase in retired:
        if phrase in lower:
            bad.append(f"site.css retains retired reference treatment: {phrase!r}")

    bad.extend(check_square_geometry(body))
    return bad


# -- GEOMETRY ---------------------------------------------------------------
#
# The site is SQUARE by decision: zero radius everywhere, with exactly two
# exceptions that are geometry rather than chrome (the two discs in the brand
# mark, and the plotted point estimate on a confidence interval).
#
# This replaces the inverse gate, which read:
#
#     if re.search(r"--radius\s*:\s*0(?:rem|px)?\s*;", body):
#         bad.append("site.css collapses the Terminal Daily rounded geometry
#                     to zero")
#     if body.count("border-radius") < 8:
#         bad.append("site.css rounded component geometry is incomplete")
#
# It was rewritten rather than removed. Deleting it would have left the new
# decision resting on nothing: the next person to paste in a component with a
# 0.5rem corner would get a green run. A decision worth codifying in one
# direction is worth codifying in the other, at the same strength.
#
# The old second check counted `border-radius` occurrences, on the theory that
# a stylesheet with too few of them had not finished styling its components.
# That question does not survive the flip -- under square geometry the healthy
# count is unbounded below, because one zeroed token squares most of the page.
# The completeness question that DOES survive is the same question asked the
# other way round: not "are enough corners rounded" but "is any corner
# rounded". So every border-radius in the file is classified, and anything
# that is neither square nor a documented circle is reported with its
# selector.

_CSS_RULE = re.compile(r"(?P<sel>[^{}]+)\{(?P<decl>[^{}]*)\}")
# Both the shorthand and the four longhands. A verify pass found that
# `border-top-left-radius: 8px` slipped through a shorthand-only regex --
# a gate that can be evaded by spelling the property differently is not a
# gate. `border-radius` alone would also match the longhands' prefix, so
# the alternation is ordered longest-first and anchored on the colon.
_BORDER_RADIUS = re.compile(
    r"border-(?:top|bottom)-(?:left|right)-radius\s*:\s*([^;}]+)"
    r"|border-radius\s*:\s*([^;}]+)")
_RADIUS_TOKEN = re.compile(r"(--radius[\w-]*)\s*:\s*([^;}]+)")
# Token NAMES referenced inside a value, so an allowance can compare names
# rather than substrings (var(--radius-2xl) is not var(--radius)).
_VAR_REF = re.compile(r"var\(\s*(--[\w-]+)")

# The two exceptions, by the selector that owns each. Both are commented at
# their own rule in site.css; both are drawn shapes, not container corners.
_CIRCLE_SELECTORS = (
    ".tdb-brand-mark::before",  # the coral disc behind the mark
    ".tdb-brand-mark::after",   # the hollow ring sitting on it
    ".tdb-ci-dot",              # a plotted point estimate on a CI whisker
)


def _css_rules(body: str):
    """Yield (selector, declarations) for each flat rule in a stylesheet.

    Rules nested one level inside @media come through individually; the
    @media prelude itself never matches, since a prelude cannot span a brace.
    """
    for match in _CSS_RULE.finditer(body):
        yield " ".join(match.group("sel").split()), match.group("decl")


def _radius_value(raw: str) -> str:
    return " ".join(re.sub(r"!important", "", raw, flags=re.I).split()).lower()


def _is_square(value: str) -> bool:
    """True when every corner in the shorthand is zero.

    `0`, `0px` and `0 0 0 0` are the same shape. `0 0 6px 6px` is not, and it
    is exactly the half-measure a bare `"border-radius: 0" in body` substring
    test would have waved through.
    """
    corners = value.split("/")[0].split()
    return bool(corners) and all(
        re.fullmatch(r"0(?:rem|px|em|%)?", corner) for corner in corners)


def _is_circular(value: str) -> bool:
    """True for the disc/pill idiom, as opposed to a rounded corner.

    999px, 9999px, 50% and Tailwind's calc(infinity*1px) / 3.40282e38px all
    mean "make this round". A 0.5rem corner does not, and must not be able to
    pass itself off as one of the two geometry exceptions.
    """
    if re.fullmatch(r"calc\(\s*infinity\s*\*\s*1px\s*\)", value):
        return True
    match = re.fullmatch(r"(\d+(?:\.\d+)?(?:e\+?\d+)?)(px|rem|%)", value)
    if not match:
        return False
    size, unit = float(match.group(1)), match.group(2)
    return {"%": size >= 50, "px": size >= 100, "rem": size >= 6}[unit]


def check_square_geometry(body: str) -> list[str]:
    """Fail closed when the square geometry decision is reversed by accident.

    ``body`` is site.css with comments stripped.
    """
    bad: list[str] = []

    # 1. --radius is declared, and pinned to zero.
    #
    #    Every vendored tw.css corner utility is arithmetic over this one
    #    token: .rounded-lg is var(--radius), .rounded-md is
    #    calc(var(--radius) - 2px), .rounded-xl is calc(var(--radius) + 4px).
    #    Pinning it squares all of them without a rule each -- which is why
    #    the file is allowed to go on writing `border-radius: var(--radius)`
    #    in the rules below.
    #
    #    DECLARED and ZERO are two requirements, not one. tw.css ships its own
    #    `--radius` declaration, so deleting site.css's line does not mean "no
    #    radius" -- it means the vendored value silently wins and every
    #    .rounded-* utility on the site comes back.
    tokens = _RADIUS_TOKEN.findall(body)
    if not any(name == "--radius" for name, _ in tokens):
        bad.append(
            "site.css does not declare --radius: the site's geometry is "
            "square, and tw.css declares its own --radius, so an absent "
            "declaration hands every .rounded-* utility back to the vendor")
    for name, raw in tokens:
        value = _radius_value(raw)
        if not _is_square(value):
            bad.append(
                f"site.css declares {name}: {value} -- the site's geometry is "
                "square; this token must be 0")

    # The tokens clause 1 just proved square. Only these may be referenced as
    # an allowance below; a var() naming anything else is the vendor's value.
    declared_tokens = {name for name, _ in tokens}

    # 2. Nothing else in the file rounds anything, and the two shapes that are
    #    geometry rather than chrome are still round.
    circles: dict[str, str] = {}
    for selector, decl in _css_rules(body):
        owner = next(
            (circle for circle in _CIRCLE_SELECTORS
             if re.search(re.escape(circle) + r"(?![\w-])", selector)), None)
        for pair in _BORDER_RADIUS.findall(decl):
            raw = pair[0] or pair[1]
            value = _radius_value(raw)
            if owner is not None:
                circles[owner] = value
                if not _is_circular(value):
                    bad.append(
                        f"site.css gives {owner} border-radius: {value} -- "
                        "the brand mark's discs and the CI point estimate are "
                        "drawn GEOMETRY, not container chrome; squaring them "
                        "deletes a logo and turns a point estimate into a "
                        "third tick mark on a whisker that already has two")
                continue
            # Only a token THIS file declares is known to be zero. A verify
            # pass found `var(--radius-2xl)` passing here: it is declared in
            # vendored tw.css at 16px, never checked by clause 1, so the
            # allowance handed the corner straight back to the vendor.
            #  -- and matched EXACTLY. `f"var(--radius" in value` is a prefix
            #     test, so it also accepts var(--radius-2xl); the token names
            #     referenced have to be pulled out and compared as names.
            referenced = set(_VAR_REF.findall(value))
            if _is_square(value) or (referenced and referenced <= declared_tokens):
                continue
            shape = "a disc/pill" if _is_circular(value) else "a rounded corner"
            bad.append(
                f"site.css gives {selector!r} border-radius: {value} -- "
                f"{shape} outside the two documented geometry exceptions; "
                "the site's component geometry is square")
    for circle in _CIRCLE_SELECTORS:
        if circle not in circles:
            bad.append(
                f"site.css no longer gives {circle} a border-radius at all: "
                "it is one of the two shapes that must stay round")

    # 3. The one utility --radius cannot reach.
    #
    #    tw.css hardcodes .rounded-full to 3.40282e38px instead of deriving it
    #    from the token, so zeroing --radius does not touch it. Measured on
    #    the running site: the theme switch and its toggle buttons, emitted by
    #    site.js, stay pills at --radius: 0 -- the only rounded chrome left on
    #    an otherwise square page. Either site.css squares that utility, or
    #    nothing the site ships asks for it.
    emitters = [DOCS / "assets" / "site.js", *sorted(DOCS.rglob("*.html"))]
    shipping = [path for path in emitters if path.exists()
                and "rounded-full" in path.read_text(
                    encoding="utf-8", errors="replace")]
    if shipping:
        neutralised = any(
            "rounded-full" in selector
            and any(_is_square(_radius_value(raw))
                    for pair in _BORDER_RADIUS.findall(decl)
                    for raw in (pair[0] or pair[1],))
            for selector, decl in _css_rules(body))
        if not neutralised:
            where = ", ".join(str(path.relative_to(DOCS)) for path in shipping[:3])
            bad.append(
                "site.css does not square the vendored .rounded-full utility, "
                f"which {where} still ships: tw.css hardcodes it to "
                "3.40282e38px rather than var(--radius), so --radius: 0 "
                "cannot reach it and those controls render as pills")

    return bad


_DATED_SUITE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _primary_suite(suite_ids: set[str]) -> str:
    ordered = sorted(suite_ids)
    dated = [sid for sid in ordered if _DATED_SUITE.fullmatch(sid)]
    return (dated or ordered)[-1] if ordered else ""


def check_suite_membership(release: Path | None = None) -> list[str]:
    """Fail closed when the public suite/task bipartite index disagrees.

    The emitter's ``tasks/.suite-<id>.json`` files are authoritative for dated
    suites.  Registry suites with an explicit ``path`` are the backwards-
    compatible source for packages that predate those ledgers.  This check
    independently rebuilds both directions and compares registry.json,
    site_data.json, origin counts, and each task's membership list.
    """
    release = (release or HERE.parent).resolve()
    task_root = release / "tasks"
    bad: list[str] = []

    def load(path: Path, label: str):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 -- gate reports malformed inputs
            bad.append(f"{label}: unreadable JSON ({exc})")
            return None

    registry = load(release / "registry.json", "registry.json")
    site = load(release / "docs" / "site_data.json", "site_data.json")
    if not isinstance(registry, dict) or not isinstance(site, dict):
        return bad

    def index_rows(rows, label: str) -> dict[str, dict]:
        if not isinstance(rows, list):
            bad.append(f"{label}: expected a list")
            return {}
        out = {}
        for pos, row in enumerate(rows):
            if not isinstance(row, dict) or not row.get("id"):
                bad.append(f"{label}[{pos}]: missing object id")
                continue
            sid = str(row["id"])
            if sid in out:
                bad.append(f"{label}: duplicate id {sid!r}")
                continue
            out[sid] = row
        return out

    registry_suites = index_rows(registry.get("suites"), "registry.json suites")
    site_suites = index_rows(site.get("suites"), "site_data.json suites")
    site_tasks = index_rows(site.get("tasks"), "site_data.json tasks")

    expected_by_suite: dict[str, set[str]] = {}
    expected_by_task: dict[str, set[str]] = {}
    origin_counts: dict[str, dict[str, int]] = {}
    explicit_tasks: set[str] = set()
    source_suites: set[str] = set()

    def add_edge(sid: str, tid: str, origin: str) -> None:
        ids = expected_by_suite.setdefault(sid, set())
        if tid in ids:
            return
        ids.add(tid)
        expected_by_task.setdefault(tid, set()).add(sid)
        counts = origin_counts.setdefault(
            sid, {"fresh": 0, "carried": 0, "unknown": 0}
        )
        counts[origin if origin in ("fresh", "carried") else "unknown"] += 1

    for member_file in sorted(task_root.glob(".suite-*.json")):
        sid = member_file.name[len(".suite-"):-len(".json")]
        source_suites.add(sid)
        members = load(member_file, str(member_file.relative_to(release)))
        if not isinstance(members, list):
            if members is not None:
                bad.append(f"{member_file.relative_to(release)}: expected a list")
            continue
        seen: set[str] = set()
        for pos, member in enumerate(members):
            where = f"{member_file.relative_to(release)}[{pos}]"
            if not isinstance(member, dict) or not member.get("task"):
                bad.append(f"{where}: missing task id")
                continue
            tid = str(member["task"])
            if tid in seen:
                bad.append(f"{member_file.relative_to(release)}: duplicate task {tid!r}")
                continue
            seen.add(tid)
            explicit_tasks.add(tid)

            mode = member.get("mode")
            if mode not in ("archive", "live"):
                bad.append(f"{where}: mode must be 'archive' or 'live'")
            elif not (task_root / str(mode) / tid).is_dir():
                bad.append(f"{where}: package tasks/{mode}/{tid} is missing")

            window = member.get("suite_window")
            if window is not None and not isinstance(window, dict):
                bad.append(f"{where}: suite_window must be an object")
                window = {}
            origin = (window or {}).get("origin", "unknown")
            if origin not in ("fresh", "carried", "unknown"):
                bad.append(f"{where}: invalid suite_window.origin {origin!r}")
                origin = "unknown"
            add_edge(sid, tid, origin)

    # Legacy/sample suites declare a package path instead of a membership file.
    # A task named by ANY explicit ledger is not implicitly absorbed by a sample
    # path; otherwise every dated archive package would reappear in `sample`.
    for sid, row in registry_suites.items():
        raw_path = row.get("path")
        if not raw_path:
            continue
        source_suites.add(sid)
        path = (release / str(raw_path)).resolve()
        try:
            path.relative_to(release)
        except ValueError:
            bad.append(f"registry suite {sid!r}: path escapes release root")
            continue
        if not path.is_dir():
            bad.append(f"registry suite {sid!r}: path {raw_path!r} is missing")
            continue
        for package in sorted(p for p in path.iterdir() if p.is_dir()):
            if package.name not in explicit_tasks:
                add_edge(sid, package.name, "unknown")

    for sid, row in registry_suites.items():
        if sid not in source_suites and row.get("n_tasks") not in (None, 0):
            bad.append(f"registry suite {sid!r}: no .suite ledger or package path")
        expected_by_suite.setdefault(sid, set())
        origin_counts.setdefault(sid, {"fresh": 0, "carried": 0, "unknown": 0})

    for sid in sorted(set(expected_by_suite) - set(registry_suites)):
        bad.append(f"membership suite {sid!r}: missing registry.json row")
    for sid in sorted(set(site_suites) - set(registry_suites)):
        bad.append(f"site_data suite {sid!r}: missing registry.json row")
    for sid in sorted(set(registry_suites) - set(site_suites)):
        bad.append(f"registry suite {sid!r}: missing site_data.json row")

    for sid, expected_ids in sorted(expected_by_suite.items()):
        registry_row = registry_suites.get(sid)
        site_row = site_suites.get(sid)
        if registry_row is None or site_row is None:
            continue
        expected_n = len(expected_ids)
        if registry_row.get("n_tasks") != expected_n:
            bad.append(
                f"registry suite {sid!r}: n_tasks={registry_row.get('n_tasks')!r} "
                f"!= membership count {expected_n}"
            )

        raw_ids = site_row.get("task_ids")
        if not isinstance(raw_ids, list) or any(not isinstance(v, str) for v in raw_ids):
            bad.append(f"site_data suite {sid!r}: task_ids must be a string list")
            site_ids: set[str] = set()
        else:
            site_ids = set(raw_ids)
            if len(site_ids) != len(raw_ids):
                bad.append(f"site_data suite {sid!r}: duplicate task_ids")
        if site_ids != expected_ids:
            bad.append(
                f"site_data suite {sid!r}: task_ids do not match membership "
                f"(missing={sorted(expected_ids - site_ids)}, "
                f"extra={sorted(site_ids - expected_ids)})"
            )
        if site_row.get("catalogued_tasks") != len(site_ids):
            bad.append(
                f"site_data suite {sid!r}: catalogued_tasks="
                f"{site_row.get('catalogued_tasks')!r} != task_ids count {len(site_ids)}"
            )
        if site_row.get("n_tasks") != registry_row.get("n_tasks"):
            bad.append(
                f"site_data suite {sid!r}: n_tasks={site_row.get('n_tasks')!r} "
                f"!= registry n_tasks {registry_row.get('n_tasks')!r}"
            )

        counts = origin_counts[sid]
        keys = {
            "fresh_tasks": counts["fresh"],
            "carried_tasks": counts["carried"],
            "unknown_origin_tasks": counts["unknown"],
        }
        if any(key in registry_row for key in keys):
            for key, expected in keys.items():
                if registry_row.get(key) != expected:
                    bad.append(
                        f"registry suite {sid!r}: {key}="
                        f"{registry_row.get(key)!r} != membership count {expected}"
                    )
        for key, expected in keys.items():
            if site_row.get(key) != expected:
                bad.append(
                    f"site_data suite {sid!r}: {key}="
                    f"{site_row.get(key)!r} != membership count {expected}"
                )

    for tid, expected_suites in sorted(expected_by_task.items()):
        task = site_tasks.get(tid)
        if task is None:
            bad.append(f"membership task {tid!r}: missing site_data.json task row")
            continue
        raw_suites = task.get("suites")
        if not isinstance(raw_suites, list) or any(not isinstance(v, str) for v in raw_suites):
            bad.append(f"site_data task {tid!r}: suites must be a string list")
            claimed: set[str] = set()
        else:
            claimed = set(raw_suites)
            if len(claimed) != len(raw_suites):
                bad.append(f"site_data task {tid!r}: duplicate suites")
        if claimed != expected_suites:
            bad.append(
                f"site_data task {tid!r}: suites do not match reverse membership "
                f"(expected={sorted(expected_suites)}, got={sorted(claimed)})"
            )

        membership_rows = task.get("suite_memberships")
        if not isinstance(membership_rows, list):
            bad.append(f"site_data task {tid!r}: suite_memberships must be a list")
        else:
            membership_ids = [
                str(row.get("suite"))
                for row in membership_rows
                if isinstance(row, dict) and row.get("suite")
            ]
            if len(membership_ids) != len(membership_rows) or set(membership_ids) != claimed:
                bad.append(
                    f"site_data task {tid!r}: suite_memberships disagree with suites"
                )

        expected_primary = _primary_suite(expected_suites)
        if task.get("suite") != expected_primary:
            bad.append(
                f"site_data task {tid!r}: primary suite {task.get('suite')!r} "
                f"drifted from {expected_primary!r}"
            )

    for tid, task in sorted(site_tasks.items()):
        if tid not in expected_by_task:
            bad.append(f"site_data task {tid!r}: has no registry/membership edge")

    return bad


# The home page was previously pinned to one literal section list,
# ["intro", "status", "leaderboard", "tasks"]. That froze a single layout: any
# rearrangement failed, so the cheapest repair was always to paste the new list
# in, and a check that is rewritten to match whatever it finds asserts nothing.
#
# The property worth defending is that THE RESULTS COME FIRST. It is asserted
# positionally rather than by naming the sections that may not precede the
# table, because a name-based set silently stops matching the moment a section
# is renamed -- the same class of failure as a marker that has gone vacuous.
# At most a masthead (title, tagline, calls to action) may sit above the
# leaderboard, so its index among the home sections must be 0 or 1 whatever the
# other blocks end up being called.
HOME_LEADERBOARD_MAX_INDEX = 1


def check_home_section_order(sections: list[str]) -> list[str]:
    """The leaderboard must exist on home, with at most a masthead above it."""
    bad: list[str] = []
    if not sections:
        bad.append("index.html: no data-tdb-section blocks found")
        return bad
    if len(set(sections)) != len(sections):
        bad.append(f"index.html: duplicate data-tdb-section names in {sections}")
    found = sections.count("leaderboard")
    if found != 1:
        bad.append(
            'index.html: expected exactly one data-tdb-section="leaderboard" '
            f"block, found {found} in {sections}"
        )
        return bad
    index = sections.index("leaderboard")
    if index > HOME_LEADERBOARD_MAX_INDEX:
        bad.append(
            f"index.html: results are not first -- leaderboard is section "
            f"{index} behind {sections[:index]}; at most a masthead may precede "
            f"it (index <= {HOME_LEADERBOARD_MAX_INDEX})"
        )
    return bad


def check_home_results_above_the_fold(home_markup: str) -> list[str]:
    """Nothing that reads like an explainer may sit above the results table.

    `check_home_section_order` counts sections, so it still passes a home page
    whose single pre-table block is an explainer rather than a masthead. This
    closes that gap without naming sections, which would break on a rename: on
    this site the masthead is the h1 block and every explanatory block opens
    with an h2, so an h2 above the leaderboard marker means the reader meets
    prose before numbers.
    """
    marker = 'data-tdb-section="leaderboard"'
    at = home_markup.find(marker)
    if at < 0:
        return ['index.html: no data-tdb-section="leaderboard" block on the home page']
    headings = re.findall(r"<h2\b[^>]*>(.*?)</h2>", home_markup[:at], flags=re.S | re.I)
    if headings:
        titles = [" ".join(re.sub(r"<[^>]+>", " ", h).split()) for h in headings]
        return [
            "index.html: results are not first -- section heading(s) "
            f"{titles} are rendered above the leaderboard table"
        ]
    return []


# Marketing copy that has been removed from the home page. Re-adding any of it
# is a regression, not an edit: the home page states results and the caveat
# that qualifies them, and nothing about how good the project is.
#
# The results-first rebuild was audited for new entries and added none, which
# is a finding rather than an oversight. What it removed was a status grid, an
# integrity disclosure and a task preview -- data and caveats, not self-
# description -- so the phrases it retired ("availability is not ranking
# authority", "latest dated suite", "integrity limits and current blockers")
# are not marketing and do not belong here; banning a caveat would be exactly
# backwards. "what the suite separates" left home but is still a live label on
# /guide/ and /leaderboard/, so it is not retired at all. Copy that is still
# shipped, or that was never written, makes a ban that catches nothing.
#
# What that rebuild actually retired was a set of PANELS, and a phrase list is
# the wrong instrument for those: `check_home_section_order` and
# `check_home_results_above_the_fold` keep them from coming back structurally,
# whatever words they would use. Add a phrase here only after confirming it is
# gone from the whole of docs/; `tests/test_site_home_architecture.py` asserts
# that for every entry.
RETIRED_HOME_PHRASES = (
    "how the universe is grown",
    "we measure the benchmark itself",
    "explore our benchmarks",
    "i want to test my agent",
    # Added with the results-first rebuild. The masthead used to end
    # "Fresh merged pull requests become executable tasks. The catalogue is
    # public." -- the second sentence is the page describing its own feature
    # rather than showing a result, which is what the rebuild removed. Verified
    # absent from every page under docs/, not guessed: a ban-list entry naming
    # copy that still ships (or never shipped) bans nothing while looking like
    # it bans something.
    "the catalogue is public",
)


def check_retired_home_copy(home_lower: str) -> list[str]:
    """Home must not regrow a retired marketing panel."""
    return [
        f"index.html: retired marketing panel returned: {phrase!r}"
        for phrase in RETIRED_HOME_PHRASES
        if phrase in home_lower
    ]


# The integrity disclosure was REMOVED on the owner's instruction: the coral
# quote block on nine pages, the scoring-invariant sentence, the replay-blocker
# ledger, the `#integrity` anchor and the `why` link the UNOFFICIAL badge used
# to carry. The gate that asserted those caveats is gone with them -- asserting
# the presence of deleted copy would fail the build forever, and keeping a dead
# check is worse than keeping none.
#
# What is NOT gone is the reason the caveats existed: these numbers are not a
# certified ranking. The word `unofficial` is now the only thing on the site
# that says so, which makes it load-bearing in a way it never was while the
# disclosure stood behind it. So the check narrows rather than disappears --
# it guards the one marker that remains instead of the ten sentences that did.
#
# Read from the raw source, not markup_only(): both badges are built by JS
# string concatenation, and markup_only() blanks script bodies. That is exactly
# how the old `why` link once pointed at a non-existent anchor with every gate
# green.
UNOFFICIAL_MARKER_PAGES = ("index.html", "leaderboard/index.html")


def check_unofficial_marker(source) -> list[str]:
    """The pages that render a leaderboard must still mark it unofficial."""
    bad = []
    for rel in UNOFFICIAL_MARKER_PAGES:
        raw = source(rel)
        if 'data-official="false"' not in raw or "unofficial" not in raw.lower():
            bad.append(
                f"{rel}: the `unofficial` marker is gone. With the integrity "
                f"disclosure removed this word is the only thing telling a "
                f"reader these numbers are not a certified ranking."
            )
    return bad


def check_public_frontend() -> list[str]:
    """Keep the public surface data-first and its strongest claims qualified.

    This is intentionally a static contract. The site is dependency-free and is
    served directly by GitHub Pages, so regressions in section order or caveat copy
    should fail before publishing without needing a browser or JavaScript runtime.
    """
    bad = []

    def source(rel: str) -> str:
        return (DOCS / rel).read_text(encoding="utf-8", errors="replace")

    home = source("index.html")
    home_markup = markup_only(home)
    sections = re.findall(r'data-tdb-section="([^"]+)"', home_markup)
    bad.extend(check_home_section_order(sections))
    bad.extend(check_home_results_above_the_fold(home_markup))

    lower_home = home.lower()
    bad.extend(check_retired_home_copy(lower_home))

    all_public_html = "\n".join(
        page.read_text(encoding="utf-8", errors="replace").lower()
        for page in DOCS.rglob("*.html")
    )

    bad.extend(check_unofficial_marker(source))

    for rel in ("benchmarks/index.html", "leaderboard/index.html", "registry/index.html"):
        raw = markup_only(source(rel))
        if "data-tdb-primary-data" not in raw:
            bad.append(f"{rel}: primary published data marker missing")

    quickstart = source("guide/quickstart/index.html").lower()
    for phrase in ("private, locally patched harbor", "third party cannot currently run",
                   "no publication date is promised"):
        if phrase not in quickstart:
            bad.append(f"guide/quickstart/index.html: execution dependency caveat missing {phrase!r}")

    try:
        site = json.loads(source("site_data.json"))
    except Exception as exc:
        bad.append(f"site_data.json: cannot verify generated-page caveats ({exc})")
        site = {}
    for kind, records in (("benchmarks", site.get("suites") or []),
                          ("registry", site.get("tasks") or [])):
        for record in records:
            if record.get("status") != "archive" or not record.get("id"):
                continue
            rel = f'{kind}/{record["id"]}/index.html'
            page = DOCS / rel
            if not page.exists():
                continue  # link/data checks report the missing generated page elsewhere
            text = page.read_text(encoding="utf-8", errors="replace").lower()
            if "unpublished patched harbor fork" not in text or "stock harbor 0.13.1" not in text:
                bad.append(f"{rel}: archived-page execution dependency caveat missing")

    submit = source("submit/index.html")
    lower_submit = submit.lower()
    for phrase in ("public bundle does not run a replay worker",
                   "pending rows never enter the verified ranking",
                   "pending submissions",
                   "verified community results",
                   "ed25519-signed v2 receipt",
                   "complete frozen-roster coverage"):
        if phrase not in lower_submit:
            bad.append(f"submit/index.html: verified/pending caveat missing {phrase!r}")
    if "community_verified" not in submit or "community_pending" not in submit:
        bad.append("submit/index.html: must read distinct community_verified/community_pending views")
    if lower_submit.find('id="verified"') > lower_submit.find('id="pending"'):
        bad.append("submit/index.html: verified view must precede the non-ranked pending view")
    submission_guide = " ".join(source("guide/submission/index.html").lower().split())
    for phrase in (
        "pip install -e '.[replay]'",
        "in-process ed25519",
        "does not invoke an external openssl process",
        "canonical absolute path",
        "worker-private attempt directory",
        "harbor_binary_path",
        "harbor_package_root",
        "complete harbor package and network-patch tree",
        "recomputes and compares those facts before and after replay",
        "rejects symlinks and hardlinks",
        "same already-open snapshot bytes",
        "distinct uids",
        "shared ownership plus mode bits is not isolation",
        "fake harbor tests",
        "fake-runner tests are not evidence of a production replay",
        "production replay remains blocked",
        "reachable control canary",
        "blocked isolated canary",
        "signer-only private-key mount",
        "read-only manifest/public-key mounts",
    ):
        if phrase not in submission_guide:
            bad.append(f"guide/submission/index.html: authority caveat missing {phrase!r}")
    for stale in ("on ingest the patch is replayed", "pending cells sit in the denominator",
                  "every listed number was produced by replaying"):
        if stale in lower_submit:
            bad.append(f"submit/index.html: stale replay-worker claim remains {stale!r}")
    for stale in (
        "re-scored on ingest",
        "node worker replays",
        "worker replays your patch",
        "deployment egress canary is still pending",
        "worth zero until replayed",
        "attempt worth zero",
        "execution-verified, false_accept 0",
        "a property of execution scoring, held by construction",
        "why the score cannot be gamed by the model",
    ):
        if stale in all_public_html:
            bad.append(f"public HTML: stale or overbroad integrity claim remains {stale!r}")

    try:
        board = json.loads(source("leaderboard_data.json"))
    except Exception as exc:
        bad.append(f"leaderboard_data.json: cannot verify semantic FA denominators ({exc})")
        board = {}
    for key in ("community_verified", "community_replay_verified", "community_pending"):
        if not isinstance(board.get(key), list):
            bad.append(f"leaderboard_data.json: missing separate {key} collection")
    if board.get("community") != board.get("community_verified"):
        bad.append("leaderboard_data.json: legacy community alias must be verified-only")
    community_suite = board.get("community_suite")
    if (not isinstance(community_suite, dict)
            or community_suite.get("ranking_requires_complete_roster") is not True
            or community_suite.get("official_results_included") is not False):
        bad.append("leaderboard_data.json: community suite authority policy is missing")
    if not board.get("total_fa_n") and board.get("total_fa") is not None:
        bad.append("leaderboard_data.json: total_fa must be null when total_fa_n is zero")
    for row in board.get("leaderboard") or []:
        for scaffold, cell in row.items():
            if not isinstance(cell, dict) or "fa_n" not in cell:
                continue
            if not cell.get("fa_n") and cell.get("fa") is not None:
                bad.append(
                    "leaderboard_data.json: "
                    f"{row.get('model', '<unknown>')}/{scaffold} renders semantic FA "
                    "without measured trials"
                )
    leaderboard_html = source("leaderboard/index.html")
    leaderboard_requirements = (
        'schema_version === "td-relative-capability-v3"',
        "input.frozen_task_roster_n === 50",
        "input.task_roster_digest_trusted === true",
        "input.cell_manifest_digest_trusted === true",
        "scoring.official_ranking === true",
        'scoring.publication_registry_mode === "code-controlled-allowlist"',
        "scoring.publication_bundle_approved === true",
        "scoring.relative_report_digest_matches === true",
        "scoring.anti_cheat_deployment_active === true",
        "rating.publishable === true",
        "ALLOWED_DIMENSIONS[axis.dimension]",
    )
    for phrase in leaderboard_requirements:
        if phrase not in leaderboard_html:
            bad.append(f"leaderboard/index.html: v3 fail-closed marker missing {phrase!r}")

    # How a non-SUCCESS run is treated is a claim about the METHOD, not about one
    # day's table, so it is asserted where the method is documented. It was
    # previously asserted on the leaderboard page; moving the home of a statement
    # is fine, dropping the assertion is not -- these decide how every rate on
    # the site is read, and "are not converted to zero" is the load-bearing one.
    methods = source("guide/quality-methods/index.html").lower()
    for phrase in ("outcome:null",
                   "are not converted to zero",
                   "authenticated_counts",
                   "untrusted_declared_counts",
                   "task-family: unavailable"):
        if phrase not in methods:
            bad.append("guide/quality-methods/index.html: outcome-treatment "
                       f"statement missing {phrase!r}")
    registry_html = source("registry/index.html")
    if 'T.getJSON("leaderboard_data.json")' in registry_html or "board.matrix" in registry_html:
        bad.append("registry/index.html: legacy matrix must not invent task rows or scores")

    scoring = site.get("scoring") if isinstance(site, dict) else None
    if not isinstance(scoring, dict):
        bad.append("site_data.json: machine-readable scoring publication status missing")
    elif scoring.get("official_ranking") is not True:
        leaked = [
            task.get("id", "<unknown>")
            for task in site.get("tasks") or []
            if task.get("solved_by") is not None or task.get("n_models") is not None
        ]
        if leaked:
            bad.append(
                "site_data.json: unranked catalogue leaked task score fields for "
                + ", ".join(leaked)
            )

    shell = source("assets/site.js")
    labels = ['["status"', '["leaderboard"', '["tasks"', '["docs"', '["submit"']
    positions = [shell.find(label) for label in labels]
    if any(pos < 0 for pos in positions) or positions != sorted(positions):
        bad.append("assets/site.js: navigation must order status, leaderboard, tasks, docs, submit")
    if '["run it"' in shell or '["quality"' in shell:
        bad.append("assets/site.js: retired top-level marketing/method navigation returned")

    # Regression for the homepage outage where one declaration ended with '=' and
    # the same declaration began again on the next line. This catches that exact
    # invalid-JavaScript shape in both inline scripts and the shared shell.
    duplicate_declaration = re.compile(
        r"\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*"
        r"(?:var|let|const)\s+\1\b"
    )
    scripts = [shell]
    for page in DOCS.rglob("*.html"):
        raw = page.read_text(encoding="utf-8", errors="replace")
        scripts.extend(m.group(2) for m in _SCRIPT_BODY.finditer(raw) if not m.group(1).lower().startswith('<script src='))
    for script in scripts:
        match = duplicate_declaration.search(script)
        if match:
            bad.append(f"invalid duplicate JavaScript declaration for {match.group(1)!r}")
            break

    return bad


def check_data_consistency() -> list[str]:
    """Cross-check the two published JSON files. WARNINGS, not failures.

    The shipped bundle deliberately carries one sample task per split while
    leaderboard_data.json currently holds a legacy diagnostic snapshot, so the
    two do not have to agree. The v3 frontend ignores that matrix rather than
    rendering it as a score. On a future formal publish, every bound matrix id
    must have a task page and the frozen suite must be present here.
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
        out.append(f"{len(missing)}/{len(matrix)} legacy matrix task ids have no page in "
                   f"site_data.json (v3 frontend ignores this matrix): {', '.join(missing[:4])}"
                   + (" …" if len(missing) > 4 else ""))
    if board.get("date") and board["date"] not in suites:
        out.append(f'leaderboard_data.date "{board["date"]}" names no suite in site_data.json '
                   f'(suites: {", ".join(sorted(map(str, suites)))}) -- this legacy '
                   "snapshot remains diagnostic-only until replaced by formal v3 authority")
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

    for group in (check_links(pages, all_ids), check_entities_in_text_nodes(pages),
                  check_commands(pages), check_silent_catches(pages),
                  check_asset_versions(pages),
                  check_published_days(),
                  check_js_definitions(pages),
                  check_no_external(pages), check_site_css(),
                  check_public_frontend(), check_suite_membership()):
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
