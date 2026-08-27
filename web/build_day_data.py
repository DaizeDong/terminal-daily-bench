#!/usr/bin/env python3
"""Build the site's per-day data layout, and install days emitted elsewhere.

WHY THIS EXISTS. The site used to read two whole-site files (site_data.json,
leaderboard_data.json) that were regenerated in place, and the pages that showed
history rendered one card per published day. Both scale badly on a benchmark
whose suite rotates DAILY: the reader downloads every day to look at one, and
publishing a day means rewriting a file every page depends on.

THE LAYOUT INSTEAD:

    docs/data/index.json          {"days": [...newest first...], "latest": ...}
    docs/data/days/<date>.json    one sealed day

Publishing day N+1 writes ONE new file and appends ONE id to the index. Nothing
else is rewritten, no page is regenerated, and the site changes because the data
changed -- which is the property the old arrangement did not have.

TWO WAYS IN, and they meet in the same place:

  --install <file>   a day already emitted in tdb-day-v1 shape by whatever
                     produced the results. This is the path that makes a
                     measured result appear on the site with no hand-editing.

  --from-legacy      convert the existing whole-site leaderboard_data.json +
                     site_data.json into the same shape, so the site has history
                     from before the layout existed.

Both then rewrite index.json from what is actually on disk, so the index can
never claim a day whose file is missing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

SCHEMA_DAY = "tdb-day-v1"
SCHEMA_INDEX = "tdb-day-index-v1"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _write(path: Path, obj: Any) -> None:
    """Atomic, and newline-normalised so a Windows checkout does not churn."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1, sort_keys=False)
        fh.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# validation -- a malformed day must be refused here, not rendered as empty
# ---------------------------------------------------------------------------
def validate_day(day: Dict[str, Any], source: str) -> None:
    """Raise with a usable message, rather than let the page show nothing.

    Every field checked here is one the page reads. The failure this prevents is
    the one the site already had once: a data problem arriving as a page that
    says "0 entries", which is indistinguishable from a day on which nothing was
    measured.
    """
    def bad(msg: str) -> None:
        raise SystemExit(f"FATAL: {source}: {msg}")

    if not isinstance(day, dict):
        bad("top level is not an object")
    if day.get("schema") != SCHEMA_DAY:
        bad(f"schema is {day.get('schema')!r}, expected {SCHEMA_DAY!r}")
    date = day.get("date")
    if not isinstance(date, str) or not DATE_RE.match(date):
        bad(f"date is {date!r}, expected YYYY-MM-DD")
    board = day.get("leaderboard")
    if not isinstance(board, list):
        bad("leaderboard is not a list")

    cells = 0
    for i, entry in enumerate(board):
        if not isinstance(entry, dict) or not entry.get("model"):
            bad(f"leaderboard[{i}] has no model")
        for key, cell in entry.items():
            if key == "model" or not isinstance(cell, dict):
                continue
            if "n" not in cell:
                continue
            cells += 1
            n, solved = cell.get("n"), cell.get("solved")
            if not isinstance(n, int) or n < 0:
                bad(f"leaderboard[{i}].{key}.n is {n!r}")
            if not isinstance(solved, int) or solved < 0 or solved > n:
                bad(f"leaderboard[{i}].{key}: solved={solved!r} is not in 0..{n}")
    if board and not cells:
        bad("leaderboard has entries but not one measured cell -- the page would "
            "render an empty table for a file that is not empty")

    # ---- solve grids -----------------------------------------------------
    # `g` is TRI-STATE (1 solved / 0 attempted-and-failed / null never
    # attempted). Two things can go wrong silently and both render as a
    # plausible page: a row shorter than `tasks` slides every cell after the
    # gap onto the wrong task, and a cell that is neither 1, 0 nor null (a
    # bool, a float, the string "0") is truthy-tested somewhere downstream and
    # becomes a solve. Neither is visible in a screenshot, so both are refused
    # here rather than published.
    grids = []
    if isinstance(day.get("matrix"), dict):
        grids.append(("matrix", day["matrix"]))
    if isinstance(day.get("matrices"), dict):
        for name in sorted(day["matrices"]):
            if isinstance(day["matrices"][name], dict):
                grids.append((f"matrices[{name!r}]", day["matrices"][name]))
    for label, mx in grids:
        mx_tasks = mx.get("tasks")
        if not isinstance(mx_tasks, list):
            bad(f"{label}.tasks is not a list")
        mx_rows = mx.get("rows")
        if not isinstance(mx_rows, list):
            bad(f"{label}.rows is not a list")
        for i, row in enumerate(mx_rows):
            if not isinstance(row, dict) or not row.get("model"):
                bad(f"{label}.rows[{i}] has no model")
            g = row.get("g")
            if not isinstance(g, list):
                bad(f"{label}.rows[{i}].g is not a list")
            if len(g) != len(mx_tasks):
                bad(f"{label}.rows[{i}] ({row.get('model')!r}) has {len(g)} cells "
                    f"for {len(mx_tasks)} tasks -- every cell after the gap would "
                    "be attributed to the wrong task")
            for j, cell in enumerate(g):
                if cell is None:
                    continue          # never attempted; NOT a failure
                # `__class__ is not int` and not isinstance(): True is an int
                # in Python and would slip through isinstance, then serialise
                # back out as `true` -- a fourth state nothing downstream reads.
                if cell.__class__ is not int or cell not in (0, 1):
                    bad(f"{label}.rows[{i}].g[{j}] is {cell!r}; a solve cell is "
                        "1, 0 or null (never attempted)")


