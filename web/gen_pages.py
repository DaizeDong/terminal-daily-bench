#!/usr/bin/env python3
"""gen_pages.py -- static page generator for the terminal-daily-bench site.

Reads
    release/registry.json                 (suite catalogue shipped with the bundle)
    release/docs/site_data.json           (published catalogue: suites[] + tasks[])
    release/docs/leaderboard_data.json    (optional: today's scored matrix)
    release/tasks/{archive,live}/<id>/    (optional: local task packages, for detail)

Writes
    release/docs/benchmarks/<suite-id>/index.html    one page per daily suite
    release/docs/registry/<task-id>/index.html       one page per task

Both live two directories below the site root, so every generated page loads the
same three stylesheets, in this order, and ends with the same script tag:

    ../../assets/tw.css        the vendored Tailwind build (all utilities)
    ../../assets/tw-extra.css  its second chunk
    ../../assets/site.css      our thin additive layer
    ../../assets/site.js       data-root="../.." data-page="<key>"

NOTHING here hand-rolls CSS. Every class string below is copied verbatim from the
reference DOM and is already compiled into tw.css; if a look cannot be expressed
with those utilities the DOM structure is wrong, not the stylesheet.

No third-party dependencies. Idempotent: a page is only rewritten when its bytes
change, and every action is printed (write / update / unchanged).

--------------------------------------------------------------------------------
SHARED PAGE TEMPLATE API  (the 'registry' generator imports these -- do not
rename without updating that caller):

    render_page(title, description, page_key, depth, body, script="", head="")
        -> full HTML document string. `depth` is how many directories below the
           site root the page sits (2 for benchmarks/<id>/ and registry/<id>/);
           it drives both asset hrefs and the data-root attribute.
    write_page(path, html)      idempotent write + a printed line
    esc(s)                      HTML-escape any value
    cls(s)                      escape a class string for an HTML attribute
    pill(text, kind="")         a <span data-slot="badge">   kind: primary|outline|""
    status_pill(status)         live -> primary badge, archive -> secondary badge
    tags(*pills)                a flex row of badges
    strip(pairs)                the stat band, as their card grid
    sec_head(title, eyebrow="", more=None)   their centred section header
    task_page_body(task, pkg)   the shared BODY for one task page
    load_task_package(task_id)  best-effort dict from tasks/{archive,live}/<id>/
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RELEASE = HERE.parent
DOCS = RELEASE / "docs"
TASKS = RELEASE / "tasks"

REPO_URL = "https://github.com/DaizeDong/terminal-daily-bench"


# ============================================================================
# THE REFERENCE CLASS STRINGS
# Copied verbatim from the reference DOM. Do not "tidy" them: byte-equality with
# the reference is the whole point, and every token is compiled into tw.css.
# ============================================================================

CARD = (
    "bg-card text-card-foreground flex flex-col gap-6 border hover:bg-sidebar "
    "dark:hover:bg-accent -mb-px rounded-none border-x-0 py-0 font-mono shadow-none "
    "transition-all duration-200 sm:-mr-px sm:border-x"
)
CARD_HEADER = (
    "@container/card-header grid auto-rows-min grid-rows-[auto_auto] items-start "
    "gap-1.5 px-6 has-data-[slot=card-action]:grid-cols-[1fr_auto] [.border-b]:pb-6"
)

_BADGE_BASE = (
    "inline-flex items-center justify-center border px-2 py-0.5 text-sm sm:text-xs "
    "font-medium w-fit whitespace-nowrap shrink-0 [&>svg]:size-3 gap-1 "
    "[&>svg]:pointer-events-none focus-visible:border-ring focus-visible:ring-ring/50 "
    "focus-visible:ring-[3px] aria-invalid:ring-destructive/20 "
    "dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive "
    "transition-[color,box-shadow] overflow-hidden "
)
BADGE_PRIMARY = _BADGE_BASE + (
    "border-transparent bg-primary text-primary-foreground "
    "[a&]:hover:bg-primary/90 font-mono"
)
BADGE_SECONDARY = _BADGE_BASE + (
    "border-transparent bg-secondary text-secondary-foreground "
    "[a&]:hover:bg-secondary/90 font-mono"
)
BADGE_OUTLINE = _BADGE_BASE + "text-foreground font-mono"

_BTN = (
    "font-mono inline-flex shrink-0 items-center justify-center gap-2 font-medium "
    "whitespace-nowrap transition-all outline-none focus-visible:border-ring "
    "focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none "
    "disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 "
    "dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 "
    "[&_svg:not([class*='size-'])]:size-4 "
)
BTN_PRIMARY = _BTN + "bg-primary text-primary-foreground hover:bg-primary/90 h-12 px-8 text-base has-[>svg]:px-6 rounded-none"
BTN_SECONDARY = _BTN + "bg-secondary text-secondary-foreground hover:bg-secondary/80 h-12 px-8 text-base has-[>svg]:px-6 rounded-none"

TABLE = (
    "w-full caption-bottom text-sm [&_tr>td:first-child]:pl-6 [&_tr>td:last-child]:pr-6 "
    "[&_tr>th:first-child]:pl-6 [&_tr>th:last-child]:pr-6"
)
_CHK = "[&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-[2px]"
TH = ("text-foreground h-10 px-2 text-left align-middle font-medium whitespace-nowrap "
      + _CHK + " py-3 text-base")
TD = "p-2 align-middle whitespace-nowrap " + _CHK + " py-4 text-base"
# their cells are always nowrap; a descriptive column drops that one token, which
# is how Tailwind spells "wrap normally" (there is no whitespace-normal compiled)
TD_PROSE = "p-2 align-middle " + _CHK + " py-4 text-base"
TR_HEAD = "data-[state=selected]:bg-muted border-b transition-colors px-6 hover:bg-transparent"
TR_BODY = "hover:bg-muted/50 data-[state=selected]:bg-muted border-b transition-colors px-6"

LINK = "hover:underline hover:underline-offset-4"
DASH = '<span class="text-muted-foreground">&mdash;</span>'

CHEVRON = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" class="text-muted-foreground size-4" aria-hidden="true">'
    '<path d="m6 9 6 6 6-6"></path></svg>'
)
CARET = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" class="lucide"><path d="m9 18 6-6-6-6"></path></svg>'
)


# ----------------------------------------------------------------- primitives

def esc(value) -> str:
    """HTML-escape any value (None becomes an empty string)."""
    if value is None:
        return ""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def cls(value: str) -> str:
    """Escape a class string for an HTML attribute, the way the reference does:
    `&` -> `&amp;` and `>` -> `&gt;`, so arbitrary variants survive round-tripping."""
    return value.replace("&", "&amp;").replace(">", "&gt;")


def pill(text, kind: str = "") -> str:
    """A badge in their treatment. kind: primary | outline | "" (secondary)."""
    variant = {"primary": BADGE_PRIMARY, "outline": BADGE_OUTLINE}.get(kind, BADGE_SECONDARY)
    return f'<span data-slot="badge" class="{cls(variant)}">{esc(text)}</span>'


def status_pill(status: str) -> str:
    """live = sealed, gold withheld (primary) · archive = released in full (secondary)."""
    return pill(status or "unknown", "primary" if status == "live" else "")


def tags(*items) -> str:
    inner = "".join(i for i in items if i)
    return f'<div class="mb-6 flex flex-wrap gap-2">{inner}</div>' if inner else ""


def stat_card(label, value, note: str = "") -> str:
    """One cell of the stat band, in their card idiom."""
    shown = DASH if value in (None, "") else esc(value)
    body = (
        f'<div data-slot="card" class="{cls(CARD)}">'
        f'<div class="flex flex-1 flex-col justify-between gap-6 py-6">'
        f'<div data-slot="card-header" class="{cls(CARD_HEADER)}">'
        f'<p class="text-muted-foreground font-mono text-sm sm:text-xs">{esc(label)}</p>'
        f'<h2 class="line-clamp-1 font-mono text-xl font-medium tabular-nums">{shown}</h2>'
        f"</div>"
    )
    if note:
        body += (
            f'<div data-slot="card-content" class="px-6">'
            f'<p class="text-muted-foreground line-clamp-2 font-mono text-sm sm:text-xs">'
            f"{esc(note)}</p></div>"
        )
    return body + "</div></div>"


def strip(pairs) -> str:
    """The stat band: their hairline card grid, edge to edge on mobile.

    `pairs` is [(label, value)] or [(label, value, note)].
    """
    cells = "".join(
        stat_card(p[0], p[1], p[2] if len(p) > 2 else "") for p in pairs
    )
    return (
        '<div class="-mx-4 mb-6 flex flex-col sm:mx-0">'
        f'<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3">{cells}</div>'
        "</div>"
    )


def sec_head(title, eyebrow: str = "", more=None) -> str:
    """Their centred section header: eyebrow line, chevron, optional sub-line."""
    out = [
        '<div class="mb-4 flex flex-col items-center gap-2">',
        f'<p class="font-mono text-sm">{esc(title)}</p>',
        CHEVRON,
    ]
    if eyebrow:
        out.append(f'<p class="text-muted-foreground font-mono text-xs">{esc(eyebrow)}</p>')
    if more:
        href, label = more
        out.append(
            '<a class="text-muted-foreground hover:text-foreground font-mono text-xs '
            f'underline-offset-4 hover:underline" href="{esc(href)}">{esc(label)} &rarr;</a>'
        )
    out.append("</div>")
    return "".join(out)


def empty(msg_html: str) -> str:
    """A hairline notice block in the same idiom as the tables."""
    return (
        '<div class="bg-card border-y px-6 py-8 font-mono text-sm '
        f'text-muted-foreground md:border-x">{msg_html}</div>'
    )


def prose_block(html: str) -> str:
    """A block of running text, in the card idiom (their tables never hold prose)."""
    return (
        '<div class="bg-card border-y px-6 py-6 font-mono text-sm/relaxed md:border-x">'
        f"{html}</div>"
    )


def code_figure(caption: str, lines) -> str:
    """Their code-block treatment (figure > caption row > pre.shiki)."""
    body = "".join(f'<span class="line">{l}</span>' for l in lines)
    return (
        '<figure dir="ltr" class="rounded-xl bg-fd-card p-1 shiki relative border '
        'outline-none overflow-hidden text-sm my-0 mb-6 font-mono">'
        '<div class="flex text-fd-muted-foreground items-center gap-2 ps-3 h-9.5">'
        f'<figcaption class="flex-1 truncate">{esc(caption)}</figcaption></div>'
        '<div class="bg-fd-secondary rounded-lg border text-[13px] py-3.5 overflow-auto '
        'max-h-[600px] fd-scroll-container">'
        '<pre class="min-w-full w-max *:flex *:flex-col shiki" tabindex="0"><code>'
        f"{body}</code></pre></div></figure>"
    )


def breadcrumb(trail) -> str:
    """Their breadcrumb: [(label, href_or_None), ...]; the last item is the page."""
    items = []
    for i, (label, href) in enumerate(trail):
        if i:
            items.append(
                '<li data-slot="breadcrumb-separator" role="presentation" aria-hidden="true" '
                f'class="{cls("[&>svg]:size-3.5")}">{CARET}</li>'
            )
        if href:
            items.append(
                '<li data-slot="breadcrumb-item" class="inline-flex items-center gap-1.5">'
                '<a data-slot="breadcrumb-link" class="hover:text-foreground transition-colors" '
                f'href="{esc(href)}">{esc(label)}</a></li>'
            )
        else:
            items.append(
                '<li data-slot="breadcrumb-item" class="inline-flex items-center gap-1.5">'
                '<span data-slot="breadcrumb-page" role="link" aria-disabled="true" '
                f'aria-current="page" class="text-foreground font-normal">{esc(label)}</span>'
                "</li>"
            )
    return (
        '<nav aria-label="breadcrumb" data-slot="breadcrumb" class="mb-6 hidden font-mono sm:block">'
        '<ol data-slot="breadcrumb-list" class="text-muted-foreground flex flex-wrap '
        'items-center gap-1.5 text-sm break-words sm:gap-2.5">'
        + "".join(items)
        + "</ol></nav>"
    )


def button_row(buttons) -> str:
    """Their CTA grid: [(label, href, primary_bool)].

    Only grid-cols variants actually compiled into tw.css are emitted
    (sm:grid-cols-{1,2}, lg:grid-cols-{2,3,4}); a single button gets no lg track.
    """
    n = min(len(buttons), 4)
    track = f" lg:grid-cols-{n}" if n >= 2 else ""
    cells = "".join(
        f'<a class="{cls(BTN_PRIMARY if primary else BTN_SECONDARY)}" href="{esc(href)}">'
        f"{esc(label)}</a>"
        for label, href, primary in buttons
    )
    return (
        f'<div class="mx-auto mb-6 grid grid-cols-1 gap-2 sm:grid-cols-2{track}">'
        f"{cells}</div>"
    )


def table_block(headers, rows) -> str:
    """Their table, wrapped in the bg-card hairline block.

    headers -- [(label, align)] where align is "left" | "right"
    rows    -- list of already-rendered "<td …>…</td>" strings
    """
    ths = []
    for label, align in headers:
        inner = (f'<div class="flex justify-end">{esc(label)}</div>'
                 if align == "right" else esc(label))
        ths.append(f'<th data-slot="table-head" class="{cls(TH)}">{inner}</th>')
    return (
        '<div class="-mx-4 mb-6 flex flex-col md:mx-0">'
        '<div class="bg-card border-y font-mono md:border-x">'
        '<div data-slot="table-container" class="relative w-full overflow-x-auto">'
        f'<table data-slot="table" class="{cls(TABLE)}">'
        f'<thead data-slot="table-header" class="{cls("[&_tr]:border-b")}">'
        f'<tr data-slot="table-row" class="{cls(TR_HEAD)}">' + "".join(ths) + "</tr></thead>"
        f'<tbody data-slot="table-body" class="{cls("[&_tr:last-child]:border-0")}">'
        + "".join(f'<tr data-slot="table-row" class="{cls(TR_BODY)}">{r}</tr>' for r in rows)
        + "</tbody></table></div></div></div>"
    )


def td(html, align: str = "left", extra: str = "", prose: bool = False) -> str:
    base = TD_PROSE if prose else TD
    p_cls = ("text-right" if align == "right" else "text-left") + (" " + extra if extra else "")
    return f'<td data-slot="table-cell" class="{cls(base)}"><p class="{cls(p_cls)}">{html}</p></td>'


FAVICON = (
    "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'>"
    "<text y='13' font-size='13'>&#9622;</text></svg>"
)


def render_page(title, description, page_key, depth, body, script="", head="") -> str:
    """The one shell every generated page uses -- the reference page frame.

    depth  -- directories below the site root (2 for benchmarks/<id>/ and
              registry/<id>/). Drives asset hrefs and data-root.
    body   -- HTML placed inside the max-w-7xl content column.
    script -- optional JS, emitted after site.js (window.TDB is available).
    head   -- optional extra <head> markup.
    """
    root = "/".join([".."] * depth) if depth > 0 else "."
    tail = f'<script>\n{script}\n</script>\n' if script.strip() else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="stylesheet" href="{root}/assets/tw.css">
<link rel="stylesheet" href="{root}/assets/tw-extra.css">
<link rel="stylesheet" href="{root}/assets/site.css">
<link rel="icon" href="{FAVICON}">
{head}</head>
<body>

<main id="nd-home-layout" class="flex flex-1 flex-col pt-14">
  <!-- the fixed header is injected here by assets/site.js -->
  <div class="flex flex-1 flex-col items-center px-4 py-6 sm:pt-12">
    <div class="flex w-full max-w-7xl flex-1 flex-col" data-tdb-canary-host>
{body}
    </div>
  </div>
</main>

<script src="{root}/assets/site.js" data-root="{root}" data-page="{esc(page_key)}"></script>
{tail}</body>
</html>
"""


