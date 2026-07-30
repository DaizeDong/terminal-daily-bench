#!/usr/bin/env python3
"""Community result submission + un-gameable ingest for the Terminal Daily leaderboard.

A community member runs the day's task set with their own model/scaffold; the harness
POSTs one submission record per (model, task) cell here. The IRON discipline: a
submitted ``reward_claimed`` is ADVISORY ONLY. Nothing a submitter sends is ever read
as a score — only ``verified_reward``, written by a replay of the submitted PATCH
through the execution gate, counts toward any rate.

STATE OF THE REPLAY WORKER — read this before quoting any property of this module.
The worker is NOT RUNNING. ``apply_verified`` is the only function that can promote a
row, and nothing in this repository calls it. The consequence is not a hole, it is the
opposite: every submission stays ``pending`` forever, and ``rebuild_leaderboard``
counts a pending row as zero solved out of one attempt. A third party therefore cannot
raise their number by submitting anything — verified or forged. What they also cannot
do, today, is raise it at all. Do not describe ingest re-scoring in the present tense
until a worker exists and this paragraph is deleted.

Flow:
  1. ``validate(sub)``  — schema + required fields + patch present.
  2. ``record(sub)``    — append to submissions.jsonl as ``verify_status="pending"``.
  3. re-score           — NOT IMPLEMENTED. When built, a node worker replays
                          ``sub['patch']`` via the gate (needs apptainer) and writes
                          back ``verified_reward`` + ``verify_status="verified"``.
  4. ``rebuild_leaderboard`` — fold verified submissions into leaderboard_data.json.

CLI:
  python submit_result.py validate  < submission.json
  python submit_result.py record    < submission.json   [--store DIR]
  python submit_result.py rebuild    --store DIR --out leaderboard_data.json
"""
from __future__ import annotations

import json
import sys
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

REQUIRED = ("date", "submitter", "model", "scaffold", "task", "patch")
STORE_DEFAULT = "community_submissions"


def validate(sub: Dict[str, Any]) -> List[str]:
    """Return a list of problems ([] = valid). Structural only; trust nothing semantic."""
    errs: List[str] = []
    for k in REQUIRED:
        if not sub.get(k):
            errs.append(f"missing required field: {k}")
    if sub.get("patch") and not isinstance(sub["patch"], str):
        errs.append("patch must be a unified-diff string")
    if not str(sub.get("task", "")).startswith("td-"):
        errs.append("task must be a Terminal Daily task id (td-...)")
    # reward_claimed is advisory; it is NOT validated against anything — it is
    # overwritten by the re-scored verified_reward on ingest.
    return errs


def content_id(sub: Dict[str, Any]) -> str:
    """Content-addressed id of the submission (dedup + tamper-evidence)."""
    canon = json.dumps(
        {k: sub.get(k) for k in REQUIRED}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


def record(sub: Dict[str, Any], store: str = STORE_DEFAULT) -> Dict[str, Any]:
    """Validate + append a submission as PENDING re-verification. Never trusts the score."""
    errs = validate(sub)
    if errs:
        raise ValueError("invalid submission: " + "; ".join(errs))
    entry = {
        "id": content_id(sub),
        "date": sub["date"], "submitter": sub["submitter"],
        "model": sub["model"], "scaffold": sub["scaffold"], "task": sub["task"],
        "reward_claimed": sub.get("reward_claimed"),   # advisory only
        "verify_status": "pending",                    # until a node re-scores the patch
        "verified_reward": None,                       # the ONLY figure the board trusts
        # NOT a measured 0. false_accept is a property of a GATE DECISION, and a pending
        # row has had no decision made about it -- writing 0 here would let an aggregate
        # report "0 false accepts" over rows nothing ever adjudicated. It becomes a
        # number when the replay worker adjudicates the patch, and not before.
        "false_accept": None,
    }
    p = Path(store) / f"{sub['date']}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def apply_verified(store: str, sub_id: str, verified_reward: float) -> None:
    """A node worker calls this after replaying the patch through the gate."""
    for p in Path(store).glob("*.jsonl"):
        lines = p.read_text(encoding="utf-8").splitlines()
        changed = False
        for i, ln in enumerate(lines):
            e = json.loads(ln)
            if e.get("id") == sub_id:
                e["verified_reward"] = float(verified_reward)
                e["verify_status"] = "verified"
                lines[i] = json.dumps(e, sort_keys=True)
                changed = True
        if changed:
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def rebuild_leaderboard(store: str, out: str) -> Dict[str, Any]:
    """Fold VERIFIED community submissions into the leaderboard's community section.

    Only ``verify_status=="verified"`` entries contribute a solved/attempt; a pending
    submission is listed but contributes 0 to any rate (its number is not yet trusted).

    ``false_accept`` aggregates over VERIFIED rows only, and stays ``None`` when a
    submitter has none. Summing it over pending rows would print "0 false accepts"
    about submissions the gate has never adjudicated -- an unearned safety claim, which
    is the one thing this project treats as worse than an acknowledged gap.
    """
    board = json.loads(Path(out).read_text(encoding="utf-8")) if Path(out).exists() else {"community": []}
    agg: Dict[tuple, Dict[str, Any]] = {}
    for p in Path(store).glob("*.jsonl"):
        for ln in p.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            e = json.loads(ln)
            key = (e["submitter"], e["model"], e["scaffold"])
            a = agg.setdefault(key, {"submitter": e["submitter"], "model": e["model"],
                                     "scaffold": e["scaffold"], "n": 0, "solved": 0,
                                     "pending": 0, "verified": 0,
                                     "false_accept": None})
            a["n"] += 1
            if e["verify_status"] == "verified":
                a["verified"] += 1
                a["solved"] += int((e.get("verified_reward") or 0) >= 0.999)
                a["false_accept"] = (a["false_accept"] or 0) + int(e.get("false_accept") or 0)
            else:
                a["pending"] += 1
    board["community"] = [
        {**v, "rate": round(v["solved"] / v["n"], 3) if v["n"] else 0.0} for v in agg.values()]
    Path(out).write_text(json.dumps(board, indent=1), encoding="utf-8")
    return board


def _main(argv: List[str]) -> int:
    if not argv:
        print(__doc__); return 2
    cmd = argv[0]
    store = STORE_DEFAULT
    if "--store" in argv:
        store = argv[argv.index("--store") + 1]
    if cmd == "validate":
        sub = json.load(sys.stdin)
        errs = validate(sub)
        print(json.dumps({"valid": not errs, "errors": errs}, indent=1))
        return 0 if not errs else 1
    if cmd == "record":
        sub = json.load(sys.stdin)
        print(json.dumps(record(sub, store), indent=1))
        return 0
    if cmd == "rebuild":
        out = argv[argv.index("--out") + 1] if "--out" in argv else "leaderboard_data.json"
        b = rebuild_leaderboard(store, out)
        print(f"community rows: {len(b.get('community', []))} -> {out}")
        return 0
    print(f"unknown command {cmd!r}"); return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
