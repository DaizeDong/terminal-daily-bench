"""Dependency-free structural fixtures for the static v3 capability frontend."""
from __future__ import annotations

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
PAGE_GENERATOR = (ROOT / "web" / "gen_pages.py").read_text(encoding="utf-8")
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
    assert "canonical C1&ndash;C14" in METHODS
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
    assert "<p data-tdb-stat-value" in HOME
    assert "<p data-tdb-stat-value" in PAGE_GENERATOR
    assert '<h2 class="mt-2 line-clamp-1 font-mono text-xl' not in HOME
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
    assert "data-tdb-integrity-details" in HOME
    assert "integrity limits and current blockers" in HOME
    assert "Protected tests decide published scores" in HOME
    assert "paired staged-SIF egress canary passed" in HOME
    assert "no production protected replay has run" in HOME
    assert "active=false" in HOME
    assert "code-controlled allowlist" in HOME
    assert "self-signed report/matrix pins cannot approve themselves" in HOME
    assert "one collaborator" in HOME
    assert "deployment egress canary is still pending" not in HOME
    assert "unpublished patched Harbor fork" in HOME
    assert "stock Harbor 0.13.1 is insufficient" in HOME


def test_homepage_previews_stay_short_and_link_to_full_views():
    assert "var BOARD_PREVIEW_LIMIT = 5;" in HOME
    assert "rows.slice(0, BOARD_PREVIEW_LIMIT)" in HOME
    assert "var TASK_PREVIEW_LIMIT = 3;" in HOME
    assert "scoped.slice(0, TASK_PREVIEW_LIMIT)" in HOME
    assert 'href="./leaderboard/">full leaderboard' in HOME
    assert 'href="./registry/">all tasks' in HOME


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
        "--td-font-display",
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

    assert "Terminal Daily" in SHELL
    assert "tdb-brand-mark" in SHELL
    assert "tdb-page-" in SHELL
    assert "<span>Terminal</span> <span>Daily</span>" in HOME