def _shown(path: Path) -> str:
    """Path as printed: relative to the release root when it lives under it."""
    try:
        return str(path.resolve().relative_to(RELEASE))
    except ValueError:
        return str(path)


def write_page(path: Path, html: str) -> str:
    """Idempotent write. Returns 'write' | 'update' | 'unchanged'."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") == html:
            print(f"  unchanged  {_shown(path)}")
            return "unchanged"
        path.write_text(html, encoding="utf-8")
        print(f"  update     {_shown(path)}")
        return "update"
    path.write_text(html, encoding="utf-8")
    print(f"  write      {_shown(path)}")
    return "write"


# ----------------------------------------------------------------- data loads

def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def safe_id(value) -> str | None:
    """Only ids that are safe as a single path segment become directories."""
    s = str(value or "").strip()
    if not s or s in {".", ".."} or not SAFE_ID.match(s):
        return None
    return s


def _toml_scalars(text: str) -> dict:
    """Tiny flat reader for the handful of task.toml scalars we display."""
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.split("  #")[0].strip()
        if v[:1] == '"' and v[-1:] == '"':
            v = v[1:-1]
        out.setdefault(k.strip(), v)
    return out


def load_task_package(task_id: str) -> dict:
    """Best-effort detail for one task, from the local package if it is shipped."""
    tid = safe_id(task_id)
    if not tid:
        return {}
    for split in ("archive", "live"):
        d = TASKS / split / tid
        if not d.is_dir():
            continue
        pkg = {"split": split, "path": f"tasks/{split}/{tid}"}
        pkg["record"] = read_json(d / "record.json", {}) or {}
        pkg["provenance"] = read_json(d / "PROVENANCE.json", {}) or {}
        toml = d / "task.toml"
        if toml.exists():
            pkg["toml"] = _toml_scalars(toml.read_text(encoding="utf-8", errors="replace"))
        instr = d / "instruction.md"
        if instr.exists():
            pkg["instruction"] = instr.read_text(encoding="utf-8", errors="replace")
        pkg["has_solution"] = (d / "solution").is_dir()
        return pkg
    return {}


def instruction_title(text: str) -> str:
    for line in (text or "").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


_MD = [
    (re.compile(r"`{1,3}([^`]*)`{1,3}"), r"\1"),          # code spans
    (re.compile(r"\*{1,3}([^*]+)\*{1,3}"), r"\1"),        # bold / italic
    (re.compile(r"\[([^\]]+)\]\([^)]*\)"), r"\1"),        # links -> label
    (re.compile(r"\s+"), " "),
]


def instruction_excerpt(text: str, limit: int = 700) -> str:
    """First prose paragraphs of the instruction, de-marked-down and trimmed."""
    body = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("```"):
            continue
        body.append(s.lstrip("-* "))
        if sum(len(b) for b in body) > limit:
            break
    out = " ".join(body)
    for pat, rep in _MD:
        out = pat.sub(rep, out)
    out = out.strip()[:limit]
    return out + ("…" if len(out) >= limit else "")


# ----------------------------------------------------------------- page bodies

def _pr_link(repo, pr_number) -> str:
    if repo and pr_number:
        url = f"https://github.com/{repo}/pull/{pr_number}"
        return (f'<a class="{cls(LINK)}" href="{esc(url)}" target="_blank" '
                f'rel="noopener noreferrer">{esc(repo)}#{esc(pr_number)}</a>')
    if repo:
        return (f'<a class="{cls(LINK)}" href="https://github.com/{esc(repo)}" '
                f'target="_blank" rel="noopener noreferrer">{esc(repo)}</a>')
    return DASH


def _h2(text) -> str:
    return f'<h2 class="mb-6 font-mono text-4xl tracking-tighter">{esc(text)}</h2>'


def _lede(html) -> str:
    return f'<p class="text-muted-foreground mb-6 font-mono text-sm">{html}</p>'


def _section(inner) -> str:
    return f'<div class="flex flex-col py-12 sm:pb-16">{inner}</div>'


def suite_page_body(suite: dict, suite_tasks: list) -> str:
    sid = suite.get("id", "")
    live = suite.get("status") == "live"
    langs = suite.get("languages") or sorted(
        {t.get("language") for t in suite_tasks if t.get("language")}
    )
    n_tasks = suite.get("n_tasks")
    if n_tasks is None:
        n_tasks = len(suite_tasks)
    solved_any = sum(1 for t in suite_tasks if (t.get("solved_by") or 0) > 0)
    f2p = sum(t.get("n_fail_to_pass") or 0 for t in suite_tasks)

    head = [
        breadcrumb([("Home", "../../"), ("Benchmarks", "../"), (f"suite {sid}", None)]),
        _h2(f"suite {sid}"),
        _lede(
            "Gold patch and protected tests are withheld while this suite is live; "
            "submissions are scored server-side by re-laying the protected tests."
            if live
            else "Archived and released in full &mdash; environment, protected tests and the "
            "reference solution &mdash; so every number here can be reproduced locally."
        ),
        tags(status_pill(suite.get("status", "")),
             *[pill(l, "outline") for l in langs]),
        button_row([
            ("all suites", "../", False),
            ("leaderboard", "../../leaderboard/", False),
            ("task registry", "../../registry/", False),
        ]),
        '<div class="-mx-4 mb-6 sm:mx-0" id="rail"></div>',
    ]

    stats = strip([
        ("tasks", n_tasks, "one merged pull request each"),
        ("languages", len(langs) or None, "mined across the ecosystem"),
        ("fail-to-pass tests", f2p or None, "re-laid over the agent's workspace"),
        ("solved by a model", solved_any, "execution-verified"),
        ("false-accepts", 0, "the gate cannot be talked into a pass"),
        ("status", suite.get("status") or None, "live is sealed; archive is released in full"),
    ])

    if suite_tasks:
        rows = []
        for t in suite_tasks:
            tid = t.get("id", "")
            href = f"../../registry/{tid}/" if safe_id(tid) else "../../registry/"
            solved = t.get("solved_by")
            n_models = t.get("n_models")
            if solved is None or not n_models:
                cell = DASH
            else:
                muted = "" if solved else " text-muted-foreground"
                cell = f'<span class="tabular-nums{muted}">{esc(solved)}/{esc(n_models)}</span>'
            rows.append(
                td(f'<a class="{cls(LINK)}" href="{esc(href)}">{esc(tid)}</a>')
                + td(esc(t.get("title") or ""), prose=True)
                + td(_pr_link(t.get("repo"), t.get("pr_number")))
                + td(pill(t.get("language"), "outline") if t.get("language") else DASH)
                + td(pill(t.get("difficulty")) if t.get("difficulty") else DASH)
                + td(esc(t.get("n_fail_to_pass") or 0), "right", "tabular-nums")
                + td(cell, "right")
            )
        table = table_block(
            [("Task", "left"), ("What it asks for", "left"), ("Source pull request", "left"),
             ("Language", "left"), ("Difficulty", "left"),
             ("F2P Tests", "right"), ("Solved By", "right")],
            rows,
        )
    else:
        table = (
            '<div class="-mx-4 mb-6 flex flex-col md:mx-0">'
            + empty(
                "This suite has no published task list. Live suites expose their tasks only "
                "through the scoring endpoint until they are archived."
            )
            + "</div>"
        )

    cmd = (
        ["tdb submit &lt;RESULTS.jsonl&gt;   # re-scored by the same gate on ingest"]
        if live
        else [
            "tdb run    &lt;MODEL&gt; tasks/archive/&lt;task-id&gt;",
            "tdb oracle tasks/archive/&lt;task-id&gt;   # -&gt; reward 1.0",
        ]
    )

    return "\n".join([
        "\n".join(head),
        _section(
            sec_head("tasks in this suite", suite.get("note") or "",
                     ("../../registry/", "all tasks"))
            + stats
            + table
        ),
        _section(
            sec_head("how this suite is scored", "execution proof only")
            + code_figure(
                "Run one task, then prove it is solvable with the oracle patch"
                if not live else "Run your model, then submit the patch",
                cmd,
            )
            + '<p class="text-muted-foreground mx-auto max-w-3xl text-center font-mono '
              'text-sm/relaxed">A patch is applied to a throwaway copy of the workspace. The '
              "workspace tests are discarded, the protected tests are re-laid from the trusted "
              "package, and they run with the network cut. The reward is that run's outcome and "
              'nothing else, so <span class="text-foreground">false_accept = 0</span> holds by '
              "construction.</p>"
        ),
    ])


SUITE_SCRIPT = """(async function () {
  var T = window.TDB;
  var site = await T.getJSON("site_data.json").catch(function () { return null; });
  if (site && site.suites) {
    T.dayRail(document.getElementById("rail"), site.suites, %s);
  }
})();"""


def task_page_body(task: dict, pkg: dict) -> str:
    """SHARED task-page body. The registry generator renders this inside render_page(depth=2)."""
    tid = task.get("id", "")
    suite = task.get("suite", "")
    live = task.get("status") == "live"
    rec = (pkg or {}).get("record") or {}
    tom = (pkg or {}).get("toml") or {}
    instruction = (pkg or {}).get("instruction") or ""

    repo = task.get("repo") or rec.get("repo") or tom.get("source_repo")
    pr = task.get("pr_number") or rec.get("pr_number") or tom.get("pr_number")
    title = task.get("title") or tom.get("description") or instruction_title(instruction)
    f2p = rec.get("fail_to_pass") or []
    n_f2p = task.get("n_fail_to_pass") or len(f2p) or None
    language = task.get("language") or rec.get("language")
    difficulty = task.get("difficulty") or tom.get("difficulty")

    buttons = []
    if safe_id(suite):
        buttons.append((f"suite {suite}", f"../../benchmarks/{suite}/", False))
    buttons.append(("all tasks", "../", False))
    if repo and pr:
        buttons.append(("source pull request", f"https://github.com/{repo}/pull/{pr}", False))
    buttons.append(("how to submit", "../../submit/", False))

    head = [
        breadcrumb([("Home", "../../"), ("Tasks", "../"), (tid, None)]),
        _h2(title or tid),
        _lede(
            f'<span class="text-foreground">{esc(tid)}</span> &middot; mined from a real merged '
            "pull request, rebuilt into a package an agent can be dropped into. Nothing here is "
            "authored by a model, and the solve is minted by re-executing protected tests."
        ),
        tags(status_pill(task.get("status", "")),
             pill(language, "outline") if language else "",
             pill(difficulty) if difficulty else ""),
        button_row(buttons),
    ]

    solved, n_models = task.get("solved_by"), task.get("n_models")
    stats = strip([
        ("language", language or None, "the upstream repository's language"),
        ("difficulty", difficulty or None, "derived from who solved it"),
        ("fail-to-pass tests", n_f2p, "must fail before the patch, pass after"),
        ("solved by",
         f"{solved}/{n_models}" if solved is not None and n_models else None,
         "execution-verified solves"),
        ("false-accepts", 0, "the gate cannot be talked into a pass"),
        ("suite", suite or None, "every day is its own sealed suite"),
    ])

    suite_cell = (
        f'<a class="{cls(LINK)}" href="../../benchmarks/{esc(suite)}/">{esc(suite)}</a>'
        if safe_id(suite) else (esc(suite) or DASH)
    )
    facts = [
        ("Task id", f'<span class="text-foreground">{esc(tid)}</span>'),
        ("Suite", suite_cell),
        ("Status", status_pill(task.get("status", ""))),
        ("Source", _pr_link(repo, pr)),
        ("Base commit", esc(rec.get("base_sha", "")) if rec.get("base_sha") else None),
        ("Merge commit", esc(rec.get("merge_sha", "")) if rec.get("merge_sha") else None),
        ("Network at run time", esc(rec.get("network_profile") or "run-offline")),
        ("Upstream license", esc(rec.get("source_license_spdx") or "see source repository")),
    ]
    fact_rows = [
        f'<th data-slot="table-head" class="{cls(TH)}">{esc(k)}</th>' + td(v)
        for k, v in facts if v
    ]
    fact_table = (
        '<div class="-mx-4 mb-6 flex flex-col md:mx-0">'
        '<div class="bg-card border-y font-mono md:border-x">'
        '<div data-slot="table-container" class="relative w-full overflow-x-auto">'
        f'<table data-slot="table" class="{cls(TABLE)}">'
        f'<tbody data-slot="table-body" class="{cls("[&_tr:last-child]:border-0")}">'
        + "".join(f'<tr data-slot="table-row" class="{cls(TR_BODY)}">{r}</tr>' for r in fact_rows)
        + "</tbody></table></div></div></div>"
    )

    brief = ""
    if instruction:
        brief = _section(
            sec_head("what the agent is asked to do", "the instruction it sees")
            + '<div class="-mx-4 mb-6 flex flex-col md:mx-0">'
            + prose_block(f"<p>{esc(instruction_excerpt(instruction))}</p>")
            + "</div>"
        )

    if f2p and not live:
        items = "".join(
            f'<li class="border-b py-2 last:border-b-0">{esc(x)}</li>' for x in f2p
        )
        f2p_block = _section(
            sec_head("fail-to-pass tests", "must fail before the patch, pass after")
            + '<div class="-mx-4 mb-6 flex flex-col md:mx-0">'
            + prose_block(f'<ul class="flex flex-col">{items}</ul>')
            + "</div>"
        )
    elif live:
        f2p_block = _section(
            sec_head("protected tests", "withheld while the suite is live")
            + '<div class="-mx-4 mb-6 flex flex-col md:mx-0">'
            + empty(
                "This task is in a live suite: the protected test bodies and the reference "
                "solution are withheld. Only the failing-test identifiers are exposed to the "
                "agent, and scoring happens server-side. The package is released in full when "
                "the suite is archived, two weeks after it was sealed."
            )
            + "</div>"
        )
    else:
        f2p_block = ""

    cmd = (
        ["tdb submit &lt;RESULTS.jsonl&gt;"]
        if live
        else [
            f"tdb run    &lt;MODEL&gt; tasks/archive/{esc(tid)}",
            f"tdb oracle tasks/archive/{esc(tid)}   # -&gt; reward 1.0",
        ]
    )
    run = _section(
        sec_head("reproduce it", "archived tasks ship complete" if not live else "live task")
        + code_figure("Score a model on this task, then prove it is solvable", cmd)
        + '<p class="text-muted-foreground mx-auto max-w-3xl text-center font-mono '
          'text-sm/relaxed">The reward is the outcome of the re-laid protected tests, nothing '
          "else. A submitted reward is advisory and is replayed on ingest. "
          f'<a class="hover:text-foreground underline underline-offset-4" href="../../submit/">'
          "how to submit &rarr;</a></p>"
    )

    body = [
        "\n".join(h for h in head if h),
        _section(
            sec_head("provenance", "mined from a real merged pull request")
            + stats
            + fact_table
        ),
        brief,
        f2p_block,
        run,
    ]
    return "\n".join(b for b in body if b)


# ----------------------------------------------------------------- generation

def collect(site: dict, registry: dict):
    """Suites + tasks, preferring site_data.json and falling back to registry.json."""
    suites = list((site or {}).get("suites") or [])
    tasks = list((site or {}).get("tasks") or [])
    if not suites:
        suites = list((registry or {}).get("suites") or [])
    # de-duplicate suites by id, keeping the first
    seen, out = set(), []
    for s in suites:
        sid = safe_id(s.get("id"))
        if not sid or sid in seen:
            if not sid:
                print(f"  skip       suite with unusable id: {s.get('id')!r}", file=sys.stderr)
            continue
        seen.add(sid)
        out.append(s)
    return out, tasks


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--docs", default=str(DOCS), help="site root (default: release/docs)")
    ap.add_argument("--suites-only", action="store_true", help="skip per-task pages")
    ap.add_argument("--tasks-only", action="store_true", help="skip per-suite pages")
    args = ap.parse_args(argv)

    docs = Path(args.docs).resolve()
    registry = read_json(RELEASE / "registry.json", {}) or {}
    site = read_json(docs / "site_data.json")
    if site is None:
        print(f"note: {docs / 'site_data.json'} not found - falling back to registry.json")
        site = {}

    suites, tasks = collect(site, registry)
    by_suite = {}
    for t in tasks:
        by_suite.setdefault(t.get("suite"), []).append(t)

    counts = {"write": 0, "update": 0, "unchanged": 0}

    def tally(action):
        counts[action] = counts.get(action, 0) + 1

    if not args.tasks_only:
        print(f"suites -> {docs / 'benchmarks'}")
        if not suites:
            print("  (none: neither site_data.json nor registry.json lists a suite)")
        for s in suites:
            sid = safe_id(s.get("id"))
            st = by_suite.get(s.get("id"), [])
            html = render_page(
                title=f"suite {sid} — terminal-daily-bench",
                description=(
                    f"The {sid} daily suite: "
                    f"{s.get('n_tasks', len(st))} tasks mined from merged pull requests, "
                    f"scored by re-laid protected tests."
                ),
                page_key="benchmarks",
                depth=2,
                body=suite_page_body(s, st),
                script=SUITE_SCRIPT % json.dumps(sid),
            )
            tally(write_page(docs / "benchmarks" / sid / "index.html", html))

    if not args.suites_only:
        print(f"tasks  -> {docs / 'registry'}")
        if not tasks:
            print("  (none: site_data.json has no tasks[])")
        seen = set()
        for t in tasks:
            tid = safe_id(t.get("id"))
            if not tid:
                print(f"  skip       task with unusable id: {t.get('id')!r}", file=sys.stderr)
                continue
            if tid in seen:
                continue
            seen.add(tid)
            pkg = load_task_package(tid)
            html = render_page(
                title=f"{t.get('title') or tid} — terminal-daily-bench",
                description=(
                    f"Task {tid} from suite {t.get('suite', '')}, mined from "
                    f"{t.get('repo', 'a merged pull request')}. Scored by re-laid protected tests."
                ),
                page_key="tasks",
                depth=2,
                body=task_page_body(t, pkg),
            )
            tally(write_page(docs / "registry" / tid / "index.html", html))

    total = sum(counts.values())
    print(
        f"done: {total} page(s) - {counts['write']} new, "
        f"{counts['update']} updated, {counts['unchanged']} unchanged"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
