"""cli.py -- the `tdb` command-line interface.

  tdb run <MODEL> <TASK_DIR> [--out OUT]   score a model on a task (execution gate)
  tdb oracle <TASK_DIR>                    the gate baseline (task's own solution -> 1.0)
  tdb quality <RESULTS.jsonl|json>         multi-angle quality card + readiness verdict
  tdb version

The model call uses a generic OpenAI-compatible endpoint (OPENAI_BASE_URL /
OPENAI_API_KEY). Scoring needs an apptainer/singularity host. `oracle` needs no model.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List

from . import __version__, eval as _eval, quality as _q


def _cmd_run(a) -> int:
    out = a.out or os.path.join(os.environ.get("TDB_WORK", "./.tdb_work"), "results",
                                f"{os.path.basename(a.task.rstrip('/'))}__{a.model}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    return _eval.main(["--model", a.model, "--task", a.task, "--out", out])


def _cmd_oracle(a) -> int:
    return _cmd_run(argparse.Namespace(model="oracle", task=a.task, out=a.out))


def _load_matrix(path: str):
    """Build a (task x model) solved matrix from a results file (jsonl or json list).
    Each record needs task + model + (solved | reward>=1)."""
    rows = []
    text = open(path).read().strip()
    recs = ([json.loads(l) for l in text.splitlines() if l.strip()]
            if not text.startswith("[") else json.loads(text))
    tasks, models = [], []
    cell = {}
    for r in recs:
        t, m = r.get("task"), r.get("model")
        if t is None or m is None:
            continue
        solved = bool(r.get("solved") if "solved" in r else (r.get("reward", 0) >= 0.999))
        if t not in tasks:
            tasks.append(t)
        if m not in models and m != "oracle":
            models.append(m)
        if m != "oracle":
            cell[(t, m)] = 1 if (cell.get((t, m)) or solved) else 0
    matrix = [[cell.get((t, m), 0) for m in models] for t in tasks]
    return tasks, models, matrix


def _cmd_quality(a) -> int:
    tasks, models, matrix = _load_matrix(a.results)
    if not tasks or len(models) < 2:
        print("need >=1 task and >=2 models to read multi-angle quality", file=sys.stderr)
        return 2
    card = _q.benchmark_quality_report(matrix, deep=True)
    rd = _q.benchmark_readiness(matrix)
    m = card["msq"]
    print(f"tasks={len(tasks)} models={len(models)}")
    print(f"  D(discrimination)={m['D']:.3f}  C(coverage)={m['C']:.3f}  M(monotonicity)={m['M']:.3f}")
    irt = card.get("irt", {}); rel = card.get("reliability", {})
    print(f"  IRT test-information={irt.get('total_information'):.3f}  KR-20 reliability={rel.get('kr20')}")
    ci = card.get("ci", {}).get("D", {})
    if ci.get("lo") is not None:
        print(f"  D 95% CI=[{ci['lo']:.3f}, {ci['hi']:.3f}]")
    print(f"  readiness: {'READY' if rd['ready'] else 'NOT-ready'}"
          + ("" if rd["ready"] else f" (bottleneck={rd['bottleneck']}, need ~{rd['recommended_n']} tasks)"))
    print(json.dumps({"msq": m, "irt": irt, "reliability": rel, "readiness": rd}, default=str))
    return 0


def _cmd_publish(a) -> int:
    """Regenerate the website's data file from a day's result JSONs.

    The site renders from `web/leaderboard_data.json`, so publishing a new day is
    exactly: run this, commit the JSON, push -- GitHub Pages redeploys automatically.
    """
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    agg = os.path.join(here, "..", "web", "aggregate_leaderboard.py")
    if not os.path.exists(agg):
        print(f"aggregator not found at {agg}", file=sys.stderr)
        return 2
    out = a.out or os.path.join(here, "..", "docs", "leaderboard_data.json")
    cmd = [sys.executable, agg, f"--results={a.results}", f"--out={out}"]
    if a.date:
        cmd.append(f"--date={a.date}")
    rc = subprocess.run(cmd).returncode
    if rc == 0:
        print(f"\nsite data updated: {out}\n"
              f"  commit + push it and the leaderboard site redeploys (GitHub Pages).")
    return rc


def main(argv: List[str] = None) -> int:
    p = argparse.ArgumentParser(prog="tdb", description="terminal-daily-bench")
    p.add_argument("--version", action="version", version=f"terminal-daily-bench {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="score a model on a task"); r.add_argument("model"); r.add_argument("task"); r.add_argument("--out", default=None); r.set_defaults(fn=_cmd_run)
    o = sub.add_parser("oracle", help="gate baseline"); o.add_argument("task"); o.add_argument("--out", default=None); o.set_defaults(fn=_cmd_oracle)
    q = sub.add_parser("quality", help="multi-angle quality card"); q.add_argument("results"); q.set_defaults(fn=_cmd_quality)
    pb = sub.add_parser("publish", help="results -> website data file (leaderboard_data.json)")
    pb.add_argument("results", help="DIR[:scaffold][,DIR[:scaffold] ...] of result JSONs")
    pb.add_argument("--out", default=None, help="default: web/leaderboard_data.json")
    pb.add_argument("--date", default=None, help="YYYY-MM-DD shown on the site")
    pb.set_defaults(fn=_cmd_publish)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
