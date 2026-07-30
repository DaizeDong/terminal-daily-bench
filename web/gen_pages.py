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

Both live two directories below the site root, so every generated page uses the
same shell:  ../../assets/site.css  +  ../../assets/site.js  data-root="../.."

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
    pill(text, kind="")         <span class="pill [kind]">   kind: pass|pending|lang
    status_pill(status)         archive -> pass pill, live -> pending pill
    tags(*pills)                <div class="tags"> wrapper
    strip(pairs)                the .strip stat band, from [(label, value), ...]
    sec_head(title, eyebrow="", more=None)   the .sec-head row
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


def pill(text, kind: str = "") -> str:
    cls = "pill" + (" " + kind if kind else "")
    return f'<span class="{cls}">{esc(text)}</span>'


def status_pill(status: str) -> str:
    """archive = released in full (pass) · live = withheld, server-side (pending)."""
    return pill(status or "unknown", "pending" if status == "live" else "pass")


def tags(*items) -> str:
    inner = "".join(i for i in items if i)
    return f'<div class="tags">{inner}</div>' if inner else ""


def strip(pairs) -> str:
    cells = "".join(
        f'<div class="cell"><div class="k">{esc(k)}</div><div class="v">{v}</div></div>'
        for k, v in pairs
    )
    return f'<div class="strip">{cells}</div>'


def sec_head(title, eyebrow: str = "", more=None) -> str:
    out = [f'<div class="sec-head"><h2>{esc(title)}</h2>']
    if eyebrow:
        out.append(f'<span class="eyebrow">{esc(eyebrow)}</span>')
    if more:
        href, label = more
        out.append(f'<a class="more" href="{esc(href)}">{esc(label)} &rarr;</a>')
    out.append("</div>")
    return "".join(out)


def empty(msg_html: str) -> str:
    return f'<div class="empty">{msg_html}</div>'


FAVICON = (
    "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'>"
    "<text y='13' font-size='13'>&#9622;</text></svg>"
)


