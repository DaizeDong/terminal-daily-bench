"""cli.py -- the `tdb` command-line interface.

  tdb doctor [TASK_DIR]                    preflight: is this host able to score?
  tdb run <MODEL> <TASK_DIR> [--out OUT]   score a model on a task (execution gate)
  tdb oracle <TASK_DIR>                    the gate baseline (task's own solution -> 1.0)
  tdb quality <RESULTS.jsonl|json>         multi-angle quality card + readiness verdict
  tdb version

The model call uses a generic OpenAI-compatible endpoint (OPENAI_BASE_URL /
OPENAI_API_KEY). Scoring shells out to `harbor` and needs an apptainer/singularity
host. `oracle` needs no model. Run `tdb doctor` first -- it reports exactly which of
those pieces are present on this host, and the harbor build we score against is not
yet public (see README "Requirements").
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
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
    if rc != 0:
        return rc
    # the site has TWO data files: the board (who solved what) and the catalogue
    # (what the benchmark contains). Regenerate both so one command refreshes the site.
    gen = os.path.join(here, "..", "web", "gen_site_data.py")
    if os.path.exists(gen):
        subprocess.run([sys.executable, gen])
    print(f"\nsite data updated: {out}\n"
          f"  commit + push it and the site redeploys (GitHub Pages).")
    return 0


# ---------------------------------------------------------------------------
# doctor -- preflight. Reports honestly; never fixes anything, never guesses.
# ---------------------------------------------------------------------------
_REQUIRED = "required"        # scoring is impossible without it
_RUN_ONLY = "required-for-run"  # only `tdb run` (a real model) needs it
_OPTIONAL = "optional"


def _probe_version(exe: str) -> str:
    """Best-effort `<exe> --version`; returns '' if it cannot be read."""
    try:
        p = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60)
    except Exception as e:  # noqa: BLE001 -- a broken binary must not crash the doctor
        return f"(--version failed: {type(e).__name__})"
    line = ((p.stdout or "") + (p.stderr or "")).strip().splitlines()
    return line[0].strip() if line else "(--version printed nothing)"


def _check_task_dir(task: str):
    """Structural sanity of a task package (see tasks/SCHEMA.md). Never executes it."""
    if not os.path.isdir(task):
        return False, f"not a directory: {task}"
    missing = [n for n in ("task.toml", "instruction.md", "tests", "environment")
               if not os.path.exists(os.path.join(task, n))]
    if missing:
        return False, f"{task}: missing {', '.join(missing)}"
    split = ("archive-style (solution/ present)"
             if os.path.isdir(os.path.join(task, "solution"))
             else "live-style (no solution/ -- `tdb oracle` will not work; scored server-side)")
    note = f"{os.path.basename(task.rstrip('/'))}: task.toml + instruction.md + tests/ + environment/, {split}"
    # What the gate would execute. `environment.docker_image` is either a build
    # recipe relative to the task dir (harbor builds the SIF) or an absolute
    # image/SIF path. Informational only -- harbor, not this bundle, materializes it.
    try:
        import tomllib
        with open(os.path.join(task, "task.toml"), "rb") as fh:
            img = (tomllib.load(fh).get("environment", {}) or {}).get("docker_image", "")
    except Exception:  # noqa: BLE001
        return False, note + "; task.toml unreadable as TOML"
    if img:
        local = img if os.path.isabs(img) else os.path.join(task, img)
        if os.path.exists(local):
            kind = ("build recipe present, SIF built by harbor"
                    if not local.endswith(".sif") else "image present")
        else:
            kind = "not on this host; harbor pulls/builds it"
        note += f"; image={img} ({kind})"
    return True, note


def _cmd_doctor(a) -> int:
    """Preflight the host: python, harbor, apptainer/singularity, endpoint env, task dir.

    Prints one OK/MISSING line per check and exits non-zero if anything required is
    absent. This is deliberately blunt: the execution gate shells out to `harbor`, and
    the harbor build these tasks are scored against is a patched fork that is not yet
    published (README "Requirements"), so a fresh third-party host is EXPECTED to see
    `harbor  MISSING` here.
    """
    checks = []  # (ok, level, name, detail)

    v = sys.version_info
    checks.append((v >= (3, 10), _REQUIRED, "python >= 3.10",
                   f"{v.major}.{v.minor}.{v.micro} at {sys.executable}"))

    harbor = shutil.which("harbor")
    checks.append((bool(harbor), _REQUIRED, "harbor on PATH",
                   f"{harbor} -- {_probe_version('harbor')}" if harbor else
                   "not on PATH. Scoring shells out to `harbor run -p <task> -a oracle "
                   "-e singularity --ek singularity_*=...`; the build we score against "
                   "is a patched fork that is not yet public (README 'Requirements')."))

    apptainer = shutil.which("apptainer") or shutil.which("singularity")
    checks.append((bool(apptainer), _REQUIRED, "apptainer/singularity on PATH",
                   f"{apptainer} -- {_probe_version(apptainer)}" if apptainer else
                   "not on PATH; the harbor singularity backend executes each task's SIF"))

    base = os.environ.get("OPENAI_BASE_URL")
    checks.append((True, _OPTIONAL, "OPENAI_BASE_URL",
                   base if base else "unset -> defaults to https://api.openai.com/v1"))

    key = os.environ.get("OPENAI_API_KEY")
    key_level = _OPTIONAL if a.oracle_only else _RUN_ONLY
    checks.append((bool(key), key_level, "OPENAI_API_KEY",
                   f"set (len={len(key)}, ...{key[-4:]})" if key else
                   "unset -- needed by `tdb run` only (`tdb oracle` / `tdb quality` do "
                   "not call a model; pass --oracle-only to stop treating this as a failure)"))

    if a.task:
        ok, detail = _check_task_dir(a.task)
        checks.append((ok, _REQUIRED, "task dir well-formed", detail))
    else:
        checks.append((True, _OPTIONAL, "task dir well-formed",
                       "no TASK_DIR given -- pass one to check it, e.g. "
                       "`tdb doctor tasks/archive/<task-id>`"))

    print(f"tdb doctor -- terminal-daily-bench {__version__}")
    failures = []
    for ok, level, name, detail in checks:
        if ok:
            status = "OK     "
        elif level == _OPTIONAL:
            status = "MISSING"  # reported, not fatal
        else:
            status = "MISSING"
            failures.append((name, level))
        suffix = "" if level == _REQUIRED else f"  [{level}]"
        print(f"{status}  {name}{suffix}: {detail}")

    if failures:
        print("\nNOT ready: " + ", ".join(n for n, _ in failures))
        if any(n == "harbor on PATH" for n, _ in failures):
            print("Note: `harbor` is the execution gate. The build these tasks are scored "
                  "against is a patched fork of harbor-framework/harbor that we have NOT "
                  "published yet; vendoring/publishing it is tracked as the next release "
                  "step. Until then `tdb run`/`tdb oracle` cannot run on a third-party "
                  "host. `tdb quality` and `tdb publish` work without harbor.")
        return 1
    print("\nready: this host can run the execution gate.")
    return 0


def main(argv: List[str] = None) -> int:
    p = argparse.ArgumentParser(prog="tdb", description="terminal-daily-bench")
    p.add_argument("--version", action="version", version=f"terminal-daily-bench {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("doctor", help="preflight this host (run me first)")
    d.add_argument("task", nargs="?", default=None, help="optional task dir to sanity-check")
    d.add_argument("--oracle-only", action="store_true",
                   help="do not fail on a missing OPENAI_API_KEY (oracle/quality need no model)")
    d.set_defaults(fn=_cmd_doctor)
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
