#!/usr/bin/env python3
"""Aggregate gate-scored eval results into the dashboard's COMPLETE data payload.

This is the PUBLISH step of the pipeline: point it at the day's result JSONs and it
emits `leaderboard_data.json` -- the single file the website renders from. Upload that
file and the site updates; nothing else changes.

    aggregate_leaderboard.py --results=DIR[:scaffold][,DIR[:scaffold] ...] \
                             --out=leaderboard_data.json [--date=YYYY-MM-DD]

Each result JSON is one scored (model, task) cell as emitted by `tdb run`
(model / task / solved / reward / false_accept_check). The payload produced:

    date n_tasks n_models n_cells semantic_fa semantic_fa_n cost_measured
    tasks[]        the day's task ids
    pooled{}       per-scaffold pooled n/solved
    leaderboard[]  one row per model, per-scaffold {n, solved, rate, fa}
    matrix{}       the primary scaffold's drill-down grid -- ONE grid, for the
                   best-covered scaffold: {tasks[], rows[{model, g[]}], scaffold};
                   g is TRI-STATE: 1 solved, 0 attempted-and-failed,
                   null never attempted
    quality{}      the multi-angle MSQ card per scaffold (D/C/M, IRT info, KR-20,
                   D 95% CI, readiness) -- via terminal_daily_bench.quality.
                   NOT computed on `matrix`: it is computed on the COMPLETE-CASE
                   reduction of that scaffold's grid, so its n_tasks / n_models
                   are the REDUCED axes and its D can differ from any D a reader
                   recomputes over the published grid. `complete_case`
                   {unattempted_cells, tasks_dropped, models_dropped} is the
                   receipt that says by how much; a page printing these
                   denominators next to the matrix's own must read it, or the
                   two silently describe different populations.
    community_verified[]  receipt-backed community submissions
    community_pending[]   unranked submissions/replay/promotion state

Integrity: this only reads already-minted execution outcomes. Protected-test replay
prevents a claimed reward from becoming a score, but it does not establish semantic
verifier false-accept. Missing cheat-trial evidence stays ``null``, never zero.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import sys

# The MSQ instrument ships in the package; degrade gracefully if not importable
# (quality is then omitted and the dashboard simply hides the card).
try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from terminal_daily_bench import quality as _q
except Exception:  # noqa: BLE001
    _q = None

_MSQ_THRESHOLDS = {"min_D": 0.4, "min_kr20": 0.7, "max_d_halfwidth": 0.15}


def load(d, scaffold):
    """Read every result JSON in ``d`` as scored (model, task) cells."""
    out = []
    for f in glob.glob(os.path.join(d, "*.json")):
        try:
            j = json.load(open(f))
        except Exception:  # noqa: BLE001 -- a malformed file never sinks the publish
            continue
        model = j.get("model", "")
        if not model or "oracle" in model.lower():
            continue          # the oracle is the gate baseline, not a leaderboard entry
        solved = bool(j.get("solved") or
                      (isinstance(j.get("reward"), (int, float)) and j["reward"] >= 0.999))
        integrity = j.get("false_accept_check") or {}
        semantic_fa = integrity.get("semantic_false_accept")
        if not isinstance(semantic_fa, (bool, int, float)):
            semantic_fa = None
        out.append({
            "model": model, "task": j.get("task"), "solved": solved,
            "fa": semantic_fa,
            "scaffold": scaffold, "cost_usd": j.get("cost_usd"),
        })
    return out


def _matrix(rows, scaffold):
    """Per-task drill-down grid for ONE scaffold: {tasks, rows:[{model,g[]}], scaffold}.

    ``g`` is TRI-STATE: 1 solved, 0 attempted-and-failed, null never attempted.

    ``solved`` is keyed over the cells that EXIST, so ``.get()`` returns None
    for exactly the (model, task) pairs no run produced. The previous ``, 0``
    default made 15 of the 600 cells in the shipped 2026-08-19 claude-code grid
    indistinguishable from failures, and no consumer -- page, gate or reader --
    could tell which. A grid is rectangular because its axes are; that does not
    make every intersection an observation.
    """
    cells = [r for r in rows if r["scaffold"] == scaffold]
    if not cells:
        return None
    tasks = sorted({r["task"] for r in cells if r["task"]})
    models = sorted({r["model"] for r in cells})
    solved = {(r["model"], r["task"]): int(r["solved"]) for r in cells}
    return {"tasks": tasks, "scaffold": scaffold,
            "rows": [{"model": m, "g": [solved.get((m, t)) for t in tasks]}
                     for m in models]}


def _complete_case(mx):
    """Reduce a tri-state grid to its largest greedy null-free submatrix.

    Returns ``(matrix, tasks_dropped, models_dropped, unattempted)`` where
    ``matrix`` is rows=tasks, cols=models -- the orientation `quality` expects.

    D, KR-20 and the IRT information total are all defined on a rectangular
    grid of observed outcomes. A null is "no run produced this cell", so the
    only two options are DROP or IMPUTE, and imputing a null as 0 is the exact
    defect this file's tri-state ``g`` exists to remove -- it would feed a
    never-run pair into the instrument as a failure and quietly depress D.

    So: drop. Greedily remove whichever axis entry carries the most nulls,
    preferring the task on a tie (an item run against only part of the field
    has no well-defined difficulty) and breaking name ties by sort order, so
    the reduction is deterministic and reproducible from the payload alone.
    """
    tasks, models = list(mx["tasks"]), [r["model"] for r in mx["rows"]]
    grid = {(r["model"], t): r["g"][j]
            for r in mx["rows"] for j, t in enumerate(mx["tasks"])}
    unattempted = sum(1 for v in grid.values() if v is None)
    live_t, live_m = list(tasks), list(models)
    while live_t and live_m:
        nulls = [(m, t) for m in live_m for t in live_t if grid[(m, t)] is None]
        if not nulls:
            break
        per_t = collections.Counter(t for _, t in nulls)
        per_m = collections.Counter(m for m, _ in nulls)
        worst_t = min(per_t.items(), key=lambda kv: (-kv[1], kv[0]))
        worst_m = min(per_m.items(), key=lambda kv: (-kv[1], kv[0]))
        if worst_t[1] >= worst_m[1]:
            live_t.remove(worst_t[0])
        else:
            live_m.remove(worst_m[0])
    matrix = [[grid[(m, t)] for m in live_m] for t in live_t]
    return matrix, len(tasks) - len(live_t), len(models) - len(live_m), unattempted


def _quality(rows, scaffold):
    """The MSQ card for ONE scaffold, computed from its (task x model) solve matrix."""
    if _q is None:
        return None
    mx = _matrix(rows, scaffold)
    if not mx or len(mx["rows"]) < 2 or not mx["tasks"]:
        return None            # a multi-angle read needs >= 2 models
    # quality expects rows = tasks, cols = models, and every cell observed:
    # `g` is tri-state now, so the nulls are DROPPED here, never imputed.
    matrix, t_drop, m_drop, unattempted = _complete_case(mx)
    if len(matrix) < 1 or len(matrix[0]) < 2:
        return None            # nothing rectangular survives the reduction
    try:
        card = _q.benchmark_quality_report(matrix, deep=True, ci_n_boot=500)
        rd = _q.benchmark_readiness(matrix, ci_n_boot=500, **_MSQ_THRESHOLDS)
        m, ci = card["msq"], card["ci"]["D"]
        irt, rel = card["irt"], card["reliability"]
        return {
            "D": m["D"], "C": m["C"], "M": m["M"], "composite": m["composite"],
            "irt_info": irt["total_information"], "kr20": rel["kr20"] or 0.0,
            "D_ci": [ci["lo"], ci["hi"]],
            # n_tasks / n_models describe the REDUCED grid the card was
            # computed on, not the axes of the published matrix.
            "n_tasks": m["n_tasks"], "n_models": m["n_models"],
            "ready": rd["ready"], "bottleneck": rd["bottleneck"],
            "required_n_D": rd["recommended_n"],
            "complete_case": {"unattempted_cells": unattempted,
                              "tasks_dropped": t_drop, "models_dropped": m_drop},
        }
    except Exception as e:  # noqa: BLE001 -- an advisory card never blocks publishing
        print(f"[warn] quality card for {scaffold} failed: {type(e).__name__}: {e}",
              file=sys.stderr)
        return None


def build_payload(rows, date):
    """Assemble the COMPLETE dashboard payload from scored cells."""
    scaffolds = sorted({r["scaffold"] for r in rows})
    tasks = sorted({r["task"] for r in rows if r["task"]})
    models = sorted({r["model"] for r in rows})

    board = collections.defaultdict(lambda: collections.defaultdict(
        lambda: {"n": 0, "solved": 0, "fa": 0, "fa_n": 0}))
    pooled = collections.defaultdict(lambda: {"n": 0, "solved": 0})
    for r in rows:
        b = board[r["model"]][r["scaffold"]]
        b["n"] += 1
        b["solved"] += int(r["solved"])
        if r["fa"] is not None:
            b["fa"] += int(r["fa"])
            b["fa_n"] += 1
        p = pooled[r["scaffold"]]
        p["n"] += 1
        p["solved"] += int(r["solved"])

    leaderboard = []
    for model, per_scaffold in board.items():
        row = {"model": model}
        for s, v in per_scaffold.items():
            row[s] = {"n": v["n"], "solved": v["solved"],
                      "rate": round(v["solved"] / v["n"], 3) if v["n"] else 0.0,
                      "fa": v["fa"] if v["fa_n"] else None,
                      "fa_n": v["fa_n"]}
        leaderboard.append(row)
    # rank by the best rate the model reached under any scaffold, then by name
    leaderboard.sort(key=lambda r: (-max((v.get("rate", 0.0) for v in r.values()
                                          if isinstance(v, dict)), default=0.0),
                                    r["model"]))
    if leaderboard:
        leaderboard[0]["lead"] = True

    # SUPERSEDED by the per-day layout under docs/data/, which adds one file
    # per day instead of overwriting this one. Kept working only so the legacy
    # whole-site file is not actively wrong while it still exists.
    #
    # The name it looked for was "terminus2"; the scaffold is spelled
    # "terminus-2". The test therefore never fired and sorted()[0] won, so the
    # published drill-down silently described "claude-code" -- 12 of 152 models
    # -- while claiming to be the flagship agent's matrix. Prefer the
    # best-covered scaffold, which is a property of the data rather than a name
    # someone has to keep in sync.
    primary = max(scaffolds, key=lambda s_: sum(
        1 for r in rows if r.get("scaffold") == s_), default="") if scaffolds else ""
    payload = {
        "date": date,
        "n_tasks": len(tasks), "n_models": len(models), "n_cells": len(rows),
        "total_fa": (sum(int(r["fa"]) for r in rows if r["fa"] is not None)
                     if any(r["fa"] is not None for r in rows) else None),
        "total_fa_n": sum(1 for r in rows if r["fa"] is not None),
        "cost_measured": any(r.get("cost_usd") is not None for r in rows),
        "tasks": tasks,
        "pooled": {s: dict(pooled[s]) for s in scaffolds},
        "leaderboard": leaderboard,
        # ONE grid: the primary scaffold's. A `matrices` map keyed by every
        # scaffold was emitted here alongside it; nothing on the site read it,
        # and because JSON has no references the primary grid was serialised
        # twice, so the map roughly quadrupled a file that `/`, `/quality/` and
        # `/leaderboard/` all fetch on their critical path. Per-scaffold
        # drill-downs belong in a separate on-demand file if a consumer ever
        # ships -- build_day_data.validate_day already accepts one.
        "matrix": _matrix(rows, primary),
        "quality": None,
        "community_verified": [],
        "community_replay_verified": [],
        "community_pending": [],
        "community_suite": {
            "date": None,
            "suite_sha256": None,
            "roster_n": None,
            "ranking_requires_complete_roster": True,
            "official_results_included": False,
        },
        # Backward-compatible alias.  It is intentionally verified-only.
        "community": [],
    }
    q = {s: v for s, v in ((s, _quality(rows, s)) for s in scaffolds) if v}
    if q:
        q["thresholds"] = _MSQ_THRESHOLDS
        payload["quality"] = q
    return payload


def main(argv):
    dirs, out, date = [], "leaderboard_data.json", "today"
    for a in argv:
        if a.startswith("--results="):
            dirs = [x.split(":") for x in a.split("=", 1)[1].split(",")]
        elif a.startswith("--out="):
            out = a.split("=", 1)[1]
        elif a.startswith("--date="):
            date = a.split("=", 1)[1]
    if not dirs:
        print(__doc__)
        return 2
    rows = []
    for spec in dirs:
        d = spec[0]
        scaffold = spec[1] if len(spec) > 1 else "single_shot"
        rows += load(d, scaffold)
    if not rows:
        print("no result cells found -- nothing to publish", file=sys.stderr)
        return 1
    payload = build_payload(rows, date)
    with open(out, "w") as fh:
        json.dump(payload, fh, indent=1)
    fa_summary = (str(payload["total_fa"]) if payload["total_fa"] is not None
                  else "unmeasured")
    print(f"published {len(rows)} cells / {payload['n_models']} models / "
          f"{payload['n_tasks']} tasks, semantic_FA={fa_summary}"
          f"{', MSQ card OK' if payload['quality'] else ''} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
