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


# --- LIVE gold-recovery redaction -------------------------------------------
# A LIVE package withholds solution/ and the protected test bodies. That premise
# is worthless if the package also publishes the coordinates of the upstream
# merge: our tasks are derived from PUBLIC merged GitHub PRs, so
# ``git show <merge_sha>`` returns BOTH the withheld gold patch and the withheld
# test bodies, with no network needed inside the container and no cleverness
# required. ``oracle_patch_sha256`` makes it worse than a hint -- it lets an
# attacker CONFIRM offline that the fetched diff is byte-identical to the gold
# before submitting.
#
# So LIVE packages drop every field that points at the upstream commit. ARCHIVE
# packages keep all of it: they ship solution/ anyway, and full provenance is
# exactly what makes an archived task reproducible and auditable.
#
# base_sha is dropped too. It is not itself the answer, but it is the parent of
# the merge -- `git log <base_sha>..` in the named repo walks straight to it.
_LIVE_REDACT_KEYS = ("pr_number", "base_sha", "merge_sha", "source_ref",
                     "oracle_patch_sha256", "pr_url", "commit_sha")


def _sanitize_task_toml(text: str, *, live: bool = False) -> str:
    """Rewrite a host-specific ``docker_image = "<abs .sif>"`` to a portable ref.

    When ``live``, also drop the upstream-commit coordinates (see
    ``_LIVE_REDACT_KEYS``) so the withheld gold cannot be fetched from GitHub.
    """
    import re
    text = re.sub(r'(?m)^(\s*docker_image\s*=\s*).*$',
                  rf'\1"{_PORTABLE_IMAGE}"  # build from the task Dockerfile', text)
    if live:
        for key in _LIVE_REDACT_KEYS:
            text = re.sub(rf'(?m)^\s*{re.escape(key)}\s*=.*$\n?', "", text)
    return text


def _sanitize_provenance(text: str, *, live: bool) -> str:
    """Strip upstream-commit pointers from PROVENANCE.json on LIVE packages."""
    if not live:
        return text
    try:
        d = json.loads(text)
    except Exception:
        # Unparseable provenance on a live task is not shippable -- a regex
        # fallback could silently miss a field and leak the gold. Ship nothing.
        return json.dumps({"note": "provenance withheld while this task is live"},
                          indent=2)
    clean = {k: v for k, v in d.items() if k not in _LIVE_REDACT_KEYS}
    clean["note"] = ("upstream commit withheld while this task is live; "
                     "full provenance is published when it archives")
    return json.dumps(clean, indent=2)


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
    # `fail_to_pass` is the key real mined records use; the *_selectors names are
    # older/alternate shapes. Missing it shipped live tasks with an EMPTY failing-test
    # list, which makes a live task unusable (you get no target to fix).
    for k in ("fail_to_pass", "f2p_selectors", "expected_f2p_selectors", "f2p"):
        v = d.get(k)
        if isinstance(v, list) and v:
            return v
    src_obj = d.get("source", {})
    if isinstance(src_obj, dict):
        for k in ("fail_to_pass", "f2p_selectors"):
            v = src_obj.get(k)
            if isinstance(v, list) and v:
                return v
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
        (dest / "task.toml").write_text(
            _sanitize_task_toml((src / "task.toml").read_text(), live=not archive))
    if (src / "instruction.md").exists():
        shutil.copy2(src / "instruction.md", dest / "instruction.md")
    if (src / "PROVENANCE.json").exists():
        (dest / "PROVENANCE.json").write_text(
            _sanitize_provenance((src / "PROVENANCE.json").read_text(), live=not archive))
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
