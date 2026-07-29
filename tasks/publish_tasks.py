#!/usr/bin/env python3
"""publish_tasks.py -- apply the task-release policy (idempotent, checked).

Given a source task package and its merge date, publish it into the release tree:
  * ARCHIVE (>= ARCHIVE_WEEKS old): copy in FULL (incl. solution/) for reproducibility.
  * LIVE   (< ARCHIVE_WEEKS old): copy WITHOUT solution/ and without the protected
    test body -- only the failing-test IDs are exposed; scoring is server-side.
This blocks memorization + test-editing on live tasks while releasing archived tasks
fully. Pure file ops; never ships a secret (the package holds none, but we assert).

Usage:  publish_tasks.py <src_task_dir> <merge_date YYYY-MM-DD> <today YYYY-MM-DD> <out_root>
"""
import json, shutil, sys, datetime
from pathlib import Path

ARCHIVE_WEEKS = 2  # user decision: 2-week window before full release

# record.json fields that are HOST-SPECIFIC or internal build noise -> stripped on publish.
_RECORD_DROP = {"image_ref", "image_build", "generator", "repro",
                "netns_available", "needs_network"}
# a portable image reference: the consumer builds it from the task's own Dockerfile.
_PORTABLE_IMAGE = "environment/Dockerfile"


def _sanitize_task_toml(text: str) -> str:
    """Rewrite a host-specific ``docker_image = "<abs .sif>"`` to a portable ref."""
    import re
    return re.sub(r'(?m)^(\s*docker_image\s*=\s*).*$',
                  rf'\1"{_PORTABLE_IMAGE}"  # build from the task Dockerfile', text)


def _sanitize_record(text: str) -> str:
    """Drop host-path / internal build fields from record.json; keep portable metadata."""
    try:
        d = json.loads(text)
    except Exception:
        return text
    clean = {k: v for k, v in d.items() if k not in _RECORD_DROP}
    return json.dumps(clean, indent=2)


def _is_archive(merge_date: str, today: str) -> bool:
    m = datetime.date.fromisoformat(merge_date)
    t = datetime.date.fromisoformat(today)
    return (t - m).days >= ARCHIVE_WEEKS * 7


def _failing_test_ids(src: Path) -> list:
    """Best-effort failing-test IDs from record.json (F2P selectors) for live tasks."""
    rec = src / "record.json"
    if not rec.exists():
        return []
    try:
        d = json.loads(rec.read_text())
    except Exception:
        return []
    for k in ("f2p_selectors", "expected_f2p_selectors", "f2p"):
        v = d.get(k)
        if isinstance(v, list) and v:
            return v
    src_obj = d.get("source", {})
    if isinstance(src_obj, dict):
        return src_obj.get("f2p_selectors", []) or []
    return []


def publish(src: Path, merge_date: str, today: str, out_root: Path) -> dict:
    archive = _is_archive(merge_date, today)
    dest_root = out_root / ("archive" if archive else "live")
    dest = dest_root / src.name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    # always ship (SANITIZED): task.toml (portable image ref), instruction.md, PROVENANCE.json
    if (src / "task.toml").exists():
        (dest / "task.toml").write_text(_sanitize_task_toml((src / "task.toml").read_text()))
    for name in ("instruction.md", "PROVENANCE.json"):
        if (src / name).exists():
            shutil.copy2(src / name, dest / name)
    if (src / "environment").is_dir():
        shutil.copytree(src / "environment", dest / "environment")

    if archive:
        # FULL: solution/ + tests/ + record.json (record SANITIZED of host paths) ship
        for name in ("solution", "tests"):
            if (src / name).is_dir():
                shutil.copytree(src / name, dest / name)
        if (src / "record.json").exists():
            (dest / "record.json").write_text(_sanitize_record((src / "record.json").read_text()))
    else:
        # LIVE: withhold solution/ + the protected test body; expose only failing IDs
        (dest / "tests").mkdir(exist_ok=True)
        if (src / "tests" / "test.sh").exists():
            shutil.copy2(src / "tests" / "test.sh", dest / "tests" / "test.sh")
        (dest / "FAILING_TESTS.json").write_text(
            json.dumps({"failing_test_ids": _failing_test_ids(src),
                        "note": "protected assertions + gold solution withheld; "
                                "submit a patch, scored server-side"}, indent=2))

    return {"task": src.name, "mode": "archive" if archive else "live",
            "shipped_solution": archive, "dest": str(dest)}


if __name__ == "__main__":
    src, merge_date, today, out_root = sys.argv[1:5]
    print(json.dumps(publish(Path(src), merge_date, today, Path(out_root)), indent=2))
