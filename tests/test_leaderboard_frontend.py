"""Dependency-free structural fixtures for the static v3 capability frontend."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import verify_site  # noqa: E402

HOME = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
LEADERBOARD = (ROOT / "docs" / "leaderboard" / "index.html").read_text(
    encoding="utf-8"
)
REGISTRY = (ROOT / "docs" / "registry" / "index.html").read_text(
    encoding="utf-8"
)
SHELL = (ROOT / "docs" / "assets" / "site.js").read_text(encoding="utf-8")
SITE_CSS = (ROOT / "docs" / "assets" / "site.css").read_text(encoding="utf-8")
# Reader-facing method claims may move between linked guide pages.
METHODS = chr(10).join(
    page.read_text(encoding="utf-8")
    for page in sorted((ROOT / "docs" / "guide" / "quality-methods").rglob("index.html"))
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


def test_relative_axes_are_authority_bounded_and_categories_remain_explained():
    assert (
        "var ALLOWED_DIMENSIONS = { overall: true, language: true, capability: true };"
        in LEADERBOARD
    )
    assert "!ALLOWED_DIMENSIONS[axis.dimension]" in LEADERBOARD
    text = verify_site.reader_text(METHODS).lower()
    assert re.search(r"task.family rankings.{0,90}unavailable", text)
    assert re.search(r"labels.{0,80}(?:inferred|code changes|repair)", text)
    assert re.search(r"declared.{0,90}(?:not|cannot).{0,90}(?:checked|derived)", text)
    assert re.search(r"formal.{0,40}ranking.{0,140}(?:requires|evidence)", text)
    codes = re.findall(r'<th\b[^>]*>\s*(C\d+)\s*</th>', METHODS)
    assert set(codes) == {f"C{number}" for number in range(1, 15)}
    assert 'id="capability-taxonomy"' in METHODS
    assert any(tag == "a" and "labels/" in attrs.get("href", "")
               for tag, attrs in verify_site._ReaderMarkup(METHODS).nodes)


def test_missing_outcomes_and_result_sources_remain_distinct():
    assert verify_site.check_reader_claims(
        METHODS, ["missing_not_failure", "separate_result_sources"]
    ) == []
    assert "worth zero" not in PAGE_GENERATOR.lower()
    assert "attempt worth zero" not in PAGE_GENERATOR.lower()


def test_registry_never_reconstructs_tasks_or_scores_from_legacy_matrix():
    assert 'T.getJSON("leaderboard_data.json")' not in REGISTRY
    assert "board.matrix" not in REGISTRY
    # Arithmetic, including unknown versus zero, is exercised by the catalogue
    # behavior cases below; labels may change without changing score eligibility.
    assert "function isScored(" in REGISTRY
    assert "isScored(t)" in REGISTRY


def _nav_table():
    """The NAV literal out of site.js, parsed rather than string-matched.

    Every entry is `["label", "href/", ["page-key", ...]]` with double-quoted
    strings, so the literal is already JSON once the newlines are gone.
    """
    assert "var NAV = [" in SHELL, "site.js no longer declares a NAV array"
    body = SHELL.split("var NAV = ", 1)[1].split("\n  ];", 1)[0]
    return json.loads(body + "\n  ]")


def test_the_quality_report_is_reachable_without_typing_the_url():
    """Readers can reach the quality evidence from results and guide pages."""
    nav = _nav_table()

    # the pinned five, in the pinned order, with quality NOT among them
    # Ordered by HREF. The display labels are prose and were capitalised for a
    # formal masthead; the hrefs are what the rows point at and cannot be
    # restyled, so they are what an order assertion should be made of. Keeping
    # the label form here would have made every future copy edit a test
    # failure, which is how a gate stops being read.
    assert [row[1] for row in nav] == [
        "leaderboard/", "registry/", "benchmarks/", "guide/", "submit/"
    ]

    # every key belongs to exactly one row, or two header items light at once
    keys = [k for row in nav for k in row[2]]
    assert len(keys) == len(set(keys)), "a page key lights up two nav items"

    # landing on the report lights `docs`, which is the row that owns the key
    owners = [row[1] for row in nav if "quality" in row[2]]
    assert owners == ["guide/"], owners

    quality_page = (ROOT / "docs" / "quality" / "index.html").read_text(
        encoding="utf-8")
    assert 'data-page="quality"' in quality_page
    assert 'id="discrimination"' in quality_page

    # Both a direct section link and a link to the report itself are useful
    # entrances. Literal anchors also cover links rendered by page JavaScript;
    # the browser audit verifies that those links appear at runtime.
    quality_target = (ROOT / "docs/quality").resolve()
    quality_ids = {attrs["id"] for _, attrs in verify_site._ReaderMarkup(quality_page).nodes
                   if attrs.get("id")}
    linking = []
    for page in PUBLISHED_PAGES:
        if page.parent.resolve() == quality_target:
            continue
        raw = page.read_text(encoding="utf-8", errors="replace")
        for href in re.findall(r'''href=["']([^"']+)["']''', raw):
            target = urlsplit(href)
            if target.scheme or target.netloc:
                continue
            if (page.parent / target.path).resolve() == quality_target:
                assert not target.fragment or target.fragment in quality_ids
                linking.append(page)
                break
    assert len(linking) >= 2, (
        "the discrimination report is reachable from "
        f"{len(linking)} page(s); it was an orphan once already")
    assert (ROOT / "docs" / "leaderboard" / "index.html") in linking, (
        "the leaderboard lost its link to the discrimination report")


def test_guide_content_uses_the_shared_responsive_document_layout():
    nodes = verify_site._ReaderMarkup(TASK_FORMAT).nodes
    assert any(tag == "article" and "tdb-doc" in attrs.get("class", "").split()
               for tag, attrs in nodes)
    assert any(tag == "main" and "tdb-docs" in attrs.get("class", "").split()
               for tag, attrs in nodes)
    # Long examples still need a bounded document and a scrollable code surface.
    compact = re.sub(r"\s+", "", SITE_CSS)
    assert ".tdb-doc>*{max-width:100%;}" in compact
    assert re.search(r"\.tdb-code[^{}]*pre[^{}]*\{[^{}]*overflow(?:-x)?:\s*auto", SITE_CSS)


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


def _strip_guard_condition(src):
    """A leading if condition controls output but is not part of that output.

    Strings and safe calls have already been removed. Keep the entire body so
    a raw property in guarded markup is checked exactly as an unguarded one.
    """
    guard = re.match(r"\s*if\s*\(", src)
    if not guard:
        return src
    depth = 1
    for i in range(guard.end(), len(src)):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                return src[i + 1:]
    return src


def test_markup_scan_excludes_guards_but_keeps_guarded_output_values():
    body = _strip_guard_condition("if (row.enabled && check(row.n)) { html += row.model; }")
    assert "row.enabled" not in body and "row.n" not in body
    assert "row.model" in body
    assert _strip_guard_condition("html += row.model;") == "html += row.model;"


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
        bare = _strip_guard_condition(_strip_strings(_strip_safe_calls(chunk, SAFE)))
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

def test_generated_pages_have_one_title_and_do_not_use_headings_for_metrics():
    generated = sorted((ROOT / "docs" / "benchmarks").glob("*/index.html"))
    generated += sorted((ROOT / "docs" / "registry").glob("*/index.html"))
    assert generated
    for page in generated:
        nodes = verify_site._ReaderMarkup(page.read_text(encoding="utf-8")).nodes
        assert sum(tag == "h1" for tag, _ in nodes) == 1, page
        for tag, attrs in nodes:
            if re.fullmatch(r"h[1-6]", tag):
                assert "data-tdb-stat-value" not in attrs, page
                assert "tabular-nums" not in attrs.get("class", "").split(), page


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


def test_public_guides_explain_limitations_without_internal_contract_dumps():
    quickstart = (ROOT / "docs/guide/quickstart/index.html").read_text(encoding="utf-8")
    submit = (ROOT / "docs/submit/index.html").read_text(encoding="utf-8")
    assert verify_site.check_reader_claims(quickstart, ["evaluation_unavailable"]) == []
    assert verify_site.check_reader_claims(submit, ["pending_excluded", "full_task_set"]) == []
    for page in PUBLISHED_PAGES:
        assert verify_site.check_reader_copy(page.read_text(encoding="utf-8"), str(page)) == []
    assert verify_site.check_canary_metadata(SHELL) == []


def test_preliminary_results_have_a_reader_visible_status():
    pages = {"index.html": HOME, "leaderboard/index.html": LEADERBOARD}
    assert verify_site.check_preliminary_marker(pages.__getitem__) == []


@pytest.mark.parametrize("markup", [
    '<span data-official="false">Official</span>',
    '<span>Preliminary</span>',
    '<span data-official="false" hidden>Preliminary</span>',
    '<!-- <span data-official="false">Preliminary</span> -->',
])
def test_preliminary_marker_cannot_be_replaced_by_an_unrelated_word_or_comment(markup):
    assert len(verify_site.check_preliminary_marker(lambda _: markup)) == 2


@pytest.mark.parametrize("markup, finding", [
    ("<p>td-" + "a" * 16 + "</p>", "task identifier"),
    ("<footer>00000000-0000-0000-0000-000000000000</footer>", "UUID"),
    ("<code>" + "b" * 64 + "</code>", "raw digest"),
    ("<p>frozen_task_roster_n: 50</p>", "internal publication field"),
    ("<p>awaiting-certified-50-task-results</p>", "internal publication state"),
    ('<button aria-label="Open td-' + 'c' * 16 + '">Open</button>', "task identifier"),
    ("<p>td&#45;" + "d" * 16 + "</p>", "task identifier"),
    ('<span aria-hidden="true">td-' + 'e' * 16 + '</span>', "task identifier"),
])
def test_reader_copy_rejects_visible_engineering_leaks(markup, finding):
    assert any(finding in error for error in verify_site.check_reader_copy(markup))


def test_reader_copy_keeps_machine_metadata_routes_and_useful_commands():
    task_id = "td-" + "a" * 16
    markup = (
        '<head><meta id="tdb-canary" content="00000000-0000-0000-0000-000000000000"></head>'
        '<main><a href="/registry/' + task_id + '/" data-task-id="' + task_id + '">Repair file handling</a>'
        '<!-- frozen_task_roster_n -->'
        '<script type="application/json">{"frozen_task_roster_n":50}</script>'
        '<pre><code>tdb doctor path/to/task</code></pre></main>'
    )
    assert verify_site.check_reader_copy(markup) == []
    text = verify_site.reader_text(markup)
    assert "Repair file handling" in text and "tdb doctor" in text
    assert task_id not in text and "frozen_task_roster_n" not in text


@pytest.mark.parametrize("claim, positive, negative", [
    ("evaluation_unavailable", "The required scoring environment is not publicly available.",
     "The required scoring environment is publicly available."),
    ("pending_excluded", "Pending submissions do not count toward leaderboard scores.",
     "Pending submissions count toward leaderboard scores."),
    ("full_task_set", "Compare models on the same full task set.",
     "Compare models using any selected tasks."),
    ("missing_not_failure", "Missing outcomes are not counted as model failures.",
     "Missing outcomes are counted as model failures."),
    ("separate_result_sources", "Checked results and contributor claims are recorded separately.",
     "Checked results and contributor claims are combined."),
])
def test_reader_claims_require_the_meaning_in_public_text(claim, positive, negative):
    assert verify_site.check_reader_claims('<p>' + positive + '</p>', [claim]) == []
    assert verify_site.check_reader_claims('<p>' + negative + '</p>', [claim])
    assert verify_site.check_reader_claims('<script>' + json.dumps(positive) + '</script>', [claim])
    assert verify_site.check_reader_claims('<!-- ' + positive + ' -->', [claim])


def test_footer_keeps_the_contamination_marker_in_head_metadata():
    from test_capability_ranking import _extract, _run
    result = _run(
        """var CANARY = INPUT.marker, GITHUB = 'https://example.com/project';
        function url(path) { return './' + path; }
        var head = [], body = [];
        var document = {
          head:{appendChild:function(node){head.push(node);}},
          body:{appendChild:function(node){body.push(node);}},
          getElementById:function(id){return head.concat(body).find(function(node){return node.id===id;});},
          createElement:function(tag){return {tag:tag,attrs:{},setAttribute:function(key,value){this.attrs[key]=value;}};}
        };
        """ + _extract(SHELL, "mountFooter") + """
        mountFooter(); mountFooter();
        console.log(JSON.stringify({head:head,body:body}));
        """, {"marker": "synthetic benchmark contamination marker"})
    assert len(result["head"]) == 1 and len(result["body"]) == 1
    assert result["head"][0]["tag"] == "meta"
    assert result["head"][0]["id"] == "tdb-canary"
    assert result["head"][0]["content"] == "synthetic benchmark contamination marker"
    assert result["body"][0]["tag"] == "footer"
    assert "synthetic benchmark contamination marker" not in verify_site.reader_text(result["body"][0]["innerHTML"])


def test_homepage_preview_is_bounded_and_links_to_full_views():
    # The task preview was removed from home: the registry has its own page,
    # and previewing it pushed the only measured numbers below the fold. The
    # board preview stays, so the rule is written to bind whatever previews
    # home actually renders -- every declared *_PREVIEW_LIMIT must be used to
    # slice, so a limit cannot be declared and quietly ignored.
    # The name of the array being sliced is deliberately NOT pinned. It was
    # `rows.slice(0, BOARD_PREVIEW_LIMIT)` while the preview ranked every
    # flattened cell together; it is now sliced from the mainline partition,
    # because ranking a 293-task effort sweep above a 342-task mainline score
    # is not a ranking. Pinning the variable name asserted an implementation
    # detail that the rule below already covers properly: the loop requires
    # EVERY declared limit to be used in a slice, whatever it slices, so a
    # limit still cannot be declared and quietly ignored.
    limits = dict(re.findall(r"var (\w*PREVIEW_LIMIT) = (\d+);", HOME))
    assert "BOARD_PREVIEW_LIMIT" in limits
    for name, limit in limits.items():
        assert int(limit) > 0, f"home declares an empty preview: {name}={limit}"
        assert f".slice(0, {name})" in HOME, (
            f"home declares {name} but never slices by it")

    # A preview is only honest if the full view is one click away.
    assert 'href="./leaderboard/"' in HOME, "home lost its link to the full leaderboard"
    assert 'href="./registry/"' in HOME, "home lost its way into the task registry"


def test_project_identity_and_local_font_sources_are_preserved():
    """Reference styling may change while project identity and offline assets remain."""
    # The reference-led redesign supersedes exact palette, family-count,
    # type-assignment and selector pins. Retain the local-source requirement
    # without choosing which font family the interface must use.
    faces = re.findall(r"@font-face\s*\{(.*?)\}", SITE_CSS, re.S)
    for face in faces:
        assert "url(" in face and "//" not in face.split("url(", 1)[1][:40], (
            "font sources must stay self-hosted; a remote URL breaks offline render"
        )

    assert "Terminal Daily" in SHELL
    assert "tdb-page-" in SHELL


def _catalogue_fixture():
    import importlib.util

    spec = importlib.util.spec_from_file_location("catalogue_fixtures", ROOT / "tools/make_fixtures.py")
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    return fixtures.catalogue_fixture()


def _catalogue_run(kind, script, payload):
    """Run the page's actual closures; pending fetches keep boot outside the probe."""
    from test_capability_ranking import _extract, _run

    page = REGISTRY if kind == "tasks" else (ROOT / "docs/benchmarks/index.html").read_text(encoding="utf-8")
    inline = re.findall(r"<script>\s*(.*?)</script>", page, re.S)[-1]
    names = re.findall(r"^  function (\w+)\(", inline, re.M)
    end = inline.rfind("})();")
    assert end >= 0 and names, "the catalogue probe did not reach the page closure"
    exports = "window.catalogueProbe = {" + ",".join(name + ":" + name for name in names) + "};\n"
    inline = inline[:end] + exports + inline[end:]
    setup = "\n".join([
        _extract(SHELL, "taskSuites"), _extract(SHELL, "taskInSuite"),
        "T.taskSuites = taskSuites; T.taskInSuite = taskInSuite;",
        "var window = {TDB:T, URL:URL, location:new URL('https://example.com/registry/'), addEventListener:function(){}, history:{replaceState:function(){},pushState:function(){}}};",
        DATA_RUNTIME,
        (ROOT / "docs/assets/tdb-releases.js").read_text(encoding="utf-8"),
        "T = window.TDB; T.getJSON = function(){return new Promise(function(){});}; T.fetchFailed = function(){return function(){return null;};};",
        """function probeElement() {
          return {value:'',innerHTML:'',textContent:'',hidden:false,disabled:false,className:'',
            addEventListener:function(){},setAttribute:function(){},removeAttribute:function(){},
            querySelector:function(){return probeElement();},querySelectorAll:function(){return [];},
            classList:{add:function(){},remove:function(){},toggle:function(){}},
            style:{setProperty:function(){},removeProperty:function(){}}};
        }""",
        "var probeElements = {}; " + json.dumps(re.findall(r'\bid="([^"]+)"', page)) + ".forEach(function(id){probeElements[id]=probeElement();});",
        "var document={getElementById:function(id){return probeElements[id] || null;},querySelector:function(){return probeElement();},querySelectorAll:function(){return [];},addEventListener:function(){}};",
    ])
    return _run(setup + "\n" + inline + "\nvar C = window.catalogueProbe;\n" + script, payload)


