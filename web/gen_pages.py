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
    ../../assets/site.css      the Terminal Daily visual system
    ../../assets/site.js       data-root="../.." data-page="<key>"

The utility build provides stable layout primitives. Semantic tdb-* hooks name
our own components, while site.css owns their product-specific geometry, type,
colour, and interaction. Generated markup remains dependency-free and readable.

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
    strip(pairs)                the Terminal Daily metric-card band
    sec_head(title, eyebrow="", more=None)   an editorial section header
    task_page_body(task, pkg)   the shared BODY for one task page
    load_task_package(task_id)  best-effort dict from tasks/{archive,live}/<id>/
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
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
# TERMINAL DAILY COMPONENT STRUCTURE
# The utility tokens keep layout deterministic; tdb-* hooks carry our identity
# and remain stable if the vendored utility build changes.
# ============================================================================

CARD = (
    "tdb-card bg-card text-card-foreground flex flex-col gap-6 border py-0 "
    "transition-all duration-200"
)
CARD_HEADER = (
    "tdb-card-header @container/card-header grid auto-rows-min grid-rows-[auto_auto] items-start "
    "gap-1.5 px-6 has-data-[slot=card-action]:grid-cols-[1fr_auto] [.border-b]:pb-6"
)

_BADGE_BASE = (
    "tdb-badge inline-flex items-center justify-center border px-2 py-0.5 text-sm sm:text-xs "
    "font-medium w-fit whitespace-nowrap shrink-0 [&>svg]:size-3 gap-1 "
    "[&>svg]:pointer-events-none focus-visible:border-ring focus-visible:ring-ring/50 "
    "focus-visible:ring-[3px] aria-invalid:ring-destructive/20 "
    "dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive "
    "transition-[color,box-shadow] overflow-hidden "
)
BADGE_PRIMARY = _BADGE_BASE + (
    "border-transparent bg-primary text-primary-foreground "
    "[a&]:hover:bg-primary/90"
)
BADGE_SECONDARY = _BADGE_BASE + (
    "border-transparent bg-secondary text-secondary-foreground "
    "[a&]:hover:bg-secondary/90"
)
BADGE_OUTLINE = _BADGE_BASE + "text-foreground"

_BTN = (
    "tdb-button inline-flex shrink-0 items-center justify-center gap-2 font-medium "
    "whitespace-nowrap transition-all outline-none focus-visible:border-ring "
    "focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none "
    "disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 "
    "dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 "
    "[&_svg:not([class*='size-'])]:size-4 "
)
BTN_PRIMARY = _BTN + "bg-primary text-primary-foreground hover:bg-primary/90 h-12 px-8 text-base has-[>svg]:px-6"
BTN_SECONDARY = _BTN + "bg-secondary text-secondary-foreground hover:bg-secondary/80 h-12 px-8 text-base has-[>svg]:px-6"

TABLE = (
    "tdb-table w-full caption-bottom text-sm [&_tr>td:first-child]:pl-6 [&_tr>td:last-child]:pr-6 "
    "[&_tr>th:first-child]:pl-6 [&_tr>th:last-child]:pr-6"
)
_CHK = "[&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-[2px]"
TH = ("text-foreground h-10 px-2 text-left align-middle font-medium whitespace-nowrap "
      + _CHK + " py-3 text-base")
TD = "p-2 align-middle whitespace-nowrap " + _CHK + " py-4 text-base"
# Most cells stay on one line; a descriptive cell deliberately drops nowrap.
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
    """Escape a class string so arbitrary variants survive round-tripping."""
    return value.replace("&", "&amp;").replace(">", "&gt;")


def pill(text, kind: str = "") -> str:
    """A compact metadata badge. kind: primary | outline | "" (secondary)."""
    variant = {"primary": BADGE_PRIMARY, "outline": BADGE_OUTLINE}.get(kind, BADGE_SECONDARY)
    return f'<span data-slot="badge" class="{cls(variant)}">{esc(text)}</span>'


def status_pill(status: str) -> str:
    """Describe what readers can access without internal release terminology."""
    label = {"live": "Solutions not yet public", "archive": "Solutions available"}.get(
        status, "Availability not specified"
    )
    return pill(label, "primary" if status == "live" else "")


def tags(*items) -> str:
    inner = "".join(i for i in items if i)
    return f'<div class="mb-6 flex flex-wrap gap-2">{inner}</div>' if inner else ""


