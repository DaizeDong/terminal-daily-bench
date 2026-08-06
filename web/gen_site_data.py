#!/usr/bin/env python3
"""Build docs/site_data.json -- the catalogue the site's suite and task pages render from.

The leaderboard renders from `leaderboard_data.json` (who solved what). This file is the
other half: WHAT the benchmark contains -- the daily suites and every task's provenance.
Both are plain JSON at the site root, so publishing a day stays "regenerate, commit, push".

    gen_site_data.py [--release DIR] [--out DIR/site_data.json]

Reads (all optional, degrades to whatever exists):
    <release>/registry.json          suite declarations
    <release>/tasks/{archive,live}/  the shipped task packages
    <release>/docs/leaderboard_data.json   per-task solve counts, to show difficulty

Emits:
    { generated, suites: [{id, status, n_tasks, languages, note}],
      tasks:  [{id, suite, status, repo, pr_number, base_sha, merge_sha, license,
                language, title, difficulty, n_fail_to_pass, solved_by, n_models}] }

Task packages carry no secrets (publish_tasks.py sanitises them), and nothing here reads a
reward: difficulty is derived from the already-published solve matrix.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
from pathlib import Path

_LANG_BY_EXT = {".py": "python", ".rs": "rust", ".go": "go", ".js": "javascript",
                ".ts": "typescript", ".rb": "ruby", ".java": "java",
                ".cpp": "c++", ".cc": "c++", ".c": "c", ".h": "c++"}


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- a missing/odd file just means fewer fields
        return {}


def _title_from_instruction(task_dir: Path) -> str:
    """First meaningful line of instruction.md, trimmed to a card-sized summary."""
    f = task_dir / "instruction.md"
    if not f.exists():
        return ""
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip().lstrip("#").strip()
        if s and not s.startswith(("<!--", "---")):
            return (s[:150] + "…") if len(s) > 150 else s
    return ""


def _language(record: dict, task_dir: Path) -> str:
    lang = (record.get("language") or "").lower()
    if lang:
        return lang
    counts: dict = {}
    for f in record.get("test_files") or []:
        ext = os.path.splitext(str(f))[1].lower()
        if ext in _LANG_BY_EXT:
            counts[_LANG_BY_EXT[ext]] = counts.get(_LANG_BY_EXT[ext], 0) + 1
    if counts:
        return max(counts, key=counts.get)
    toml = task_dir / "task.toml"
    if toml.exists():
        m = re.search(r'language\s*=\s*"([^"]+)"', toml.read_text(encoding="utf-8", errors="replace"))
        if m:
            return m.group(1).lower()
    return ""


def _difficulty(solved_by, n_models) -> str:
    """Difficulty as MEASURED, not guessed: how much of the field solved it."""
    if not n_models or solved_by is None:
        return ""
    r = solved_by / n_models
    if r == 0:
        return "unsolved"
    if r < 0.25:
        return "hard"
    if r < 0.6:
        return "medium"
    return "easy"


_DATED_SUITE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def primary_suite(suite_ids) -> str:
    """Return the compatibility ``suite`` without losing many-to-many membership.

    ISO-dated suites are ordered by date and take precedence over named fixture
    suites.  A carried task therefore points at the newest dated snapshot while
    its complete history remains in ``suites``.  Consumers must use ``suites``
    for membership tests; this scalar exists for older clients and sorting only.
    """
    ids = sorted({str(value) for value in suite_ids if value})
    dated = [sid for sid in ids if _DATED_SUITE.fullmatch(sid)]
    return (dated or ids)[-1] if ids else ""


def _add_membership(
    memberships_by_task: dict,
    task_ids_by_suite: dict,
    task_id: str,
    membership: dict,
) -> None:
    """Record one task/suite edge in both directions.

    The same package may be materialised in archive/ and live/ and may be
    carried through several dated suites.  Membership is therefore an edge,
    not a property that can be overwritten while scanning files.
    """
    sid = str(membership.get("suite") or "")
    if not task_id or not sid:
        return
    current = memberships_by_task.setdefault(task_id, {}).get(sid)
    if current is None:
        memberships_by_task[task_id][sid] = dict(membership, suite=sid)
    else:
        # A release gate reports duplicate/conflicting ledger rows.  Keeping the
        # first non-empty value here makes catalogue generation deterministic.
        for key, value in membership.items():
            if key not in current or current[key] in (None, ""):
                current[key] = value
    task_ids_by_suite.setdefault(sid, set()).add(task_id)


def collect(release: Path, board: dict) -> dict:
    # per-task solve counts from the published matrix (if a board has been published)
    solved_by, n_models = {}, board.get("n_models") or 0
    mx = board.get("matrix") or {}
    for i, tid in enumerate(mx.get("tasks") or []):
        solved_by[tid] = sum(int(bool(r["g"][i])) for r in mx.get("rows") or [] if i < len(r["g"]))
    if mx.get("rows"):
        n_models = len(mx["rows"])

    # which registry suite does each split belong to? (a task's suite is the suite it
    # SHIPPED in; the mine date is provenance, not a suite id)
    reg0 = _read_json(release / "registry.json")

    # Per-TASK membership, written by the emitter alongside the packages. Suites
    # share the archive/ and live/ directories, so attributing by split alone
    # gave whichever suite was declared first every task in that split: with 13
    # dated tasks published, registry.json said 13 and this catalogue said 4,
    # because `sample` (status=archive) had claimed all eleven archive packages.
    memberships_by_task: dict[str, dict[str, dict]] = {}
    task_ids_by_suite: dict[str, set[str]] = {}
    explicit_member_tasks: set[str] = set()
    for member_file in sorted((release / "tasks").glob(".suite-*.json")):
        sid = member_file.name[len(".suite-"):-len(".json")]
        members = _read_json(member_file)
        if not isinstance(members, list):
            continue
        for m in members:
            if isinstance(m, dict) and m.get("task"):
                tid = str(m["task"])
                window = m.get("suite_window") if isinstance(m.get("suite_window"), dict) else {}
                membership = {"suite": sid}
                if m.get("mode"):
                    membership["mode"] = str(m["mode"])
                for key in ("origin", "certified_date", "age_days",
                            "source_ledger", "selected_ledger_date"):
                    if key in window:
                        membership[key] = window[key]
                _add_membership(
                    memberships_by_task, task_ids_by_suite, tid, membership
                )
                explicit_member_tasks.add(tid)

    # Fallback for packages that predate membership files: only a suite that
    # DECLARES a path owns that split wholesale. The shipped samples do
    # (path: tasks/archive, tasks/live); a dated suite does not, so it cannot
    # absorb the samples the way keying on status alone made it.
    suite_of = {}
    for s_ in reg0.get("suites") or []:
        path = str(s_.get("path") or "")
        if path:
            suite_of.setdefault(path.rstrip("/").rsplit("/", 1)[-1], str(s_.get("id")))

    # Read package copies first, then add fallback edges.  This two-pass shape is
    # load-bearing: a legacy sample task can exist in BOTH archive/ and live/.
    # Adding archive's fallback and immediately treating it as an explicit edge
    # would otherwise prevent the live fallback from ever being recorded.
    package_rows = []
    for status in ("archive", "live"):
        root = release / "tasks" / status
        if not root.is_dir():
            continue
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            rec = _read_json(d / "record.json")
            prov = _read_json(d / "PROVENANCE.json")
            failing = _read_json(d / "FAILING_TESTS.json")
            f2p = rec.get("fail_to_pass") or failing.get("failing_test_ids") or []
            lang = _language(rec, d)
            package_rows.append({
                "status": status, "dir": d, "record": rec, "provenance": prov,
                "f2p": f2p, "language": lang,
            })

    for package in package_rows:
        d, status, rec = package["dir"], package["status"], package["record"]
        if d.name in explicit_member_tasks:
            continue
        fallback = (suite_of.get(status)
                    or str(rec.get("date") or board.get("date") or status))
        _add_membership(
            memberships_by_task,
            task_ids_by_suite,
            d.name,
            {"suite": fallback, "mode": status},
        )

    tasks, suites_langs = [], {}
    for package in package_rows:
        status = package["status"]
        d = package["dir"]
        rec = package["record"]
        prov = package["provenance"]
        f2p = package["f2p"]
        lang = package["language"]
        memberships = sorted(
            memberships_by_task.get(d.name, {}).values(),
            key=lambda item: str(item["suite"]),
        )
        suite_ids = [str(item["suite"]) for item in memberships]
        # Backward-compatible primary suite for old consumers. Membership is
        # many-to-many; pages and release gates consume ``suites`` below.
        suite = primary_suite(suite_ids)
        sb = solved_by.get(d.name)
        tasks.append({
            "id": d.name, "suite": suite, "status": status,
            "suites": suite_ids,
            "suite_memberships": memberships,
            "repo": rec.get("repo") or prov.get("source_repo") or "",
            "pr_number": rec.get("pr_number"),
            "base_sha": rec.get("base_sha") or prov.get("source_ref") or "",
            "merge_sha": rec.get("merge_sha") or "",
            "license": rec.get("source_license_spdx") or prov.get("source_license_spdx") or "",
            "language": lang,
            "title": _title_from_instruction(d),
            "n_fail_to_pass": len(f2p) if isinstance(f2p, list) else None,
            "solved_by": sb, "n_models": n_models if sb is not None else None,
            "difficulty": _difficulty(sb, n_models),
        })
        if lang:
            for sid in suite_ids:
                suites_langs.setdefault(sid, set()).add(lang)

    # suites: registry declarations, enriched with what actually shipped
    reg = _read_json(release / "registry.json")
    suite_rows = {}
    for s in reg.get("suites") or []:
        sid = str(s.get("id"))
        suite_rows[sid] = {
            "id": str(s.get("id")), "status": s.get("status") or "archive",
            "n_tasks": s.get("n_tasks"), "note": s.get("note") or "",
            "languages": sorted(suites_langs.get(sid, [])),
            "task_ids": sorted(task_ids_by_suite.get(sid, set())),
        }
        for key in ("target_tasks", "complete", "publish_shortfall"):
            if key in s:
                suite_rows[sid][key] = s[key]
    for sid in sorted(task_ids_by_suite):  # membership present but registry absent
        if sid not in suite_rows:
            modes = {
                membership.get("mode")
                for per_suite in memberships_by_task.values()
                for membership in per_suite.values()
                if membership.get("suite") == sid
            }
            suite_rows[sid] = {
                "id": sid, "status": "live" if "live" in modes else "archive",
                "n_tasks": len(task_ids_by_suite[sid]), "note": "",
                "languages": sorted(suites_langs.get(sid, [])),
                "task_ids": sorted(task_ids_by_suite[sid]),
            }
    for sid, s in suite_rows.items():
        task_ids = sorted(task_ids_by_suite.get(sid, set()))
        s["task_ids"] = task_ids
        s["catalogued_tasks"] = len(task_ids)
        if s.get("n_tasks") is None:
            s["n_tasks"] = len(task_ids)
        origins = [
            membership.get("origin")
            for per_suite in memberships_by_task.values()
            for membership in per_suite.values()
            if membership.get("suite") == sid
        ]
        s["fresh_tasks"] = origins.count("fresh")
        s["carried_tasks"] = origins.count("carried")
        s["unknown_origin_tasks"] = len(task_ids) - s["fresh_tasks"] - s["carried_tasks"]

    # one page per task id: prefer the archive record (it carries the full metadata) and
    # record the other splits the same task also ships in.
    task_by_id = {}
    for t in tasks:
        prev = task_by_id.get(t["id"])
        if prev is None:
            t["also_in"] = []
            task_by_id[t["id"]] = t
        else:
            keep, other = (prev, t) if prev["status"] == "archive" else (t, prev)
            keep["also_in"] = sorted(set(
                keep.get("also_in", []) + other.get("also_in", []) + [other["status"]]
            ) - {keep["status"]})
            merged_memberships = {
                str(item["suite"]): item
                for item in (keep.get("suite_memberships", [])
                             + other.get("suite_memberships", []))
                if item.get("suite")
            }
            keep["suite_memberships"] = [
                merged_memberships[sid] for sid in sorted(merged_memberships)
            ]
            keep["suites"] = sorted(merged_memberships)
            keep["suite"] = primary_suite(keep["suites"])
            task_by_id[t["id"]] = keep
    tasks = sorted(task_by_id.values(), key=lambda t: (t["suite"], t["id"]))

    return {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "suites": sorted(suite_rows.values(), key=lambda s: str(s["id"])),
        "tasks": tasks,
    }


def main() -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", default=str(here.parent))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    release = Path(a.release)
    out = Path(a.out) if a.out else release / "docs" / "site_data.json"
    board = _read_json(release / "docs" / "leaderboard_data.json")
    data = collect(release, board)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"site catalogue: {len(data['suites'])} suites, {len(data['tasks'])} tasks -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