def test_large_task_catalogue_filters_and_sorts_before_selecting_a_page():
    data = _catalogue_fixture()
    target = data["site"]["tasks"][-1]
    older_suite = target["suites"][0]
    expected_members = sorted(t["id"] for t in data["site"]["tasks"] if older_suite in t["suites"])
    out = _catalogue_run("tasks", """
      var tasks = C.prepareTasks(INPUT.site, INPUT.cap).reverse();
      var state = C.readTaskState('');
      var last = C.withTaskFilters(state, {q:'Unique terminal fixture', suite:INPUT.older});
      var match = C.selectTaskPage(tasks, last);
      var base = C.withTaskFilters(state, {sort:'task', dir:'asc'});
      var second = C.selectTaskPage(tasks, Object.assign({},base,{page:2}));
      var finalPage = C.selectTaskPage(tasks, Object.assign({},base,{page:1000000}));
      var members = C.filterTasks(tasks, C.withTaskFilters(state,{suite:INPUT.older}));
      console.log(JSON.stringify({match:match, second:second, finalPage:finalPage,
        members:members.map(function(t){return t.id;}).sort(), original:tasks.map(function(t){return t.id;})}));
    """, dict(data, older=older_suite))
    assert [t["id"] for t in out["match"]["items"]] == [target["id"]]
    assert out["members"] == expected_members
    assert [t["id"] for t in out["second"]["items"]] == [f"task-{i:05d}" for i in range(25, 50)]
    assert (out["second"]["start"], out["second"]["end"], out["second"]["total"]) == (26, 50, 2401)
    assert (out["finalPage"]["page"], len(out["finalPage"]["items"])) == (97, 1)
    assert out["original"] == [t["id"] for t in reversed(data["site"]["tasks"])]