def stat_card(label, value, note: str = "") -> str:
    """One metric as a line: label, value, note.

    It was a bordered card with a coloured stripe. Six of them opened every
    task page -- a full screen for six numbers, most of which the fact table
    directly underneath repeated. Same information, three columns, four lines.
    """
    shown = DASH if value in (None, "") else esc(value)
    return (
        f'<div class="tdb-statrow">'
        f'<span class="tdb-statrow-k">{esc(label)}</span>'
        f'<p data-tdb-stat-value class="tdb-statrow-v">{shown}</p>'
        f'<span class="tdb-statrow-n">{esc(note)}</span>'
        f"</div>"
    )


def strip(pairs) -> str:
    """The stat band: one line per metric, two columns on a wide screen.

    `pairs` is [(label, value)] or [(label, value, note)].
    """
    cells = "".join(
        stat_card(p[0], p[1], p[2] if len(p) > 2 else "") for p in pairs
    )
    return f'<div class="tdb-statgrid mb-6">{cells}</div>'


def sec_head(title, eyebrow: str = "", more=None) -> str:
    """The same section heading used by the catalogue and report pages."""
    out = [
        '<div class="tdb-block-head tdb-section-head">',
        f'<h2>{esc(title)}</h2>',
    ]
    if eyebrow:
        out.append(f'<p>{esc(eyebrow)}</p>')
    if more:
        href, label = more
        out.append(
            f'<a class="tdb-block-tools" href="{esc(href)}">{esc(label)} &rarr;</a>'
        )
    out.append("</div>")
    return "".join(out)


def empty(msg_html: str) -> str:
    """A quiet empty-state panel."""
    return (
        '<div class="tdb-panel bg-card border-y px-6 py-8 text-sm '
        f'text-muted-foreground md:border-x">{msg_html}</div>'
    )


def prose_block(html: str) -> str:
    """A readable long-form panel kept separate from dense data tables."""
    return (
        '<div class="tdb-panel bg-card border-y px-6 py-6 text-sm/relaxed md:border-x">'
        f"{html}</div>"
    )


def code_figure(caption: str, lines) -> str:
    """Self-contained command figure (caption row plus scrollable code)."""
    body = "\n".join(lines)
    return (
        '<figure dir="ltr" class="tdb-code">'
        f'<figcaption>{esc(caption)}</figcaption>'
        f'<pre tabindex="0"><code>{body}</code></pre></figure>'
    )


def button_row(buttons) -> str:
    """Related pages as one line of links: [(label, href, primary_bool)].

    These were four full-width pill buttons in a responsive grid. Nothing here
    is an action -- they are links to sibling pages -- and a row of buttons
    above the content pushes the content off the screen.
    """
    cells = "".join(
        f'<a class="tdb-navlink" data-primary="{"true" if primary else "false"}" '
        f'href="{esc(href)}">{esc(label)}</a>'
        for label, href, primary in buttons
    )
    return f'<div class="tdb-heading-links">{cells}</div>' if cells else ""


def page_heading(title: str, *, actions: str = "", metadata: str = "", attributes: str = "") -> str:
    """Shared page heading: title, optional actions, and optional context."""
    return (
        f'<header class="tdb-page-heading tdb-detail-heading"{attributes}>'
        f'<div class="tdb-heading-main"><h1 class="tdb-page-title">{esc(title)}</h1></div>'
        + (f'<div class="tdb-heading-actions">{actions}</div>' if actions else "")
        + (f'<div class="tdb-heading-context">{metadata}</div>' if metadata else "")
        + '</header>'
    )


def table_block(headers, rows, *, catalogue: bool = False) -> str:
    """A horizontally scrollable Terminal Daily data surface.

    headers -- [(label, align, optional_css_role)] where align is "left" | "right"
    rows    -- list of already-rendered "<td …>…</td>" strings
    catalogue -- progressively enhance suite tasks with search and pagination
    """
    ths = []
    for column in headers:
        label, align = column[:2]
        role = column[2] if len(column) > 2 else ""
        inner = (f'<div class="flex justify-end">{esc(label)}</div>'
                 if align == "right" else esc(label))
        ths.append(f'<th scope="col" data-slot="table-head" class="{cls(TH + " " + role)}">{inner}</th>')
    catalogue_hook = ' data-tdb-suite-tasks' if catalogue else ""
    table_label = ' aria-label="Tasks in this release"' if catalogue else ""
    return (
        f'<div class="mb-6 flex flex-col"{catalogue_hook}>'
        '<div class="tdb-table-shell bg-card border-y md:border-x">'
        '<div data-slot="table-container" class="relative w-full overflow-x-auto">'
        f'<table data-slot="table" class="{cls(TABLE + " tdb-detail-table")}"{table_label}>'
        f'<thead data-slot="table-header" class="{cls("[&_tr]:border-b")}">'
        f'<tr data-slot="table-row" class="{cls(TR_HEAD)}">' + "".join(ths) + "</tr></thead>"
        f'<tbody data-slot="table-body" class="{cls("[&_tr:last-child]:border-0")}">'
        + "".join(f'<tr data-slot="table-row" class="{cls(TR_BODY)}">{r}</tr>' for r in rows)
        + "</tbody></table></div></div></div>"
    )


