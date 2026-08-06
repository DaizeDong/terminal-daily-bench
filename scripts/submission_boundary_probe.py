#!/usr/bin/env python3
"""Exercise good, bad, and test-edit submission boundaries without scoring.

The accepted patches must remain ``pending``.  This probe never calls Harbor
and therefore never presents recorder acceptance as replay evidence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pwd
import socket
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import submit_result  # noqa: E402


def _outside_home(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        raw_home = Path(pwd.getpwuid(os.geteuid()).pw_dir)
    except KeyError as exc:
        raise ValueError("operator account HOME is unavailable") from exc
    if not raw_home.is_absolute():
        raise ValueError("operator account HOME is not absolute")
    account_home = raw_home.resolve()
    try:
        resolved.relative_to(account_home)
    except ValueError:
        return resolved
    raise ValueError("probe artifacts must not live under account HOME")


def _read_public_fixture(task_dir: Path, relative: Path) -> str:
    """Read one regular, symlink-free fixture without escaping its public task."""
    candidate = task_dir / relative
    current = task_dir
    try:
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("fixture path contains a symlink")
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(task_dir)
    except (FileNotFoundError, ValueError) as exc:
        raise ValueError("probe fixture is missing or escapes the public task") from exc
    if not resolved.is_file():
        raise ValueError("probe fixture is not a regular file")
    return resolved.read_text(encoding="utf-8")


def _make_private_store(path: Path) -> None:
    """Create an exclusive probe store so production submissions cannot be polluted."""
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    try:
        path.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise ValueError("probe store must be a new path") from exc
    path_stat = path.lstat()
    if (path.is_symlink() or not path.is_dir()
            or path_stat.st_uid != os.geteuid()
            or path_stat.st_mode & 0o077):
        raise ValueError("probe store must be a private worker-owned directory")


def _write_new(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _submission(*, date: str, task: str, patch: str,
                model_build: str, reward_claimed: float) -> dict[str, Any]:
    return {
        "date": date,
        "submitter": "operator-boundary-probe",
        "model": "not-a-model-run",
        "model_build": model_build,
        "scaffold": "recorder-boundary-only",
        "harness_version": "terminal-daily-w4-probe-v1",
        "task": task,
        "patch": patch,
        "reward_claimed": reward_claimed,
    }


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        archive_root = (ROOT / "tasks" / "archive").resolve(strict=True)
        task_dir = args.task_dir.resolve(strict=True)
    except OSError:
        raise SystemExit("--task-dir is unavailable") from None
    if not task_dir.is_dir() or task_dir.parent != archive_root:
        raise SystemExit("--task-dir must be one direct public tasks/archive package")
    try:
        store = _outside_home(args.store)
        out = _outside_home(args.out)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    try:
        out.relative_to(store)
    except ValueError:
        pass
    else:
        raise SystemExit("--out must be outside the dedicated probe store")
    task = task_dir.name
    try:
        good_patch = _read_public_fixture(
            task_dir, Path("solution") / "oracle.patch"
        )
        test_edit_patch = _read_public_fixture(
            task_dir, Path("tests") / "test_patch.diff"
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    if "word[-1] in 'sx'" not in good_patch:
        raise SystemExit("probe task's oracle patch lacks the expected semantic mutation")
    bad_patch = good_patch.replace("word[-1] in 'sx'", "word[-1] in 'sz'", 1)

    good = _submission(
        date=args.date,
        task=task,
        patch=good_patch,
        model_build="good-patch-boundary-fixture",
        reward_claimed=1.0,
    )
    bad = _submission(
        date=args.date,
        task=task,
        patch=bad_patch,
        model_build="bad-patch-boundary-fixture",
        reward_claimed=1.0,
    )
    test_edit = _submission(
        date=args.date,
        task=task,
        patch=test_edit_patch,
        model_build="test-edit-boundary-fixture",
        reward_claimed=1.0,
    )

    good_errors = submit_result.validate(good)
    bad_errors = submit_result.validate(bad)
    test_edit_errors = submit_result.validate(test_edit)
    if good_errors or bad_errors:
        raise SystemExit(f"source-only fixtures failed structural validation: {good_errors + bad_errors}")
    if not any("may not edit tests" in error for error in test_edit_errors):
        raise SystemExit("test-edit fixture was not rejected")

    try:
        _make_private_store(store)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    good_entry = submit_result.record(
        good, str(store), authenticated_submitter="operator-boundary-probe"
    )
    bad_entry = submit_result.record(
        bad, str(store), authenticated_submitter="operator-boundary-probe"
    )
    for entry in (good_entry, bad_entry):
        if (entry.get("verify_status") != "pending"
                or entry.get("verified_reward") is not None
                or entry.get("false_accept") is not None
                or entry.get("receipt_sha256") is not None
                or entry.get("claim_mismatch") is not None
                or entry.get("attempt_count") != 0
                or entry.get("attempt_id") is not None):
            raise SystemExit("recorder assigned replay authority to an unverified patch")

    report = {
        "schema": "terminal-daily-submission-boundary-probe-v1",
        "status": "SUCCESS",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "job_id": os.environ.get("SLURM_JOB_ID"),
        "hostname": socket.gethostname(),
        "task": task,
        "date": args.date,
        "good_patch": {
            "id": good_entry["id"],
            "patch_sha256": good_entry["patch_sha256"],
            "verify_status": good_entry["verify_status"],
            "verified_reward": good_entry["verified_reward"],
            "false_accept": good_entry["false_accept"],
            "receipt_sha256": good_entry["receipt_sha256"],
        },
        "bad_patch": {
            "id": bad_entry["id"],
            "patch_sha256": bad_entry["patch_sha256"],
            "verify_status": bad_entry["verify_status"],
            "verified_reward": bad_entry["verified_reward"],
            "false_accept": bad_entry["false_accept"],
            "receipt_sha256": bad_entry["receipt_sha256"],
        },
        "test_edit": {
            "recorded": False,
            "errors": test_edit_errors,
        },
        "replay": "NOT RUN",
        "production_score_claimed": False,
        "scope": "real recorder boundary; no Harbor execution or replay receipt",
    }
    _write_new(out, report)
    print(json.dumps({
        "status": report["status"],
        "task": task,
        "accepted_pending": 2,
        "test_edit_rejected": True,
        "out": str(out),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