def test_task_filters_compose_and_keep_capability_provenance_distinct():
    data = _catalogue_fixture()
    expected = sorted(t["id"] for i, t in enumerate(data["site"]["tasks"])
                      if i % 3 == 0 and t["language"] == "python" and t["declared_difficulty"] == "hard")
    out = _catalogue_run("tasks", """
      var tasks = C.prepareTasks(INPUT.site,INPUT.cap);
      var state=C.withTaskFilters(C.readTaskState(''),{language:'python',declared:'hard',capability:'C1'});
      var matches=C.filterTasks(tasks,state);
      var empty=C.selectTaskPage(tasks,C.withTaskFilters(state,{q:'missing synthetic phrase'}));
      var unread=C.prepareTasks(INPUT.site,null);
      var unindexed=C.prepareTasks(INPUT.site,INPUT.unindexed_cap);
      console.log(JSON.stringify({ids:matches.map(function(t){return t.id;}).sort(),empty:empty,
        states:tasks.slice(0,3).map(function(t){return {state:t._capState,codes:t._caps};}),
        unread:unread[0]._capState,
        unindexed:unindexed.every(function(t){return t._capState==='unverified' && t._caps.length===0;}),
        unindexedRow:C.taskRow(unindexed[0],state,false,{})}));
    """, data)
    assert expected and out["ids"] == expected
    assert (out["empty"]["total"], out["empty"]["start"], out["empty"]["end"], out["empty"]["pages"]) == (0, 0, 0, 1)
    assert out["states"][0] == {"state": "rederived", "codes": ["C1", "C3"]}
    assert out["states"][1] == {"state": "declared", "codes": ["C2"]}
    assert out["states"][2] == {"state": "unverified", "codes": []}
    assert out["unread"] == "unread"
    # A catalogue can be newer than its capability index. Missing records do
    # not establish that the task was audited and matched no taxonomy axis.
    assert out["unindexed"]
    assert re.search(r"\b(?:unverified|not (?:checked|reviewed|verified)|awaiting review)\b",
                     verify_site.reader_text(out["unindexedRow"]), re.I)
    assert "No axis" not in out["unindexedRow"]
    assert "No taxonomy axis matched" not in out["unindexedRow"]


