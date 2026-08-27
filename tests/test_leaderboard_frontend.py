"""Dependency-free structural fixtures for the static v3 capability frontend."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOME = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
LEADERBOARD = (ROOT / "docs" / "leaderboard" / "index.html").read_text(
    encoding="utf-8"
)
REGISTRY = (ROOT / "docs" / "registry" / "index.html").read_text(
    encoding="utf-8"
)
SHELL = (ROOT / "docs" / "assets" / "site.js").read_text(encoding="utf-8")
SITE_CSS = (ROOT / "docs" / "assets" / "site.css").read_text(encoding="utf-8")
METHODS = (ROOT / "docs" / "guide" / "quality-methods" / "index.html").read_text(
    encoding="utf-8"
)
DATA_RUNTIME = (ROOT / "docs" / "assets" / "tdb-data.js").read_text(encoding="utf-8")
TASK_FORMAT = (ROOT / "docs" / "guide" / "task-format" / "index.html").read_text(
    encoding="utf-8"
)
TW_CSS = (ROOT / "docs" / "assets" / "tw.css").read_text(encoding="utf-8")
PAGE_GENERATOR = (ROOT / "web" / "gen_pages.py").read_text(encoding="utf-8")

# Every published page as one haystack, case preserved. The home page was
# rebuilt to lead with the leaderboard, which moved several claims off it; the
# assertions below therefore ask whether the SITE still publishes a statement,
# not whether index.html does. Relocating a statement stays legal; losing it
# does not.
PUBLISHED_PAGES = sorted((ROOT / "docs").rglob("*.html"))
PUBLISHED = "\n".join(
    page.read_text(encoding="utf-8", errors="replace") for page in PUBLISHED_PAGES
)
DATA_GENERATOR = (ROOT / "web" / "gen_site_data.py").read_text(encoding="utf-8")


def test_home_and_full_board_require_code_approved_relative_v3_authority():
    for source in (HOME, LEADERBOARD):
        assert 'schema_version === "td-relative-capability-v3"' in source
        assert "scoring.official_ranking === true" in source
        assert (
            'scoring.publication_registry_mode === "code-controlled-allowlist"'
            in source
        )
        assert "scoring.publication_bundle_approved === true" in source
        assert "scoring.relative_report_digest_matches === true" in source
        assert "scoring.anti_cheat_deployment_active === true" in source
        assert "input.frozen_task_roster_n === 50" in source
        assert "input.task_roster_digest_trusted === true" in source
        assert "input.cell_manifest_digest_trusted === true" in source
        assert "publishable === true" in source

    assert "var rows = (board && board.leaderboard) || []" not in HOME
    assert "discoverHarnesses" not in HOME
    assert "KNOWN_HARNESSES" not in LEADERBOARD
    assert "build(b)" not in LEADERBOARD


def test_site_data_generator_rejects_legacy_or_partial_matrix_authority():
    assert 'RELATIVE_SCHEMA = "td-relative-capability-v3"' in DATA_GENERATOR
    assert "FORMAL_TASK_TARGET = 50" in DATA_GENERATOR
    assert 'PUBLICATION_BUNDLE_SCHEMA = "td-relative-publication-bundle-v1"' in DATA_GENERATOR
    assert 'PUBLICATION_REGISTRY_MODE = "code-controlled-allowlist"' in DATA_GENERATOR
    assert "APPROVED_PUBLICATION_BUNDLE_SHA256S" in DATA_GENERATOR
    assert "ANTI_CHEAT_DEPLOYMENT_ACTIVE = False" in DATA_GENERATOR
    assert "matrix_task_id_roster_sha256" in DATA_GENERATOR
    assert "relative_report_digest_matches" in DATA_GENERATOR
    assert "def scoring_status(" in DATA_GENERATOR
    assert "def _published_matrix(" in DATA_GENERATOR
    assert 'state = "awaiting-certified-50-task-results"' in DATA_GENERATOR
    assert '"legacy_snapshot_present": legacy_present' in DATA_GENERATOR


def test_relative_axes_are_authority_bounded_and_task_family_is_unavailable():
    # The enforcement is code and lives with the page that renders. The
    # statement of what is enforced is documentation and lives with the method.
    # Both halves are asserted: an allowlist nobody documents is unauditable,
    # and a documented allowlist nobody enforces is decoration.
    assert (
        "var ALLOWED_DIMENSIONS = { overall: true, language: true, capability: true };"
        in LEADERBOARD
    )
    assert "!ALLOWED_DIMENSIONS[axis.dimension]" in LEADERBOARD

    assert "Task-family: unavailable." in METHODS
    # WAS: assert "canonical C1&ndash;C14" in METHODS. That taxonomy is defined
    # in zero .py files, C5 covers 61/61 tasks (zero bits) and nothing can
    # render it, so the page asserted a label set it could neither produce nor
    # attribute. Deleting the claim without pinning its replacement would let
    # the next edit quietly re-assert one, so the NEW commitment is what is
    # pinned: the dimension is authorised, and it is empty.
    assert "canonical C1&ndash;C14" not in METHODS
    assert "No capability label set is currently published" in METHODS
    assert "does not infer one from tracks, merged labels" in METHODS
    assert "does not display zero" in METHODS
    assert "<code>ALLOWED_DIMENSIONS</code>" in METHODS


def test_non_success_statuses_are_null_not_zero_and_never_ranked():
    for status in ("FAILED", "BLOCKED", "NOT_RUN"):
        assert f"<code>{status}</code>" in METHODS
    assert "<code>outcome:null</code>" in METHODS
    assert "are not converted to zero" in METHODS
    assert "excluded from ratings" in METHODS
    assert "counted in coverage, not outcomes" in METHODS
    # A declaration must never be able to authenticate its own status, so the
    # two tallies are named separately and never summed.
    assert "authenticated_counts" in METHODS
    assert "untrusted_declared_counts" in METHODS
    assert "worth zero" not in PAGE_GENERATOR.lower()
    assert "attempt worth zero" not in PAGE_GENERATOR.lower()


def test_registry_never_reconstructs_tasks_or_scores_from_legacy_matrix():
    assert 'T.getJSON("leaderboard_data.json")' not in REGISTRY
    assert "board.matrix" not in REGISTRY
    assert "Official Solves" in REGISTRY
    assert "means awaiting formal coverage, not zero solves" in REGISTRY
    assert "official score coverage" in REGISTRY


def _nav_table():
    """The NAV literal out of site.js, parsed rather than string-matched.

    Every entry is `["label", "href/", ["page-key", ...]]` with double-quoted
    strings, so the literal is already JSON once the newlines are gone.
    """
    assert "var NAV = [" in SHELL, "site.js no longer declares a NAV array"
    body = SHELL.split("var NAV = ", 1)[1].split("\n  ];", 1)[0]
    return json.loads(body + "\n  ]")


def test_the_quality_report_is_reachable_without_typing_the_url():
    """/quality/ was an orphan: reachable only by typing the URL.

    A top-level nav row is the obvious fix and is the wrong one --
    verify_site.py pins the header to five items and explicitly bans a
    top-level quality entry as retired navigation. So `quality` stays a
    `docs` key and the entrances live in the pages: the home masthead, the
    leaderboard foot, and the docs shortcut rail. Each is asserted here
    because losing any one of them puts the report back out of reach, and
    nothing else in the suite would notice.
    """
    nav = _nav_table()

    # the pinned five, in the pinned order, with quality NOT among them
    assert [row[0] for row in nav] == [
        "status", "leaderboard", "tasks", "docs", "submit"
    ]

    # every key belongs to exactly one row, or two header items light at once
    keys = [k for row in nav for k in row[2]]
    assert len(keys) == len(set(keys)), "a page key lights up two nav items"

    # landing on the report lights `docs`, which is the row that owns the key
    owners = [row[0] for row in nav if "quality" in row[2]]
    assert owners == ["docs"], owners

    quality_page = (ROOT / "docs" / "quality" / "index.html").read_text(
        encoding="utf-8")
    assert 'data-page="quality"' in quality_page
    assert 'id="discrimination"' in quality_page

    # In-page entrances. The home masthead used to carry one; the results-first
    # rebuild cut it, so home is no longer named here. What is still required is
    # the property that made the list worth asserting: the report must be
    # reachable from more than one page, and specifically from the leaderboard,
    # which is where the numbers the report qualifies are printed. Naming the
    # pages individually is what made this test brittle; naming the leaderboard
    # is not brittleness, it is the point.
    linking = [
        page for page in PUBLISHED_PAGES
        if page.parent.name != "quality"
        and "quality/#discrimination" in page.read_text(
            encoding="utf-8", errors="replace")
    ]
    assert len(linking) >= 2, (
        "the discrimination report is reachable from "
        f"{len(linking)} page(s); it was an orphan once already")
    assert (ROOT / "docs" / "leaderboard" / "index.html") in linking, (
        "the leaderboard lost its link to the discrimination report")


def _registry_columns():
    assert "var COLS = [" in REGISTRY, "the registry no longer declares COLS"
    block = REGISTRY.split("var COLS = ", 1)[1].split("\n  ];", 1)[0]
    block = re.sub(r"/\*.*?\*/", " ", block, flags=re.S)
    return re.findall(r'key:\s*"([^"]+)",\s*label:\s*"([^"]+)"', block)


def test_the_declared_difficulty_facet_has_a_column_to_show_its_value():
    """A filter for an attribute the table never renders is a dead end.

    The facet rail offers "hard 43 / medium 18" and the predicate filters on
    `declared_difficulty`; the Status cell rendered `t.difficulty` -- the
    MEASURED field, which is "" on all 61 tasks while no official ranking is
    published -- so clicking a chip returned rows that looked identical to the
    ones it excluded.
    """
    cols = _registry_columns()
    by_key = dict(cols)
    assert by_key.get("declared") == "Difficulty", cols
    assert "Official Solves" in by_key.values()

    # sortable headers are driven by COLS; a key sortVal cannot read is inert
    assert 'if (k === "declared") return String(t.declared_difficulty || "");'         in REGISTRY
    # the cell is rendered from the EDITORIAL field ...
    assert "esc(t.declared_difficulty)" in REGISTRY
    # ... and the dead measured badge that used to sit in the Status cell is
    # gone, so one row can never show two difficulty slots
    assert "esc(t.difficulty)" not in REGISTRY

    # header, body row and the static loading row must agree on the width
    body_cells = REGISTRY.count(
        "'<td data-slot=\"table-cell\" class=\"' + TD")
    assert body_cells == len(cols), (body_cells, len(cols))
    spans = re.findall(r'<td data-slot="table-cell" colspan="(\d+)"', REGISTRY)
    assert spans and all(int(x) == len(cols) for x in spans), spans


def test_guide_prose_can_break_the_identifiers_that_overflow_a_phone():
    """/guide/task-format/ was the one page wider than a 390px viewport.

    `terminal_daily_bench/adapters/base.py::HarnessAdapter` in body copy is one
    unbreakable token 440px wide in a 358px content box, and because
    `body { overflow-x: hidden }` propagates to the viewport the page got no
    scrollbar -- the tail was simply cut off. The article opts its prose into
    breaking anywhere; the code blocks are unaffected because `white-space:
    pre` suppresses wrapping outright.
    """
    article = re.search(r'<article class="([^"]*prose[^"]*)"', TASK_FORMAT)
    assert article, "task-format no longer wraps its body in an article.prose"
    classes = article.group(1).split()
    assert "wrap-anywhere" in classes, classes
    # and the class must still BE something: a utility deleted from the
    # stylesheet leaves the markup looking fixed and the page still clipped
    assert ".wrap-anywhere{overflow-wrap:anywhere}" in TW_CSS


_JS_WORDS = {
    "typeof", "null", "true", "false", "undefined", "function", "return", "var",
    "if", "else", "new", "this", "void", "in", "of", "instanceof", "NaN",
}


def _strip_comments(src):
    """Drop // and /* */ comments before any quote-matching happens.

    Not cosmetic. An apostrophe in a comment -- "the model's score" -- opens a
    string as far as a naive scanner is concerned, and everything after it is
    mis-paired. That is how a bare `A` from the middle of a sentence turned up
    as an undeclared constant: the scanner had lost track of where strings were.
    """
    out, i, n, in_str = [], 0, len(src), ""
    while i < n:
        c = src[i]
        if in_str:
            out.append(c)
            if c == "\\":
                if i + 1 < n:
                    out.append(src[i + 1])
                i += 2
                continue
            if c == in_str:
                in_str = ""
            i += 1
        elif c in "\"'":
            in_str = c
            out.append(c)
            i += 1
        elif c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            i = n if j < 0 else j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _concat_chunks(js):
    """Group lines into whole assignment/concatenation expressions.

    A line ending in `+` or `=` continues into the next, so the pieces of one
    `x.innerHTML = "<td>" + esc(v) + "</td>"` are rejoined before anything is
    judged. Both halves of that matter: without `+`, the line holding only
    `(r.effort ? esc(r.effort) : "default") +` carries no '<' of its own and is
    invisible to a markup filter; without `=`, a value is severed from the
    `.textContent =` that makes it harmless, and a shell command template
    containing `-a <agent>` gets scanned as if it were markup.

    Two other splits were tried and both silently examined NOTHING: splitting
    on `;` cuts inside HTML entities (`&middot;`, `&mdash;`), and splitting on
    `;` at paren depth 0 never fires at all, because the whole script sits
    inside an IIFE and is therefore never at depth 0.
    """
    chunks, buf = [], []
    for line in js.splitlines():
        stripped = line.rstrip()
        buf.append(line.strip())
        if not stripped.endswith(("+", "=")):
            chunks.append(" ".join(buf))
            buf = []
    if buf:
        chunks.append(" ".join(buf))
    return chunks

def _strip_strings(src):
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _strip_safe_calls(src, safe_names):
    """Remove `esc(...)`, `T.pct(...)` and friends, arguments included.

    What a safe formatter consumed is safe by definition; what is LEFT is raw
    material. Removing the calls rather than pattern-matching them is what lets
    `(r.effort ? esc(r.effort) : "x")` be judged on the `r.effort` that is NOT
    wrapped -- the earlier version, which only looked at the token after a `+`,
    never saw inside the parentheses at all.
    """
    import re
    call = re.compile(r"(?:[A-Za-z_$][\w$]*\.)?(?:" + "|".join(safe_names) + r")\s*\(")
    while True:
        m = call.search(src)
        if not m:
            return src
        i, depth = m.end() - 1, 0
        while i < len(src):
            if src[i] == "(":
                depth += 1
            elif src[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        src = src[:m.start()] + " " + src[i + 1:]


def test_output_values_are_escaped_before_entering_the_dom():
    """No data-derived value reaches innerHTML unescaped.

    This replaces a version that named five call sites in one renderer. Naming
    call sites only proves the sites that existed when it was written were
    escaped; it says nothing about the next column somebody adds, and when the
    renderer changes it fails for the wrong reason -- "renamed", not "unsafe".

    So scan instead. Two filters keep it honest rather than noisy, because a
    check that flags safe code gets switched off and then protects nothing:

      * only expressions that BUILD MARKUP are scanned -- one with no '<' in
        any string literal is assembling a search key or a URL, not a DOM sink;
      * assignments to textContent/value/placeholder are skipped -- those
        cannot inject however the value was produced.

    Each surviving expression has its safe-formatter calls and then its string
    literals removed. Any property access left standing reached markup raw.
    """
    import re

    js = _strip_comments(LEADERBOARD[LEADERBOARD.index("<script>"):])
    literal = re.compile(r"""(?:"[^"\n]*"|'[^'\n]*')""")
    text_sink = re.compile(r"\.(?:textContent|value|placeholder)\s*=")
    ident = re.compile(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*")
    SAFE = ("esc", "shown", "ratio", "pct", "wilson", "accuracyCell",
            "officialBadge", "String", "Number", "encodeURIComponent", "toFixed")

    scanned, covers_row, offenders = 0, False, []
    for chunk in _concat_chunks(js):
        if text_sink.search(chunk):
            continue
        if not any("<" in lit for lit in literal.findall(chunk)):
            continue
        scanned += 1
        covers_row = covers_row or "<td" in chunk
        bare = _strip_strings(_strip_safe_calls(chunk, SAFE))
        for name in ident.findall(bare):
            head, tail = name.split(".")[0], name.rsplit(".", 1)[-1]
            if head in _JS_WORDS or name in _JS_WORDS:
                continue
            if tail == "length" or name.isdigit():
                continue
            if re.search(r"(?:Cell|Html)$", name):     # prebuilt escaped fragment
                continue
            if re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
                # SCREAMING_CASE is this file's convention for a compile-time
                # constant -- but the name is not taken on faith. Follow it to a
                # string-literal declaration here, or through a "var TD = T.TD"
                # re-export to one in the shared runtime. A data value wearing a
                # constant's name has no such declaration and is reported.
                here = re.search(r"var\s+" + name + r"""\s*=\s*["']""", js)
                alias = re.search(r"\b" + name + r"\s*=\s*T\.(\w+)", js)
                origin = alias and re.search(
                    r"var\s+" + alias.group(1) + r"""\s*=\s*["']""", DATA_RUNTIME)
                if not (here or origin):
                    offenders.append(name + " (undeclared pseudo-constant)")
                continue
            if "." not in name:        # a bare local flag or counter
                continue
            offenders.append(name)

    # A scan that examined nothing prints the same green as a scan that passed,
    # so it has to prove it reached the code that actually renders a row.
    assert scanned >= 6, f"only {scanned} markup expressions found -- the scan did not run"
    assert covers_row, "the scan never reached an expression building a <td> -- coverage lost"
    assert not offenders, (
        "values reaching markup without esc()/a numeric formatter: "
        + ", ".join(sorted(set(offenders)))
    )

    # And the escaper must actually escape, not merely exist. Every character
    # that can close an attribute or open a tag needs a mapping; a partial
    # escaper is precisely what this scan would otherwise wave through.
    body = DATA_RUNTIME[DATA_RUNTIME.index("function esc("):][:400]
    assert """/[&<>"']/g""" in body, "esc() does not match the full dangerous set"
    for ch, ent in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"),
                    ('"', "&quot;"), ("'", "&#39;")):
        assert ent in body, f"esc() has no mapping for {ch!r}"