def td(html, align: str = "left", extra: str = "", prose: bool = False, cell_class: str = "") -> str:
    base = TD_PROSE if prose else TD
    p_cls = ("text-right" if align == "right" else "text-left") + (" " + extra if extra else "")
    return f'<td data-slot="table-cell" class="{cls(base + " " + cell_class)}"><p class="{cls(p_cls)}">{html}</p></td>'


# The cache-busting token on every asset URL, derived from the assets' own
# bytes. It used to be a literal typed here AND into every hand-written page,
# so changing an asset meant remembering to bump it in two places -- and the
# first time that mattered, site.css changed, the token did not, and the
# browser served the old stylesheet against the new markup. See
# web/asset_version.py; `--check` fails the build when a page is stale.
from asset_version import current as _asset_version   # noqa: E402

ASSET_V = _asset_version()

FAVICON = (
    "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' "
    "fill='none' stroke='%23315aba' stroke-width='1.6'>"
    "<rect x='2' y='3' width='20' height='18'/><path d='M6 8l4 4-4 4 M13 16h5'/></svg>"
)


def render_page(title, description, page_key, depth, body, script="", head="") -> str:
    """The shared Terminal Daily page frame.

    depth  -- directories below the site root (2 for benchmarks/<id>/ and
              registry/<id>/). Drives asset hrefs and data-root.
    body   -- HTML placed inside the shared page content column.
    script -- optional JS, emitted after site.js (window.TDB is available).
    head   -- optional extra <head> markup.
    """
    root = "/".join([".."] * depth) if depth > 0 else "."
    tail = f'<script>\n{script}\n</script>\n' if script.strip() else ""
    if page_key in {"tasks", "benchmarks"}:
        modules = ["tdb-data", "tdb-releases"]
        if page_key == "tasks":
            modules.append("tdb-runs")
        tail = "".join(f'<script src="{root}/assets/{name}.js?v={ASSET_V}"></script>\n' for name in modules) + tail
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="stylesheet" href="{root}/assets/tw.css?v={ASSET_V}">
<link rel="stylesheet" href="{root}/assets/site.css?v={ASSET_V}">
<link rel="icon" href="{FAVICON}">
{head}</head>
<body class="tdb-generated-page">

<main id="nd-home-layout" class="flex flex-1 flex-col pt-14">
  <!-- the fixed header is injected here by assets/site.js -->
  <div class="tdb-page-frame">
    <div class="tdb-page-container tdb-detail-frame" data-tdb-canary-host>
{body}
    </div>
  </div>
</main>

<script src="{root}/assets/site.js?v={ASSET_V}" data-root="{root}" data-page="{esc(page_key)}"></script>
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
        path.write_text(html, encoding="utf-8", newline="\n")
        print(f"  update     {_shown(path)}")
        return "update"
    path.write_text(html, encoding="utf-8", newline="\n")
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