def test_task_view_state_round_trips_without_losing_external_url_context():
    out = _catalogue_run("tasks", """
      var state=C.readTaskState('?q=repair%20%26%20test&suite=2020-01-02&status=archive&repo=example%2Fproject-03&language=python&declared=hard&difficulty=medium&capability=C1&sort=task&dir=asc&page=2&size=50');
      var url=new URL(C.taskStateUrl('https://example.com/registry/?campaign=synthetic#rows',state));
      var back=C.readTaskState(url.search);
      var changed=C.withTaskFilters(state,{language:'go'});
      var clean=new URL(C.taskStateUrl(url.href,C.readTaskState('')));
      var invalid=C.readTaskState('?page=-12&size=17&sort=unknown&dir=sideways');
      console.log(JSON.stringify({state:state,back:back,changed:changed,url:url.href,clean:clean.href,invalid:invalid}));
    """, {})
    assert out["back"] == out["state"]
    assert out["state"] == {
        "q": "repair & test", "suite": "2020-01-02", "status": "archive",
        "repo": "example/project-03", "language": "python", "declared": "hard",
        "difficulty": "medium", "capability": "C1", "sort": "task", "dir": "asc",
        "scope": "", "page": 2, "size": 50,
    }
    assert out["state"]["page"] == 2 and out["state"]["size"] == 50
    assert out["changed"]["page"] == 1 and out["changed"]["language"] == "go"
    assert out["state"]["language"] == "python"
    assert "campaign=synthetic" in out["url"] and out["url"].endswith("#rows")
    assert "scope=" not in out["url"], "the default change filter is omitted from public links"
    assert out["clean"] == "https://example.com/registry/?campaign=synthetic#rows"
    assert out["invalid"]["page"] == 1 and out["invalid"]["size"] in (25, 50, 100)
    assert out["invalid"]["sort"] == "suite" and out["invalid"]["dir"] in ("asc", "desc")