def test_stat_values_are_not_document_headings():
    # The stat grid left the home page with the rest of the explanatory
    # blocks, so the marker is required of the SITE rather than of index.html.
    # The ban on rendering a stat value as a heading is unconditional and is
    # applied to every published page, which is stronger than the two pages it
    # used to name.
    assert "<p data-tdb-stat-value" in PUBLISHED, (
        "no published page renders a stat value any more")
    assert "<p data-tdb-stat-value" in PAGE_GENERATOR
    assert '<h2 class="mt-2 line-clamp-1 font-mono text-xl' not in PUBLISHED
    assert (
        '<h2 class="line-clamp-1 font-mono text-xl font-medium tabular-nums"'
        not in PAGE_GENERATOR
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
    assert 'Math.ceil(head.getBoundingClientRect().bottom) + "px"' in SHELL
    assert 'pageMain.style.setProperty(' in SHELL
    assert 'pageMain.style.removeProperty("padding-top")' in SHELL
    assert 'ev.key === "Escape"' in SHELL


def test_shell_mounts_a_real_footer_landmark():
    assert 'document.createElement("footer")' in SHELL
    assert 'footer.id = "tdb-footer"' in SHELL
    assert 'footer.setAttribute("aria-label", "Site footer")' in SHELL
    assert "document.body.appendChild(footer)" in SHELL


def test_homepage_integrity_facts_match_current_operator_evidence():
    # These facts used to be asserted against index.html. The detail moved to
    # the page the nav labels "status" when home was rebuilt to lead with the
    # table; home keeps only the compact point-of-claim marker. Each fact is
    # therefore required somewhere on the site -- a move is fine, a deletion is
    # not -- while the stale claim stays banned everywhere.
    for fact in (
        "data-tdb-integrity-details",
        "integrity limits and current blockers",
        "Protected tests decide published scores",
        "paired staged-SIF egress canary passed",
        "no production protected replay has run",
        "active=false",
        "code-controlled allowlist",
        "self-signed report/matrix pins cannot approve themselves",
        "one collaborator",
        "unpublished patched Harbor fork",
        "stock Harbor 0.13.1 is insufficient",
    ):
        assert fact in PUBLISHED, (
            f"operator-evidence fact published on no page under docs/: {fact!r}")
    assert "deployment egress canary is still pending" not in PUBLISHED

    # The disclosure must still sit beside the claim it qualifies, not only on
    # a page a reader has to go looking for.
    assert "data-tdb-integrity" in HOME


def test_homepage_previews_stay_short_and_link_to_full_views():
    # The task preview was removed from home: the registry has its own page,
    # and previewing it pushed the only measured numbers below the fold. The
    # board preview stays, so the rule is written to bind whatever previews
    # home actually renders -- every declared *_PREVIEW_LIMIT must be used to
    # slice, so a limit cannot be declared and quietly ignored.
    assert "var BOARD_PREVIEW_LIMIT = 5;" in HOME
    assert "rows.slice(0, BOARD_PREVIEW_LIMIT)" in HOME
    limits = re.findall(r"var (\w*PREVIEW_LIMIT) = \d+;", HOME)
    assert "BOARD_PREVIEW_LIMIT" in limits
    for name in limits:
        assert f".slice(0, {name})" in HOME, (
            f"home declares {name} but never slices by it")

    # A preview is only honest if the full view is one click away.
    assert 'href="./leaderboard/">full leaderboard' in HOME
    assert 'href="./registry/"' in HOME, "home lost its way into the task registry"


def test_terminal_daily_has_an_independent_visual_identity():
    """Own palette, own type, own brand, own controls -- and not a clone.

    This used to also require a conic-gradient blob behind the home masthead
    and a card rail of published suites. Those were one design's answer to the
    constraint, not the constraint; when the home page became a dense status
    table they failed a design nobody had objected to, while the rules they
    named sat in the stylesheet applying to nothing. Every marker below is a
    selector or token the site actually ships, so deleting a rule as dead code
    fails here instead of being kept alive to satisfy a checker.
    """
    for marker in (
        "--td-paper",
        "--td-night",
        "--td-coral",
        # a DECLARATION, not a reference: "--td-font-display" survives only as
        # an alias now, and every "var(--td-font-display)" still spells it, so
        # the old marker would pass on a stylesheet that declares no family.
        "--td-font:",
        "--ts-body",
        "--sp-7",
        ".tdb-brand-mark",
        ".tdb-daynav",
        ".tdb-statrow",
        '[data-slot="card"]',
        "[data-tdb-stat-value]",
        '[data-slot="table-container"]',
        "@media (prefers-reduced-motion: reduce)",
    ):
        assert marker in SITE_CSS

    for retired in (
        "square, hairline, mono, no shadow",
        "copied verbatim from the reference",
        "byte-equality with the reference",
    ):
        assert retired not in SITE_CSS.lower()
        assert retired not in PAGE_GENERATOR.lower()

    # site.css:390-397 re-pointed Tailwind's .font-mono back to the body face
    # at specificity (0,1,1), silently reverting ~262 elements to sans while
    # span/a/h1/h2/pre/figure stayed mono. It is the reason the site looked
    # like three fonts. It must not come back.
    assert "p.font-mono," not in SITE_CSS

    # Exactly one font-family may be APPLIED to elements. @font-face blocks
    # declare the vendored face rather than applying it, so they are stripped
    # before counting -- but each one must name the same family, or the site
    # would ship two faces under one alias.
    faces = re.findall(r"@font-face\s*\{(.*?)\}", SITE_CSS, re.S)
    assert faces, "the vendored face is gone; the type scale needs its weight axis"
    face_names = {re.search(r'font-family:\s*([^;]+);', f).group(1).strip()
                  for f in faces}
    assert face_names == {'"Google Sans Code"'}, face_names
    for f in faces:
        # a variable axis is the whole point: static weights would resynthesise
        assert re.search(r"font-weight:\s*300\s+800\s*;", f), f
        assert "url(" in f and "//" not in f.split("url(", 1)[1][:40], (
            "the face must stay self-hosted; a remote URL breaks offline render"
        )

    applied = SITE_CSS
    for f in faces:
        applied = applied.replace(f, "")
    assert applied.count("font-family") == 1, (
        "site.css must apply exactly one font-family; every other face is an "
        "alias of it, so a second declaration is a second family"
    )

    assert "Terminal Daily" in SHELL
    assert "tdb-brand-mark" in SHELL
    assert "tdb-page-" in SHELL
    assert "<span>Terminal</span> <span>Daily</span>" in HOME
