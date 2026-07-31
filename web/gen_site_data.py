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
    suite_of_task = {}
    for member_file in sorted((release / "tasks").glob(".suite-*.json")):
        sid = member_file.name[len(".suite-"):-len(".json")]
        for m in (_read_json(member_file) or []):
            if isinstance(m, dict) and m.get("task"):
                suite_of_task[str(m["task"])] = sid

    # Fallback for packages that predate membership files: only a suite that
    # DECLARES a path owns that split wholesale. The shipped samples do
    # (path: tasks/archive, tasks/live); a dated suite does not, so it cannot
    # absorb the samples the way keying on status alone made it.
    suite_of = {}
    for s_ in reg0.get("suites") or []:
        path = str(s_.get("path") or "")
        if path:
            suite_of.setdefault(path.rstrip("/").rsplit("/", 1)[-1], str(s_.get("id")))

    tasks, suites_langs = [], {}
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
            suite = (suite_of_task.get(d.name)
                     or suite_of.get(status)
                     or str(rec.get("date") or board.get("date") or status))
            sb = solved_by.get(d.name)
            tasks.append({
                "id": d.name, "suite": suite, "status": status,
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
                suites_langs.setdefault(suite, set()).add(lang)

    # suites: registry declarations, enriched with what actually shipped
    reg = _read_json(release / "registry.json")
    suite_rows = {}
    for s in reg.get("suites") or []:
        suite_rows[str(s.get("id"))] = {
            "id": str(s.get("id")), "status": s.get("status") or "archive",
            "n_tasks": s.get("n_tasks"), "note": s.get("note") or "",
            "languages": sorted(suites_langs.get(str(s.get("id")), [])),
        }
    for t in tasks:  # a suite present on disk but absent from registry.json still shows up
        sid = t["suite"]
        if sid not in suite_rows:
            suite_rows[sid] = {"id": sid, "status": t["status"], "n_tasks": 0, "note": "",
                               "languages": sorted(suites_langs.get(sid, []))}
    for sid, s in suite_rows.items():
        on_disk = sum(1 for t in tasks if t["suite"] == sid)
        if on_disk:
            s["n_tasks"] = on_disk

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
            keep["also_in"] = sorted(set(keep.get("also_in", []) + other.get("also_in", []) + [other["status"]]))
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