def test_task_rows_keep_editorial_difficulty_and_optional_official_scores():
    data = _catalogue_fixture()
    out = _catalogue_run("tasks", """
      var tasks=C.prepareTasks(INPUT.site,INPUT.cap), state=C.readTaskState('');
      var spec={}; INPUT.cap.axes.forEach(function(a){spec[a.code]=a;});
      var zero=tasks[0], unknown=tasks[2], hostile=tasks[tasks.length-1];
      var editorial=tasks.filter(function(t){return t.declared_difficulty==='hard';})[0];
      console.log(JSON.stringify({valid:INPUT.score_cases.map(C.isScored),
        base:C.taskRow(editorial,state,false,spec),measured:C.taskRow(zero,state,true,spec),
        unknown:C.taskRow(unknown,state,true,spec),hostile:C.taskRow(hostile,state,false,spec)}));
    """, data)
    assert out["valid"] == [False, True, True, False, False, False, False, False, False]
    assert len(re.findall(r"<td\b", out["base"])) == 5
    assert len(re.findall(r"<td\b", out["measured"])) == 6
    assert "hard" in out["base"]
    assert "0/10" in out["measured"]
    assert "0/" not in out["unknown"] and "&mdash;" in out["unknown"]
    assert "<task>" not in out["hostile"] and "&lt;task&gt;" in out["hostile"]


