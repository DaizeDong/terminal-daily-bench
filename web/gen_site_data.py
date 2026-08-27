#!/usr/bin/env python3
"""Build docs/site_data.json -- the catalogue the site's suite and task pages render from.

The leaderboard renders a trusted relative-capability report from
`leaderboard_data.json`. This file is the other half: WHAT the benchmark
contains -- the daily suites and every task's provenance. Both are plain JSON
at the site root, so publishing a day stays "regenerate, commit, push".

    gen_site_data.py [--release DIR] [--out DIR/site_data.json]

Reads (all optional, degrades to whatever exists):
    <release>/registry.json          suite declarations
    <release>/tasks/{archive,live}/  the shipped task packages
    <release>/docs/leaderboard_data.json   optional formal v3 report + task matrix

Emits:
    { generated, scoring, suites: [{id, status, n_tasks, languages, note}],
      tasks:  [{id, suite, status, repo, pr_number, base_sha, merge_sha, license,
                language, title, difficulty, declared_difficulty, n_fail_to_pass,
                solved_by, n_models}] }

``difficulty`` is MEASURED and stays gated on scoring authority (it is "" while
unranked). ``declared_difficulty`` is the EDITORIAL label the task author wrote
into ``task.toml``; it carries no model performance and is therefore ungated.

Task packages carry no secrets (publish_tasks.py sanitises them). Per-task
difficulty is derived only when a trusted, publishable 50-task v3 report binds
the accompanying matrix. Historical/fixture matrices never mint public scores.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover -- py<3.11
    import tomli as tomllib

_LANG_BY_EXT = {".py": "python", ".rs": "rust", ".go": "go", ".js": "javascript",
                ".ts": "typescript", ".rb": "ruby", ".java": "java",
                ".cpp": "c++", ".cc": "c++", ".c": "c", ".h": "c++"}

RELATIVE_SCHEMA = "td-relative-capability-v3"
FORMAL_TASK_TARGET = 50
PUBLICATION_BUNDLE_SCHEMA = "td-relative-publication-bundle-v1"
TASK_ID_ROSTER_SCHEMA = "td-frozen-task-roster-v1"
PUBLICATION_REGISTRY_MODE = "code-controlled-allowlist"
# There is no independent production publication registry yet. Adding an
# authority digest here is an explicit reviewed code change; a JSON artifact
# cannot approve itself by changing its own booleans or embedded hashes.
APPROVED_PUBLICATION_BUNDLE_SHA256S: frozenset[str] = frozenset()
ANTI_CHEAT_DEPLOYMENT_ACTIVE = False


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- a missing/odd file just means fewer fields
        return {}


def canonical_sha256(value) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256(value) -> str | None:
    if (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    ):
        return value
    return None


def _task_id_roster_sha256(tasks: list[str]) -> str:
    return canonical_sha256({
        "schema_version": TASK_ID_ROSTER_SCHEMA,
        "tasks": sorted(tasks),
    })


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


def _declared_difficulty(task_dir: Path) -> str:
    """The EDITORIAL difficulty the task author recorded in task.toml.

    Deliberately not routed through _difficulty(): that one is MEASURED and is
    gated on scoring authority, which is why site_data.json ships '' on all 61
    tasks today while the pages generated from it render 43 hard / 18 medium
    (gen_pages.py falls back to this same scalar). site_data.json is strictly
    lossier than its own output; this closes that gap. task.toml is the only
    source that covers live tasks -- record.json exists for 37 of 61.
    """
    f = task_dir / "task.toml"
    if not f.exists():
        return ""
    try:
        doc = tomllib.loads(f.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001 -- a malformed package is not a difficulty
        return ""
    value = ((doc.get("metadata") or {}).get("difficulty") or "")
    return str(value).strip().lower()


def relative_report(board: dict) -> dict:
    """Return a v3 report from either the document root or its public wrapper."""
    if not isinstance(board, dict):
        return {}
    candidates = (
        board,
        board.get("relative_capability"),
        board.get("relative_scoring"),
    )
    for candidate in candidates:
        if (
            isinstance(candidate, dict)
            and candidate.get("schema_version") == RELATIVE_SCHEMA
        ):
            return candidate
    return {}


def _publishable_overall_models(report: dict) -> list[dict]:
    for axis in report.get("axes") or []:
        if not isinstance(axis, dict) or axis.get("axis") != "overall":
            continue
        entities = axis.get("entities") or {}
        model_table = entities.get("model") if isinstance(entities, dict) else {}
        return [
            row
            for row in (model_table or {}).get("ratings") or []
            if isinstance(row, dict)
            and row.get("publishable") is True
            and type(row.get("relative_score")) in (int, float)
            and isinstance(row.get("ci"), list)
            and len(row["ci"]) == 2
            and all(type(value) in (int, float) for value in row["ci"])
        ]
    return []


def _matrix_shape(board: dict) -> dict:
    """Return a strictly binary exactly-50 matrix, or an empty object."""
    matrix = board.get("matrix") if isinstance(board, dict) else None
    if not isinstance(matrix, dict):
        return {}
    tasks = matrix.get("tasks")
    rows = matrix.get("rows")
    if (
        not isinstance(tasks, list)
        or len(tasks) != FORMAL_TASK_TARGET
        or not all(
            isinstance(task, str) and task and task == task.strip()
            for task in tasks
        )
        or len(set(tasks)) != FORMAL_TASK_TARGET
        or not isinstance(rows, list)
        or not rows
    ):
        return {}
    seen_models: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            return {}
        model = row.get("model")
        outcomes = row.get("g")
        if (
            not isinstance(model, str)
            or not model.strip()
            or model != model.strip()
            or model in seen_models
            or not isinstance(outcomes, list)
            or len(outcomes) != FORMAL_TASK_TARGET
            or not all(type(value) is int and value in (0, 1) for value in outcomes)
        ):
            return {}
        seen_models.add(model)
    return matrix


def _publication_audit(board: dict, report: dict) -> dict:
    authority = board.get("publication_authority") if isinstance(board, dict) else None
    if not isinstance(authority, dict):
        authority = {}
    try:
        authority_sha256 = canonical_sha256(authority) if authority else None
        report_sha256 = canonical_sha256(report) if report else None
    except (TypeError, ValueError):
        authority_sha256 = None
        report_sha256 = None
    matrix = _matrix_shape(board)
    try:
        matrix_sha256 = canonical_sha256(matrix) if matrix else None
    except (TypeError, ValueError):
        matrix_sha256 = None
    tasks = matrix.get("tasks") if matrix else None
    matrix_task_roster_sha256 = (
        _task_id_roster_sha256(tasks) if isinstance(tasks, list) else None
    )
    report_input = report.get("input") if isinstance(report.get("input"), dict) else {}
    schema_valid = authority.get("schema_version") == PUBLICATION_BUNDLE_SCHEMA
    report_digest_matches = (
        report_sha256 is not None
        and _sha256(authority.get("relative_report_sha256")) == report_sha256
    )
    matrix_digest_matches = (
        matrix_sha256 is not None
        and _sha256(authority.get("matrix_sha256")) == matrix_sha256
    )
    matrix_roster_matches = (
        matrix_task_roster_sha256 is not None
        and _sha256(authority.get("matrix_task_id_roster_sha256"))
        == matrix_task_roster_sha256
        and _sha256(report_input.get("frozen_task_id_roster_sha256"))
        == matrix_task_roster_sha256
    )
    bundle_approved = (
        schema_valid
        and authority_sha256 is not None
        and authority_sha256 in APPROVED_PUBLICATION_BUNDLE_SHA256S
    )
    return {
        "publication_registry_mode": PUBLICATION_REGISTRY_MODE,
        "publication_bundle_sha256": authority_sha256,
        "publication_bundle_approved": bundle_approved,
        "relative_report_sha256": report_sha256,
        "relative_report_digest_matches": report_digest_matches,
        "matrix_sha256": matrix_sha256,
        "matrix_digest_matches": matrix_digest_matches,
        "matrix_task_id_roster_sha256": matrix_task_roster_sha256,
        "matrix_task_roster_digest_matches": matrix_roster_matches,
        "anti_cheat_deployment_active": ANTI_CHEAT_DEPLOYMENT_ACTIVE,
    }


def scoring_status(board: dict) -> dict:
    """Machine-readable status gated by code-controlled publication authority."""
    report = relative_report(board)
    report_input = report.get("input") if isinstance(report.get("input"), dict) else {}
    roster_n = report_input.get("frozen_task_roster_n")
    trusted_roster = report_input.get("task_roster_digest_trusted") is True
    trusted_manifest = report_input.get("cell_manifest_digest_trusted") is True
    full_roster_digest = _sha256(report_input.get("frozen_task_roster_sha256"))
    cell_manifest_digest = _sha256(report_input.get("cell_manifest_sha256"))
    publishable = _publishable_overall_models(report)
    publication = _publication_audit(board, report)
    official = (
        roster_n == FORMAL_TASK_TARGET
        and trusted_roster
        and trusted_manifest
        and full_roster_digest is not None
        and cell_manifest_digest is not None
        and bool(publishable)
        and publication["publication_bundle_approved"]
        and publication["relative_report_digest_matches"]
        and publication["anti_cheat_deployment_active"]
    )
    legacy_present = bool(
        isinstance(board, dict)
        and (board.get("leaderboard") or board.get("matrix"))
        and not official
    )
    if official:
        state = "published"
    elif report:
        state = "unranked-incomplete-or-untrusted"
    else:
        state = "awaiting-certified-50-task-results"
    return {
        "schema_version": "td-public-scoring-status-v1",
        "relative_schema": RELATIVE_SCHEMA,
        "formal_task_target": FORMAL_TASK_TARGET,
        "formal_roster_n": roster_n,
        "official_ranking": official,
        "state": state,
        "legacy_snapshot_present": legacy_present,
        "task_roster_digest_trusted": trusted_roster,
        "cell_manifest_digest_trusted": trusted_manifest,
        "publishable_overall_models": len(publishable),
        **publication,
    }


def _published_matrix(board: dict, status: dict) -> dict:
    """Admit only a code-approved matrix transitively bound to the v3 report."""
    if status.get("official_ranking") is not True:
        return {}
    if (
        status.get("matrix_digest_matches") is not True
        or status.get("matrix_task_roster_digest_matches") is not True
        or status.get("publication_bundle_approved") is not True
    ):
        return {}
    return _matrix_shape(board)


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
    # A legacy/fixture matrix remains useful as an input artifact, but never as
    # public score authority. Only the formal v3 + exactly-50 gate admits it.
    score_status = scoring_status(board)
    solved_by, n_models = {}, 0
    mx = _published_matrix(board, score_status)
    score_status["matrix_published"] = bool(mx)
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
                "declared_difficulty": _declared_difficulty(d),
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
            "difficulty": _difficulty(sb, n_models),          # MEASURED. gated.
            "declared_difficulty": package["declared_difficulty"],   # EDITORIAL. ungated.
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
        "scoring": score_status,
        "suites": sorted(suite_rows.values(), key=lambda s: str(s["id"])),
        "tasks": tasks,
    }


_UTC_SECOND = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def retain_generated_timestamp(existing, candidate: dict) -> dict:
    """Keep the build timestamp when the emitted catalogue is byte-stable.

    ``generated`` is publication metadata, not catalogue content. Re-running the
    generator over identical inputs must therefore preserve it; otherwise a
    no-op site build changes bytes every second and cannot be reproduced.
    """
    if not isinstance(candidate, dict):
        raise TypeError("candidate catalogue must be a dict")
    result = dict(candidate)
    if not isinstance(existing, dict):
        return result
    timestamp = existing.get("generated")
    if not isinstance(timestamp, str) or not _UTC_SECOND.fullmatch(timestamp):
        return result
    old_payload = {key: value for key, value in existing.items() if key != "generated"}
    new_payload = {key: value for key, value in result.items() if key != "generated"}
    if canonical_sha256(old_payload) == canonical_sha256(new_payload):
        result["generated"] = timestamp
    return result


def main() -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", default=str(here.parent))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    release = Path(a.release)
    out = Path(a.out) if a.out else release / "docs" / "site_data.json"
    board = _read_json(release / "docs" / "leaderboard_data.json")
    data = retain_generated_timestamp(_read_json(out), collect(release, board))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"site catalogue: {len(data['suites'])} suites, {len(data['tasks'])} tasks -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