# ---------------------------------------------------------------------------
# legacy conversion
# ---------------------------------------------------------------------------
def from_legacy(docs: Path) -> Dict[str, Any]:
    board_path, site_path = docs / "leaderboard_data.json", docs / "site_data.json"
    if not board_path.is_file():
        raise SystemExit(f"FATAL: {board_path} not found")
    board = _read(board_path)
    site = _read(site_path) if site_path.is_file() else {}

    date = board.get("date")
    if not (isinstance(date, str) and DATE_RE.match(date)):
        raise SystemExit(f"FATAL: leaderboard_data.json has date={date!r}")

    suites = [s for s in (site.get("suites") or []) if s.get("id") == date]
    scoring = site.get("scoring") or {}

    day = {
        "schema": SCHEMA_DAY,
        "date": date,
        "generated": _now(),
        "source": "legacy leaderboard_data.json",
        # An uncertified day must never present itself as a ranking; the page
        # keys its label on exactly this flag.
        "official_ranking": bool(scoring.get("official_ranking")),
        "n_tasks": board.get("n_tasks"),
        "n_models": board.get("n_models"),
        "n_cells": board.get("n_cells"),
        "suite": suites[0] if suites else None,
        "leaderboard": board.get("leaderboard") or [],
        "pooled": board.get("pooled") or {},
    }
    # The solve grids come across too. Without this, validate_day's tri-state
    # checks had nothing to run against on any real file -- every day this
    # repo can produce was built here, so a grid guard the converter never
    # fed is a guard that cannot fire. Forwarded CONDITIONALLY: writing
    # `"matrix": board.get("matrix")` would put a JSON null in the day for a
    # legacy file that has no grid, and `null` is a value a reader has to
    # interpret, where an absent key is not.
    for key in ("matrix", "matrices"):
        if isinstance(board.get(key), dict):
            day[key] = board[key]
    validate_day(day, "converted from leaderboard_data.json")
    return day


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------
def rebuild_index(docs: Path) -> Dict[str, Any]:
    """The index is derived from the directory, never appended to blindly.

    An index that lists a day whose file is missing produces a 404 the reader
    sees as a broken page; deriving it means the two cannot disagree.
    """
    days_dir = docs / "data" / "days"
    days = sorted(
        p.stem for p in days_dir.glob("*.json") if DATE_RE.match(p.stem)
    ) if days_dir.is_dir() else []
    days.reverse()
    idx = {
        "schema": SCHEMA_INDEX,
        "generated": _now(),
        "days": days,
        "latest": days[0] if days else None,
    }
    _write(docs / "data" / "index.json", idx)
    return idx


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    here = Path(__file__).resolve().parent
    ap.add_argument("--docs", default=str(here.parent / "docs"),
                    help="the site root (default: ../docs)")
    ap.add_argument("--install", metavar="FILE",
                    help="a tbd-day-v1 file emitted elsewhere (e.g. by `td site-day`)")
    ap.add_argument("--from-legacy", action="store_true",
                    help="convert the existing whole-site JSON into one day")
    ap.add_argument("--index-only", action="store_true",
                    help="just rebuild data/index.json from what is on disk")
    args = ap.parse_args(argv)

    docs = Path(args.docs).resolve()
    if not docs.is_dir():
        sys.stderr.write(f"FATAL: --docs {docs} is not a directory\n")
        return 2

    if args.install:
        src = Path(args.install).resolve()
        if not src.is_file():
            sys.stderr.write(f"FATAL: {src} not found\n")
            return 2
        day = _read(src)
        validate_day(day, str(src))
        dest = docs / "data" / "days" / f"{day['date']}.json"
        existed = dest.is_file()
        _write(dest, day)
        print(f"{'replaced' if existed else 'added'} {dest.relative_to(docs)}")
    elif args.from_legacy:
        day = from_legacy(docs)
        dest = docs / "data" / "days" / f"{day['date']}.json"
        _write(dest, day)
        print(f"converted legacy data -> {dest.relative_to(docs)} "
              f"({len(day['leaderboard'])} models)")
    elif not args.index_only:
        ap.error("give one of --install, --from-legacy or --index-only")

    idx = rebuild_index(docs)
    print(f"index: {len(idx['days'])} day(s), latest {idx['latest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