def test_task_facet_counts_allow_changing_one_active_filter():
    from collections import Counter

    data = _catalogue_fixture()
    tasks = data["site"]["tasks"]
    c1 = set(data["cap"]["axes"][0]["task_ids"])
    expected_languages = Counter(t["language"] for t in tasks
                                 if t["title"].startswith("Synthetic") and t["language"]
                                 and t["declared_difficulty"] == "hard" and t["id"] in c1)
    expected_declared = Counter(t["declared_difficulty"] for t in tasks
                               if t["title"].startswith("Synthetic") and t["declared_difficulty"]
                               and t["language"] == "python" and t["id"] in c1)
    out = _catalogue_run("tasks", """
      var tasks=C.prepareTasks(INPUT.site,INPUT.cap);
      var state=C.withTaskFilters(C.readTaskState(''),{q:'Synthetic',language:'python',declared:'hard',capability:'C1'});
      var counts=C.facetCounts(tasks,state);
      var impossible=C.facetCounts(tasks,C.withTaskFilters(state,{q:'missing synthetic phrase'}));
      console.log(JSON.stringify({language:Object.fromEntries(counts.language),
        declared:Object.fromEntries(counts.declared), emptyLanguage:Array.from(impossible.language)}));
    """, data)
    assert out["language"] == dict(expected_languages)
    assert len(out["language"]) > 1, "other languages remain reachable with the remaining filters"
    assert out["declared"] == dict(expected_declared)
    assert len(out["declared"]) > 1, "other editorial difficulties remain reachable"
    assert out["emptyLanguage"] == []


