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
    expected = ["intro", "status", "leaderboard", "tasks"]
    if sections != expected:
        bad.append(f"index.html: data sections {sections} != {expected}")

    retired = (
        "how the universe is grown",
        "we measure the benchmark itself",
        "explore our benchmarks",
        "i want to test my agent",
    )
    lower_home = home.lower()
    for phrase in retired:
        if phrase in lower_home:
            bad.append(f"index.html: retired marketing panel returned: {phrase!r}")

    caveats = (
        "deterministic code",
        "claimed reward",
        "deployment egress canary is still pending",
        "unpublished patched harbor fork",
        "stock harbor 0.13.1 is insufficient",
        "completed gate decisions",
    )
    for phrase in caveats:
        if phrase not in lower_home:
            bad.append(f"index.html: integrity caveat missing {phrase!r}")

    for rel in ("index.html", "benchmarks/index.html", "leaderboard/index.html",
                "registry/index.html"):
        raw = source(rel)
        if "data-tdb-integrity" not in markup_only(raw):
            bad.append(f"{rel}: data-tdb-integrity marker missing")

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
    all_public_html = "\n".join(
        page.read_text(encoding="utf-8", errors="replace").lower()
        for page in DOCS.rglob("*.html")
    )
    for stale in (
        "re-scored on ingest",
        "node worker replays",
        "worker replays your patch",
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
    if ('hacks: measuredFa ? s.fa : null' not in leaderboard_html or
            'hacks_n: measuredFa ? s.fa_n : null' not in leaderboard_html or
            'esc(e.hacks) + "/" + esc(e.hacks_n)' not in leaderboard_html):
        bad.append("leaderboard/index.html: missing measured numerator/denominator FA mapping")
    if "protected-test replay alone is not evidence of zero" not in leaderboard_html:
        bad.append("leaderboard/index.html: semantic FA scope warning missing")

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
                   f'(suites: {", ".join(sorted(map(str, suites)))}) -- catalogue and scored '
                   "snapshot must be presented as separate artifacts")
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

    for group in (check_links(pages, all_ids), check_no_external(pages), check_site_css(),
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