def render_page(title, description, page_key, depth, body, script="", head="") -> str:
    """The one shell every generated page uses.

    depth  -- directories below the site root (2 for benchmarks/<id>/ and
              registry/<id>/). Drives asset hrefs and data-root.
    body   -- HTML placed inside <main class="wrap">.
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
<link rel="stylesheet" href="{root}/assets/site.css">
<link rel="icon" href="{FAVICON}">
{head}</head>
<body>

<main class="wrap">
{body}
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
        return f'<a href="{esc(url)}">{esc(repo)}#{esc(pr_number)}</a>'
    if repo:
        return f'<a href="https://github.com/{esc(repo)}">{esc(repo)}</a>'
    return '<span class="dash">&mdash;</span>'


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
        '<section class="hero">',
        f'<p class="eyebrow">daily suite &middot; {esc(suite.get("status", ""))}</p>',
        f"<h1>suite {esc(sid)}</h1>",
        '<p class="sub">'
        + (
            "Gold patch and protected tests are withheld while this suite is live; "
            "submissions are scored server-side by re-laying the protected tests."
            if live
            else "Archived and released in full &mdash; environment, protected tests and the "
            "reference solution &mdash; so every number here can be reproduced locally."
        )
        + "</p>",
        '<div class="cta">',
        '<a class="btn" href="../">all suites</a>',
        '<a class="btn" href="../../leaderboard/">leaderboard</a>',
        '<a class="btn" href="../../registry/">task registry</a>',
        "</div>",
        "</section>",
    ]

    rail = '<section style="padding-top:0;border-top:none"><div id="rail"></div></section>'

    stats = strip(
        [
            ("tasks", n_tasks),
            ("languages", len(langs) or "&mdash;"),
            ("fail-to-pass tests", f2p or "&mdash;"),
            ("solved by ≥ 1 model", solved_any),
            ("false-accepts", 0),
        ]
    )

    if suite_tasks:
        rows = []
        for t in suite_tasks:
            tid = t.get("id", "")
            href = f"../../registry/{tid}/" if safe_id(tid) else "../../registry/"
            solved = t.get("solved_by")
            n_models = t.get("n_models")
            if solved is None or not n_models:
                cell = '<span class="dash">&mdash;</span>'
            else:
                cls = "pass" if solved else ""
                cell = f'<span class="pill {cls}">{esc(solved)}/{esc(n_models)}</span>'
            rows.append(
                "<tr>"
                f'<td><a class="mono" href="{esc(href)}">{esc(tid)}</a></td>'
                f"<td>{esc(t.get('title') or '')}</td>"
                f"<td>{_pr_link(t.get('repo'), t.get('pr_number'))}</td>"
                f"<td>{pill(t.get('language'), 'lang') if t.get('language') else ''}</td>"
                f"<td>{pill(t.get('difficulty')) if t.get('difficulty') else ''}</td>"
                f'<td class="num">{esc(t.get("n_fail_to_pass") or 0)}</td>'
                f'<td class="num">{cell}</td>'
                "</tr>"
            )
        table = (
            '<div class="table-wrap"><table><thead><tr>'
            "<th>task</th><th>what it asks for</th><th>source pull request</th>"
            "<th>language</th><th>difficulty</th>"
            '<th class="num">f2p tests</th><th class="num">solved by</th>'
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
        )
    else:
        table = empty(
            "This suite has no published task list. Live suites expose their tasks only "
            "through the scoring endpoint until they are archived."
        )

    lang_tags = tags(*[pill(l, "lang") for l in langs]) if langs else ""

    body = [
        "\n".join(head),
        rail,
        "<section>",
        sec_head("tasks in this suite", suite.get("note") or "", (("../../registry/"), "all tasks")),
        stats,
        f'<div style="margin-top:14px">{table}</div>',
        (f'<div style="margin-top:12px">{lang_tags}</div>' if lang_tags else ""),
        "</section>",
        "<section>",
        sec_head("how this suite is scored", "execution proof only"),
        '<p class="lead">A patch is applied to a throwaway copy of the workspace. The workspace tests '
        "are discarded, the protected tests are re-laid from the trusted package, and they run with "
        "the network cut. The reward is that run's outcome and nothing else, so "
        '<span class="mono">false_accept = 0</span> holds by construction.</p>',
        "<pre>"
        + (
            "<span class=\"c\"># live suite: run your model, then submit the patch</span>\n"
            "<span class=\"k\">tdb</span> submit &lt;RESULTS.jsonl&gt;   <span class=\"c\"># re-scored by the same gate on ingest</span>"
            if live
            else "<span class=\"c\"># archived suite: everything needed to reproduce ships with it</span>\n"
            f"<span class=\"k\">tdb</span> run    &lt;MODEL&gt; tasks/archive/&lt;task-id&gt;\n"
            "<span class=\"k\">tdb</span> oracle tasks/archive/&lt;task-id&gt;   <span class=\"c\"># gate baseline &rarr; reward 1.0</span>"
        )
        + "</pre>",
        "</section>",
    ]
    return "\n".join(b for b in body if b)


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

    head = [
        '<section class="hero">',
        f'<p class="eyebrow">task &middot; suite {esc(suite)} &middot; {esc(task.get("status", ""))}</p>',
        f"<h1>{esc(title or tid)}</h1>",
        f'<p class="sub mono">{esc(tid)}</p>',
        '<div class="cta">',
        (f'<a class="btn" href="../../benchmarks/{esc(suite)}/">suite {esc(suite)}</a>' if safe_id(suite) else ""),
        '<a class="btn" href="../">all tasks</a>',
        (
            f'<a class="btn" href="https://github.com/{esc(repo)}/pull/{esc(pr)}">source pull request</a>'
            if repo and pr
            else ""
        ),
        "</div>",
        "</section>",
    ]

    solved, n_models = task.get("solved_by"), task.get("n_models")
    stats = strip(
        [
            ("language", esc(task.get("language") or rec.get("language") or "&mdash;")),
            ("difficulty", esc(task.get("difficulty") or tom.get("difficulty") or "&mdash;")),
            ("fail-to-pass tests", n_f2p if n_f2p else "&mdash;"),
            (
                "solved by",
                f"{solved}/{n_models}" if solved is not None and n_models else "&mdash;",
            ),
            ("false-accepts", 0),
        ]
    )

    facts = [
        ("task id", f'<span class="mono">{esc(tid)}</span>'),
        ("suite", f'<a class="mono" href="../../benchmarks/{esc(suite)}/">{esc(suite)}</a>'
                  if safe_id(suite) else esc(suite)),
        ("status", status_pill(task.get("status", ""))),
        ("source", _pr_link(repo, pr)),
        ("base commit", f'<span class="mono">{esc(rec.get("base_sha", ""))}</span>' if rec.get("base_sha") else None),
        ("merge commit", f'<span class="mono">{esc(rec.get("merge_sha", ""))}</span>' if rec.get("merge_sha") else None),
        ("network at run time", esc(rec.get("network_profile") or "run-offline")),
        ("upstream license", esc(rec.get("source_license_spdx") or "see source repository")),
    ]
    fact_rows = "".join(
        f"<tr><th>{esc(k)}</th><td>{v}</td></tr>" for k, v in facts if v
    )
    fact_table = f'<div class="table-wrap"><table><tbody>{fact_rows}</tbody></table></div>'

    if instruction:
        brief = (
            "<section>"
            + sec_head("what the agent is asked to do", "the instruction it sees")
            + f'<div class="prose"><p>{esc(instruction_excerpt(instruction))}</p></div>'
            + "</section>"
        )
    else:
        brief = ""

    if f2p and not live:
        items = "".join(f"<li><span class=\"mono\">{esc(x)}</span></li>" for x in f2p)
        f2p_block = (
            "<section>"
            + sec_head("fail-to-pass tests", "must fail before the patch, pass after")
            + f'<div class="prose"><ul>{items}</ul></div>'
            + "</section>"
        )
    elif live:
        f2p_block = (
            "<section>"
            + sec_head("protected tests", "withheld while the suite is live")
            + empty(
                "This task is in a live suite: the protected test bodies and the reference solution "
                "are withheld. Only the failing-test identifiers are exposed to the agent, and "
                "scoring happens server-side. The package is released in full when the suite is "
                "archived, two weeks after it was sealed."
            )
            + "</section>"
        )
    else:
        f2p_block = ""

    run = (
        "<section>"
        + sec_head("reproduce it", "archived tasks ship complete" if not live else "live task")
        + (
            "<pre><span class=\"c\"># the whole package ships with the archived suite</span>\n"
            f"<span class=\"k\">tdb</span> run    &lt;MODEL&gt; tasks/archive/{esc(tid)}\n"
            f"<span class=\"k\">tdb</span> oracle tasks/archive/{esc(tid)}   <span class=\"c\"># gate baseline &rarr; reward 1.0</span></pre>"
            if not live
            else "<pre><span class=\"c\"># live task: run your model, submit the patch, we score it</span>\n"
            "<span class=\"k\">tdb</span> submit &lt;RESULTS.jsonl&gt;</pre>"
        )
        + '<p class="lead" style="margin-top:12px">The reward is the outcome of the re-laid protected '
        "tests, nothing else. A submitted reward is advisory and is replayed on ingest. "
        '<a href="../../submit/">how to submit &rarr;</a></p>'
        + "</section>"
    )

    body = [
        "\n".join(h for h in head if h),
        "<section>" + sec_head("provenance", "mined from a real merged pull request") + stats
        + f'<div style="margin-top:14px">{fact_table}</div>' + "</section>",
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