def test_shared_page_slicing_is_bounded_and_does_not_reorder_inputs():
    data = _catalogue_fixture()
    out = _catalogue_run("suites", """
      var ids=INPUT.site.tasks.map(function(t){return t.id;});
      var original=ids.slice();
      var oversized=T.pageSlice(ids,1,10000), negative=T.pageSlice(ids,-9,25);
      var empty=T.pageSlice([],999,25), notANumber=T.pageSlice(ids,NaN,25);
      console.log(JSON.stringify({oversized:oversized,negative:negative,empty:empty,notANumber:notANumber,unchanged:JSON.stringify(ids)===JSON.stringify(original)}));
    """, data)
    assert len(out["oversized"]["items"]) <= 100
    assert len(out["negative"]["items"]) == 25 and out["negative"]["page"] == 1
    assert out["notANumber"]["page"] == 1
    assert (out["empty"]["start"], out["empty"]["end"], out["empty"]["page"], out["empty"]["pages"]) == (0, 0, 1, 1)
    assert out["unchanged"]


def test_suite_catalogue_infers_all_memberships_and_filters_before_paging():
    data = _catalogue_fixture()
    suites = data["site"]["suites"]
    unsafe_language = '<img src=x onerror="alert(1)"> & synthetic'
    next(suite for suite in suites if suite["id"] == "sample")["languages"] = [unsafe_language]
    expected = sorted((s["id"] for s in suites if s["id"].startswith("2020-02") and s["status"] == "archive"), reverse=True)
    out = _catalogue_run("suites", """
      var original=JSON.stringify(INPUT.site);
      var suites=C.catalogueSuites(INPUT.site);
      var matches=C.filterSuites(suites,{q:'synthetic',status:'archive',period:'2020-02'});
      var page=T.pageSlice(matches,2,20);
      var samples=C.filterSuites(suites,{q:'',status:'archive',period:'undated'});
      console.log(JSON.stringify({ids:matches.map(function(s){return s.id;}),page:page,
        samples:samples.map(function(s){return s.id;}),html:C.suiteRows(samples,INPUT.site.tasks),
        languages:suites.filter(function(s){return s.id==='2020-01-01'||s.id==='2020-01-02';}),
        unchanged:JSON.stringify(INPUT.site)===original}));
    """, data)
    assert out["ids"] == expected and len(expected) == 29
    assert [s["id"] for s in out["page"]["items"]] == expected[20:]
    assert out["page"]["total"] == 29 and out["page"]["start"] == 21
    assert out["samples"] == ["sample-zero", "sample"]
    assert out["unchanged"]
    languages = {s["id"]: s["languages"] for s in out["languages"]}
    assert languages["2020-01-01"] == ["published-language"]
    expected_languages = {t["language"] for t in data["site"]["tasks"] if "2020-01-02" in t["suites"] and t["language"]}
    assert set(languages["2020-01-02"]) == expected_languages
    assert "&mdash;" in out["html"] and ">0</td>" in out["html"]
    assert unsafe_language not in out["html"]
    assert '&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; synthetic' in out["html"]
    assert not any(tag == "img" for tag, _ in verify_site._ReaderMarkup(out["html"]).nodes)