def load_detail_data(path: Path) -> dict[str, dict]:
    """Read metadata-only public task details; reject unexpected package fields."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("task detail data must be a task-id mapping")
    allowed = {"instruction", "summary", "record", "toml", "split", "has_solution"}
    record_fields = {"repo", "pr_number", "source_license_spdx"}
    toml_fields = {"description", "difficulty", "source_repo", "pr_number"}
    for tid, package in data.items():
        if not safe_id(tid) or not isinstance(package, dict) or set(package) - allowed:
            raise ValueError("invalid task identity or unsupported task detail fields")
        if not isinstance(package.get("instruction", ""), str):
            raise ValueError("task instruction must be a string")
        if not isinstance(package.get("summary", ""), str):
            raise ValueError("task summary must be a string")
        for key, fields in (("record", record_fields), ("toml", toml_fields)):
            values = package.get(key, {})
            if not isinstance(values, dict) or set(values) - fields:
                raise ValueError("unsupported task metadata fields")
            for name, value in values.items():
                if name == "pr_number":
                    if value is not None and (type(value) is not int or value <= 0):
                        raise ValueError("task pull request number must be a positive integer")
                elif not isinstance(value, str):
                    raise ValueError("task metadata text must be a string")
        if package.get("split", "live") not in {"live", "archive"}:
            raise ValueError("unknown task publication status")
        if type(package.get("has_solution", False)) is not bool:
            raise ValueError("task solution availability must be boolean")
    return data


def task_suites(task: dict) -> list[str]:
    """Normalise the many-to-many suite edge list for page consumers.

    ``suite`` remains in site_data.json for old clients, but filtering and links
    must use ``suites`` or a carried task silently disappears from every suite
    except whichever one happened to become its scalar compatibility value.
    """
    values = task.get("suites")
    if not isinstance(values, list):
        values = [task.get("suite")]
    return sorted({str(value) for value in values if value})


def index_tasks_by_suite(tasks: list[dict]) -> dict[str, list[dict]]:
    """Build a many-to-many suite index without duplicating a task in one suite."""
    out: dict[str, list[dict]] = {}
    seen: dict[str, set[str]] = {}
    for task in tasks:
        identity = str(task.get("id") or "")
        for sid in task_suites(task):
            if identity and identity in seen.setdefault(sid, set()):
                continue
            if identity:
                seen[sid].add(identity)
            out.setdefault(sid, []).append(task)
    return out


def instruction_title(text: str) -> str:
    for line in (text or "").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


# Every instruction opens with the same harness preamble and closes with the same
# goal line. Both repeat across task pages, so neither says anything about
# the task the page is about; the excerpt starts at the task-specific text instead.
_INSTRUCTION_BOILERPLATE = (
    "You are working in a checked-out source repository. The upstream provenance "
    "(origin remote, project name, and commit identifiers) has been removed; solve "
    "the task from the working tree and the description below alone.",
    "You are working in a checked-out source repository. The upstream provenance "
    "(origin remote, project name, and commit identifiers) has been removed; solve "
    "the task from the working tree and the specification below alone.",
    "Make the change so that the project's regression tests pass. "
    "Do not edit the test files.",
)


_MD = [
    (re.compile(r"(?<!\w)(\*{1,3})(?=\S)(.+?)(?<=\S)\1(?!\w)"), r"\2"),
    (re.compile(r"\[([^\]]+)\]\([^)]*\)"), r"\1"),        # links -> label
    (re.compile(r"\s+"), " "),
]


def instruction_excerpt(text: str, limit: int = 700) -> str:
    """First prose paragraphs of the instruction, de-marked-down and trimmed."""
    body = []
    in_code = False
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith(("```", "~~~")):
            in_code = not in_code
            continue
        if in_code or not s or s.startswith("#"):
            continue
        if s.startswith("**") and s.endswith("**") and s.count("**") == 2:
            continue
        body.append(re.sub(r"^(?:[-*+]\s+|\d+\.\s+)", "", s))
        if sum(len(b) for b in body) > limit:
            break
    out = " ".join(body)
    code = []

    def preserve_code(match):
        code.append(match.group(1))
        return f"\ue000{len(code) - 1}\ue001"

    # Code may contain multiplication or exponentiation; Markdown cleanup must
    # not turn a quoted expression such as j**2 + 4*j into a different formula.
    out = re.sub(r"`{1,3}([^`]*)`{1,3}", preserve_code, out)
    for pat, rep in _MD:
        out = pat.sub(rep, out)
    for index, value in enumerate(code):
        out = out.replace(f"\ue000{index}\ue001", value)
    out = out.strip()
    if len(out) > limit:
        return out[:limit].rsplit(" ", 1)[0].rstrip(".,;:") + "…"
    return out


def clean_instruction_text(text: str) -> str:
    """Remove generation boilerplate while preserving literal comment examples."""
    code = []

    def protect(match):
        code.append(match.group(0))
        return f"\ue100{len(code) - 1}\ue101"

    text = re.sub(r"(`{1,3}|~{3})(.+?)\1", protect, text, flags=re.S)
    for chunk in _INSTRUCTION_BOILERPLATE:
        text = text.replace(chunk, "")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    for line in (
        "These names are referenced by the project's regression tests and must exist exactly as written.",
        "These methods are not defined anywhere in the tests, so they must be added to the project.",
        "This list is derived from the project's regression tests and is not exhaustive; it names what the tests reference by name, not everything the change must do.",
    ):
        text = text.replace(line, "")
    text = re.sub(r"(?m)^## Context \(de-identified\)\s*$", "", text)
    text = re.sub(r"(?m)^\s*\[redacted-ref\]\.?\s*$", "", text)
    for index, value in enumerate(code):
        text = text.replace(f"\ue100{index}\ue101", value)
    text = re.sub(r"(?m)^## Goal\s*\Z", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def task_summary(text: str, limit: int = 420) -> str:
    """Extract one public prose paragraph, omitting setup and provenance text."""
    text = clean_instruction_text(text)
    text = re.sub(r'(?ms)^\[//\]:\s*#\s*"\s*\n.*?^\s*"\s*$', "", text)
    text = re.sub(r"<summary\b[^>]*>.*?</summary>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"</?(?:details|div|p)\b[^>]*>", "", text, flags=re.IGNORECASE)
    paragraphs, lines = [], []
    in_code = False
    skip_section = False
    for raw in (text or "").splitlines() + [""]:
        line = raw.strip()
        if line.startswith(("```", "~~~")):
            in_code = not in_code
            line = ""
        elif in_code:
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)", line)
        if not line or heading:
            if lines:
                paragraphs.append("\n".join(lines))
                lines = []
            if heading:
                depth, label = len(heading[1]), heading[2]
                if depth > 1:
                    skip_section = not re.search(
                        r"^(?:context\b|summary\b|description\b|overview\b|problem\b|"
                        r"bug\b|what(?:'s| is| changed| this)\b|fix\b|changes\b|"
                        r"motivation\b|implementation\b|why (?:this|it)\b|root cause\b|"
                        r"proposed (?:fix|change)\b|required behavio[u]?r\b)", label, re.IGNORECASE
                    )
            continue
        if skip_section or re.fullmatch(r"(?:[-*]\s+)?\*\*[^*]+\*\*:? *", line):
            continue
        if re.match(r"^(?:[-*+]\s+|\d+\.\s+)", line):
            if lines:
                paragraphs.append("\n".join(lines))
                lines = []
            paragraphs.append(line)
            continue
        lines.append(line)

    omitted = re.compile(
        r"\[redacted[^\]]*\]|\b[0-9a-f]{7,64}\b|"
        r"(?:https?://|[A-Za-z]:[\\/]|(?<!\w)\.{1,2}[\\/])|"
        r"\b[\w.-]+(?:[\\/][\w.@+-]+)+\b|"
        r"no task description provided|"
        r"please (?:include|describe|fill|check)|include a description of|"
        r"how does someone fix|by submitting this pull request|we use the title|"
        r"\b(?:I|my|we|our)\b|"
        r"thank you|feel free to|powered by|release note:|"
        r"this (?:PR|pull request) (?:should )?fix(?:es)? this issue|"
        r"^(?:amend|commit|merge|cherry[- ]pick|co-authored-by|signed-off-by|"
        r"the last commit|previous style|no release,|"
        r"(?:added|contains) (?:a |new |unit |regression )*(?:tests?|unittests))\b",
        re.IGNORECASE | re.MULTILINE,
    )
    for paragraph in paragraphs:
        if omitted.search(paragraph) or paragraph.startswith(("|", ">", "![", "- [", "* [")):
            continue
        prose = instruction_excerpt(paragraph, len(paragraph) + 1)
        if omitted.search(prose):
            continue
        if len(prose) > limit or prose.endswith(":"):
            complete = list(re.finditer(r"[.!?](?=\s+[A-Z]|\s*$)", prose[:limit]))
            if complete:
                prose = prose[:complete[-1].end()]
            elif prose.endswith(":"):
                continue
            else:
                prose = prose[:limit].rsplit(" ", 1)[0].rstrip(".,;:") + "…"
        # Count whole words, not pieces of identifiers: a bare equation or
        # change-record fragment does not explain a task to a reader.
        if len(re.findall(r"\b[A-Za-z]{2,}\b", prose)) < 6 and len(re.findall(r"[\u3400-\u9fff]", prose)) < 24:
            continue
        return prose
    return ""


# ----------------------------------------------------------------- page bodies

def _pr_link(repo, pr_number) -> str:
    project = str(repo).rsplit("/", 1)[-1] if repo else ""
    if repo and pr_number:
        url = f"https://github.com/{repo}/pull/{pr_number}"
        return (f'<a class="{cls(LINK)}" href="{esc(url)}" target="_blank" '
                f'rel="noopener noreferrer">{esc(project)} #{esc(pr_number)}</a>')
    if repo:
        return (f'<a class="{cls(LINK)}" href="https://github.com/{esc(repo)}" '
                f'target="_blank" rel="noopener noreferrer">{esc(project)}</a>')
    return DASH


def _section(inner) -> str:
    return f'<section class="tdb-block tdb-content-section">{inner}</section>'


def _release_label(sid: str) -> str:
    """Dates identify releases; internal identifiers stay in their URLs."""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", sid or ""):
        return f"{sid} release"
    return {"sample": "Sample tasks", "sample-live": "Sample preview"}.get(
        sid, "Task collection"
    )


def _task_title(task: dict, pkg: dict | None = None) -> str:
    package = pkg or {}
    return clean_task_title(task.get("title") or (package.get("toml") or {}).get("description")
                            or instruction_title(package.get("instruction") or ""))


def clean_task_title(text: str) -> str:
    """Remove publishing syntax without reconstructing redacted names."""
    text = str(text or "").strip()
    text = re.sub(r"^(?:fix|feat|perf|refactor|docs|test|chore|build|ci|style)(?:\([^)]*\))?!?:\s*", "", text, flags=re.I)
    text = re.sub(r"\([^()]*\[redacted-ref\][^()]*\)", "", text, flags=re.I)
    text = re.sub(r"\[redacted[^\]]*\]", "", text, flags=re.I)
    text = re.sub(r"\b[0-9a-f]{8,64}\b", "", text, flags=re.I)
    text = text.replace("`", "")
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\s+([,;:)])", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip(" ,:;-")
    return text[:1].upper() + text[1:] if text else "Software maintenance task"


# Short editorial examples, grounded in each task's published instruction.md.
# These describe the requested change and its checks, never a model's reasoning.
TASK_CASES = {
    "td-a1e719fced6e790d": {
        "title": "Recognize image paths in any letter case",
        "goal": "Treat recognized image extensions as file paths regardless of letter case, even when the string could also decode as base64.",
        "success": "Missing image paths raise ValueError with a \"does not exist\" message; strings without a recognized image extension keep their base64 behavior.",
    },
    "td-c3d8f979a1b6446f": {
        "title": "Save configuration without breaking symbolic links",
        "goal": "Write configuration changes through each symbolic link to its real target, preserving the link and the target file's permissions.",
        "success": "Primary and included files retain their links and permission bits; dangling targets are created with mode 0o600 and temporary files are cleaned up.",
    },
    "td-a12f9e85169e6c4b": {
        "title": "Resume downloads without corrupting the file",
        "goal": "Decide whether to resume from the server's actual HTTP response, validating range headers before appending bytes.",
        "success": "Restart on HTTP 200, reject invalid partial responses without changing the file, stop oversized streams, and clear saved state before retrying HTTP 416 responses.",
    },
    "td-fd876514b9fadbb9": {
        "title": "Keep quoted configuration values intact",
        "goal": "Split configuration directives at unquoted separators while preserving semicolons, braces, whitespace, and opposite-kind quotes inside quoted values.",
        "success": "Formatted text must match the expected output exactly, including original quoted contents and trailing newlines.",
    },
}


def case_cards(tasks: list[dict]) -> str:
    available = {task.get("id"): task for task in tasks}
    cards = []
    for tid, case in TASK_CASES.items():
        task = available.get(tid)
        if not task:
            continue
        project = str(task.get("repo") or "").rsplit("/", 1)[-1]
        cards.append(
            f'<article class="tdb-case" data-case-task="{esc(tid)}" data-case-observed-date="2026-09-17">'
            f'<p class="tdb-case-project">{esc(project)}</p><h3>{esc(case["title"])}</h3>'
            f'<p>{esc(case["goal"])}</p>'
            '<p class="tdb-case-outcome">Loading observed results&hellip;</p>'
            f'<a href="./registry/{esc(tid)}/" data-case-link>Task and model outcomes &rarr;</a></article>'
        )
    return "\n".join(cards)


def _evaluation_note(live: bool) -> str:
    text = "Official evaluation is not open yet; submissions do not receive an official score. "
    if not live:
        text += "Local evaluation requires a custom runner that is not yet public. "
    return (
        '<p class="tdb-detail-note text-muted-foreground text-sm/relaxed">'
        + text
        + '<a class="hover:text-foreground underline underline-offset-4" '
          'href="../../guide/quickstart/">How to evaluate a model &rarr;</a></p>'
    )


def suite_page_body(suite: dict, suite_tasks: list, result_days: set[str] | None = None) -> str:
    sid = suite.get("id", "")
    live = suite.get("status") == "live"
    label = _release_label(sid)
    buttons = []
    if sid in (result_days or set()):
        buttons.append(("Model results", f"../../leaderboard/?d={sid}", False))
    header = page_heading(label, actions='<div id="rail"></div>' + button_row(buttons),
                          attributes=f' data-suite-id="{esc(sid)}"')

    if suite_tasks:
        # Site-wide rollups have no evaluation date. A release page must not
        # present them as results for this historical release.
        has_languages = any(task.get("language") for task in suite_tasks)
        rows = []
        for task in suite_tasks:
            tid = task.get("id", "")
            href = f"../../registry/{tid}/" if safe_id(tid) else "../../registry/"
            checks = task.get("n_fail_to_pass")
            rows.append(
                td(f'<a class="{cls(LINK)}" data-task-id="{esc(tid)}" '
                   f'href="{esc(href)}">{esc(_task_title(task))}</a>',
                   prose=True, cell_class="tdb-detail-task")
                + td(_pr_link(task.get("repo"), task.get("pr_number")),
                     prose=True, cell_class="tdb-detail-project")
                + (td(esc(task.get("language")) if task.get("language") else DASH,
                      cell_class="tdb-detail-language") if has_languages else "")
                + td(esc(checks) if checks is not None else DASH, "right", "tabular-nums",
                     cell_class="tdb-detail-checks")
                + td(DASH, "right", cell_class="tdb-detail-score")
            )
        table = table_block(
            [("Task", "left", "tdb-detail-task"), ("Project", "left", "tdb-detail-project")]
            + ([("Language", "left", "tdb-detail-language")] if has_languages else [])
            + [("Target tests", "right", "tdb-detail-checks"), ("Observed passes", "right", "tdb-detail-score")],
            rows,
            catalogue=True,
        )
    else:
        table = '<div class="mb-6">' + empty("No tasks are published in this release.") + '</div>'

    return "\n".join([
        header,
        (f'<section class="tdb-release-digest" data-release-digest="{esc(sid)}" aria-live="polite"></section>'
         if re.fullmatch(r"\d{4}-\d{2}-\d{2}", sid) else ""),
        _section(sec_head("Tasks") + f'<div data-release-tasks="{esc(sid)}">{table}</div>'),
        f'<details class="tdb-methods tdb-evaluation-note"><summary>Run an evaluation</summary>{_evaluation_note(live)}</details>',
    ])


SUITE_SCRIPT = """(async function () {
  var T = window.TDB;
  if (T.redirecting) return;
  var site = await T.getJSON("site_data.json").catch(T.fetchFailed("the task catalogue"));
  if (site && site.suites) {
    T.dayRail(document.getElementById("rail"), site.suites, %s);
  }
})();"""


def task_page_body(task: dict, pkg: dict) -> str:
    """Describe the task first; keep tooling identifiers in links and data attributes."""
    tid = task.get("id", "")
    suites = task_suites(task)
    live = task.get("status") == "live"
    rec = (pkg or {}).get("record") or {}
    tom = (pkg or {}).get("toml") or {}
    instruction = (pkg or {}).get("instruction") or ""
    repo = task.get("repo") or rec.get("repo") or tom.get("source_repo")
    pr = task.get("pr_number") or rec.get("pr_number") or tom.get("pr_number")
    title = _task_title(task, pkg)
    f2p = rec.get("fail_to_pass") or []
    n_f2p = task.get("n_fail_to_pass")
    if n_f2p is None and f2p:
        n_f2p = len(f2p)
    language = task.get("language") or rec.get("language")
    # Estimated difficulty is the author's label, never a measured result.
    difficulty = task.get("declared_difficulty") or tom.get("difficulty") or ""
    case = TASK_CASES.get(tid)
    summary = case["goal"] if case else (pkg.get("summary") or task_summary(instruction))
    if summary.rstrip(".") == instruction_excerpt(title).rstrip("."):
        summary = ""

    buttons = []
    if repo and pr:
        buttons.append(("Original change", f"https://github.com/{repo}/pull/{pr}", False))
    buttons.append(("Submit results", "../../submit/", False))
    header = page_heading(title, actions=button_row(buttons),
                          attributes=f' data-task-id="{esc(tid)}"')

    release_links = [
        f'<a class="{cls(LINK)}" href="../../benchmarks/{esc(sid)}/">'
        f'{esc(_release_label(sid).removesuffix(" release"))}</a>'
        for sid in suites if safe_id(sid)
    ]
    facts = [
        ("Project", _pr_link(repo, pr) if repo else None),
        ("Language", esc(language) if language else None),
        ("Estimated difficulty", esc(difficulty) if difficulty else None),
        ("Target tests", esc(n_f2p) if n_f2p is not None else None),
        ("Releases", '<span class="tdb-task-releases">' + ", ".join(release_links) + '</span>' if release_links else None),
        ("License", esc(rec.get("source_license_spdx")) if rec.get("source_license_spdx") else None),
    ]
    fact_rows = [
        f'<th scope="row" data-slot="table-head" class="{cls(TH)}">{esc(key)}</th>' + td(value)
        for key, value in facts if value is not None
    ]
    fact_table = (
        '<div class="tdb-task-facts mb-6 flex flex-col">'
        '<div class="tdb-table-shell bg-card border-y md:border-x">'
        '<div data-slot="table-container" class="relative w-full overflow-x-auto">'
        f'<table data-slot="table" class="{cls(TABLE + " tdb-facts-table")}" aria-label="About this task">'
        f'<tbody data-slot="table-body" class="{cls("[&_tr:last-child]:border-0")}">'
        + "".join(f'<tr data-slot="table-row" class="{cls(TR_BODY)}">{row}</tr>' for row in fact_rows)
        + "</tbody></table></div></div></div>"
    )
    return "\n".join([
        header,
        _section(sec_head("About this task")
                 + (f'<p class="tdb-task-summary">{esc(summary)}</p>' if summary else "")
                 + (f'<p class="tdb-task-success"><strong>Success criterion:</strong> {esc(case["success"])}</p>' if case else
                    (f'<p class="tdb-task-success"><strong>Success criterion:</strong> Pass the {esc(n_f2p)} target regression '
                     f'{"test" if n_f2p == 1 else "tests"} without editing the test files.</p>' if n_f2p else
                     '<p class="tdb-task-success"><strong>Success criterion:</strong> Make the project regression tests pass without editing the test files.</p>'))
                 + fact_table),
        f'<section class="tdb-run-details" id="model-outcomes" data-task-runs="{esc(tid)}"></section>',
        f'<details class="tdb-methods tdb-evaluation-note"><summary>Run an evaluation</summary>{_evaluation_note(live)}</details>',
    ])


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
    ap.add_argument("--detail-data", help="metadata-only task detail mapping (default: docs/data/task-details.json when present)")
    args = ap.parse_args(argv)

    docs = Path(args.docs).resolve()
    detail_path = Path(args.detail_data).resolve() if args.detail_data else docs / "data" / "task-details.json"
    try:
        detail_packages = load_detail_data(detail_path) if args.detail_data or detail_path.is_file() else {}
    except (OSError, ValueError) as error:
        print(f"Invalid task detail data: {error}", file=sys.stderr)
        return 1
    registry = read_json(RELEASE / "registry.json", {}) or {}
    site = read_json(docs / "site_data.json")
    if site is None:
        print(f"note: {docs / 'site_data.json'} not found - falling back to registry.json")
        site = {}

    suites, tasks = collect(site, registry)
    homepage = docs / "index.html"
    if homepage.is_file() and not args.suites_only:
        home = homepage.read_text(encoding="utf-8")
        updated = re.sub(
            r"<!-- TDB_CASES_START -->.*?<!-- TDB_CASES_END -->",
            lambda _: "<!-- TDB_CASES_START -->\n" + case_cards(tasks) + "\n<!-- TDB_CASES_END -->",
            home, flags=re.S,
        )
        if updated != home:
            write_page(homepage, updated)
    by_suite = index_tasks_by_suite(tasks)
    day_index = read_json(docs / "data" / "index.json", {}) or {}
    result_days = {
        day for day in day_index.get("days", [])
        if isinstance(day, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", day)
    }

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
                title=f"{_release_label(sid)} · Terminal-Daily",
                description=(
                    f"{_release_label(sid)}: "
                    f"{s.get('n_tasks', len(st))} software tasks from merged public code changes."
                ),
                page_key="benchmarks",
                depth=2,
                body=suite_page_body(s, st, result_days),
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
            pkg = load_task_package(tid) or detail_packages.get(tid, {})
            html = render_page(
                title=f"{_task_title(t, pkg)} · Terminal-Daily",
                description=(
                    f"{_task_title(t, pkg)}. A software maintenance task from a public code change."
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

    # Generated pages get ASSET_V by construction; the hand-written ones carry a
    # literal that would now be stale. Stamping them here means one command
    # leaves the whole site consistent -- the alternative is remembering a
    # second command, which is exactly how the token went stale the first time.
    from asset_version import current as _v, stamp as _stamp   # noqa: PLC0415
    token = _v()
    changed = _stamp(token)
    print(f"assets @ {token}: {changed} page(s) restamped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
