#!/usr/bin/env python3
"""Run real good/bad Harbor replays without minting authority.

This probe is intentionally diagnostic-only.  It may run against a worker-owned
Harbor installation to establish whether protected execution distinguishes an
oracle patch from a source-only bad patch.  It never loads a receipt private key,
never calls promotion, and always records ``eligible_for_leaderboard=false``.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from terminal_daily_bench.harbor_score import (  # noqa: E402
    authoritative_harbor_result_snapshot,
    reward_from_harbor_result_snapshot,
)
import replay_worker  # noqa: E402
import submit_result  # noqa: E402


SCHEMA = "terminal-daily-protected-replay-diagnostic/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError(f"not a single-link regular file: {path}")
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(fd)
        if (
            (before.st_dev, before.st_ino, before.st_mode, before.st_nlink,
             before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            !=
            (after.st_dev, after.st_ino, after.st_mode, after.st_nlink,
             after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        ):
            raise ValueError(f"file changed while hashing: {path}")
        return digest.hexdigest()
    finally:
        os.close(fd)


def _artifact_facts(path: Path) -> Dict[str, Any]:
    resolved = path.resolve(strict=True)
    info = resolved.stat()
    digest = _sha256_file(resolved)
    after = resolved.stat()
    if (
        (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
         info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        !=
        (after.st_dev, after.st_ino, after.st_mode, after.st_nlink,
         after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    ):
        raise ValueError(f"artifact changed while collecting facts: {path}")
    return {
        "path": str(resolved),
        "sha256": digest,
        "uid": info.st_uid,
        "gid": info.st_gid,
        "mode": info.st_mode & 0o777,
        "worker_owned": info.st_uid == os.geteuid(),
        "worker_writable": os.access(resolved, os.W_OK, effective_ids=True),
    }


def _copy_task(source: Path, destination: Path, *, expected_sha256: str) -> str:
    """Copy one symlink-free task and prove source/destination stayed identical."""
    try:
        before_sha256 = replay_worker.hash_tree(source)
    except (OSError, ValueError) as exc:
        raise ValueError("source task tree is unsafe") from exc
    if before_sha256 != expected_sha256:
        raise ValueError("source task tree changed before diagnostic copy")
    try:
        shutil.copytree(source, destination, symlinks=True)
        copied_sha256 = replay_worker.hash_tree(destination)
        after_sha256 = replay_worker.hash_tree(source)
    except (OSError, ValueError) as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise ValueError("diagnostic task copy is unsafe") from exc
    if copied_sha256 != before_sha256 or after_sha256 != before_sha256:
        shutil.rmtree(destination, ignore_errors=True)
        raise ValueError("source task tree changed while it was copied")
    return copied_sha256


def _stable_patch_text(path: Path) -> tuple[str, str]:
    """Read the exact bounded patch bytes later recorded in diagnostic evidence."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size < 1
                or before.st_size > submit_result.MAX_PATCH_BYTES):
            raise ValueError("diagnostic bad patch is not a bounded regular file")
        chunks = []
        total = 0
        while total <= submit_result.MAX_PATCH_BYTES:
            chunk = os.read(
                fd, min(1024 * 1024, submit_result.MAX_PATCH_BYTES + 1 - total),
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(fd)
        if (
            (before.st_dev, before.st_ino, before.st_mode, before.st_nlink,
             before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            !=
            (after.st_dev, after.st_ino, after.st_mode, after.st_nlink,
             after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            or len(payload) != before.st_size
        ):
            raise ValueError("diagnostic bad patch changed while it was read")
    finally:
        os.close(fd)
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("diagnostic bad patch is not UTF-8") from exc
    return text, hashlib.sha256(payload).hexdigest()


def _validate_bad_patch(patch: str, task: str) -> None:
    submission = {
        "date": "2026-08-06",
        "submitter": "w4-diagnostic",
        "model": "known-bad",
        "model_build": "known-bad@diagnostic",
        "scaffold": "fixed-source-patch",
        "harness_version": "w4-diagnostic/v1",
        "task": task,
        "patch": patch,
    }
    errors = submit_result.validate(submission)
    if errors:
        raise ValueError("bad diagnostic patch is structurally invalid: " + "; ".join(errors))


def _test_edit_rejected(task: str) -> Dict[str, Any]:
    patch = (
        "diff --git a/tests/test_outputs.py b/tests/test_outputs.py\n"
        "--- a/tests/test_outputs.py\n+++ b/tests/test_outputs.py\n"
        "@@ -1 +1 @@\n-pass\n+assert True\n"
    )
    submission = {
        "date": "2026-08-06", "submitter": "w4-diagnostic",
        "model": "test-editor", "model_build": "test-editor@diagnostic",
        "scaffold": "fixed-source-patch", "harness_version": "w4-diagnostic/v1",
        "task": task, "patch": patch,
    }
    errors = submit_result.validate(submission)
    return {
        "rejected": any("may not edit tests" in error for error in errors),
        "error_codes": [
            "test_path_rejected" if "may not edit tests" in error else "other_validation_error"
            for error in errors
        ],
    }


def _child_env(*, case_root: Path, harbor: Path, tdb: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    for name in ("LANG", "LC_ALL", "LC_CTYPE", "TZ", "SSL_CERT_FILE", "SSL_CERT_DIR"):
        if os.environ.get(name):
            env[name] = os.environ[name]
    private_home = case_root / "home"
    private_cache = case_root / "cache"
    private_tmp = Path(tempfile.mkdtemp(prefix="tdb-w4-replay-", dir="/tmp"))
    for path in (private_home, private_cache):
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
    env.update({
        "PATH": f"{harbor.parent}:{tdb.parent}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(private_home),
        "TMPDIR": str(private_tmp),
        "XDG_CACHE_HOME": str(private_cache / "xdg"),
        "TDB_WORK": str(case_root / "work"),
        "TDB_SIF_CACHE": str(private_cache / "sif"),
        "TDB_OVERLAY_DIR": str(private_cache / "overlays"),
        "APPTAINER_CACHEDIR": str(private_cache / "apptainer"),
        "APPTAINER_TMPDIR": str(private_tmp / "apptainer"),
        "SINGULARITY_CACHEDIR": str(private_cache / "apptainer"),
        "SINGULARITY_TMPDIR": str(private_tmp / "apptainer"),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    for name in (
        "XDG_CACHE_HOME", "TDB_WORK", "TDB_SIF_CACHE", "TDB_OVERLAY_DIR",
        "APPTAINER_CACHEDIR", "APPTAINER_TMPDIR", "SINGULARITY_CACHEDIR",
        "SINGULARITY_TMPDIR",
    ):
        Path(env[name]).mkdir(parents=True, mode=0o700, exist_ok=True)
    return env


def _run_case(*, name: str, task: Path, task_sif: Path, task_sif_sha256: str,
              tdb: Path, harbor: Path, out_root: Path,
              timeout_sec: int) -> Dict[str, Any]:
    case_root = out_root / name
    case_root.mkdir(parents=True, mode=0o700)
    result_path = case_root / "result.json"
    command = [
        str(tdb), "oracle", str(task), "--task-sif", str(task_sif),
        "--task-sif-sha256", task_sif_sha256,
        "--harbor-timeout", str(timeout_sec), "--out", str(result_path),
    ]
    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    completed = subprocess.run(
        command, env=_child_env(case_root=case_root, harbor=harbor, tdb=tdb),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        timeout=timeout_sec + 180, check=False,
    )
    finished_at = dt.datetime.now(dt.timezone.utc).isoformat()
    for stream, content in (("stdout", completed.stdout), ("stderr", completed.stderr)):
        path = case_root / f"{stream}.log"
        path.write_text((content or "")[-2_000_000:], encoding="utf-8")
        path.chmod(0o600)
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        result = {}
    jobs_dir_raw = result.get("jobs_dir")
    independent_reward = None
    snapshot_sha256 = None
    if isinstance(jobs_dir_raw, str):
        try:
            jobs_dir = Path(jobs_dir_raw).resolve(strict=True)
            jobs_dir.relative_to(case_root.resolve())
            snapshot = authoritative_harbor_result_snapshot(str(jobs_dir))
            if snapshot is not None:
                independent_reward = reward_from_harbor_result_snapshot(snapshot)
                snapshot_sha256 = hashlib.sha256(
                    str(snapshot.relative_path).encode("utf-8")
                    + b"\0" + bytes(snapshot.data)
                ).hexdigest()
        except (OSError, ValueError):
            pass
    result_sha256 = _sha256_file(result_path) if result_path.is_file() else None
    return {
        "name": name,
        "started_at": started_at,
        "finished_at": finished_at,
        "returncode": completed.returncode,
        "reported_reward": result.get("reward"),
        "independent_reward": independent_reward,
        "error_present": bool(result.get("error")),
        "result_sha256": result_sha256,
        "authoritative_snapshot_sha256": snapshot_sha256,
        "task_tree_sha256": replay_worker.hash_tree(task),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--task-sif", type=Path, required=True)
    parser.add_argument("--task-sif-sha256", required=True)
    parser.add_argument("--bad-patch", type=Path, required=True)
    parser.add_argument("--tdb", type=Path, required=True)
    parser.add_argument("--harbor", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--harbor-timeout", type=int, default=480)
    args = parser.parse_args(argv)

    if not _SHA256_RE.fullmatch(args.task_sif_sha256):
        raise SystemExit("--task-sif-sha256 must be lowercase SHA-256")
    for label, path in (
        ("task", args.task), ("task SIF", args.task_sif),
        ("bad patch", args.bad_patch), ("tdb", args.tdb),
        ("Harbor", args.harbor), ("runtime", args.runtime),
    ):
        if path.is_symlink() or not path.exists():
            raise SystemExit(f"{label} is missing or is a symlink: {path}")
    actual_sif_sha256 = _sha256_file(args.task_sif)
    if actual_sif_sha256 != args.task_sif_sha256:
        raise SystemExit("task SIF digest mismatch")
    if args.out.exists() or args.out.is_symlink():
        raise SystemExit("diagnostic output already exists")
    args.out.mkdir(parents=True, mode=0o700)
    cases_root = args.out / "cases"
    cases_root.mkdir(mode=0o700)
    good_task = cases_root / "good-task"
    bad_task = cases_root / "bad-task"
    trusted_task = args.task.resolve(strict=True)
    trusted_task_sha256 = replay_worker.hash_tree(trusted_task)
    good_task_sha256 = _copy_task(
        trusted_task, good_task, expected_sha256=trusted_task_sha256,
    )
    _copy_task(
        trusted_task, bad_task, expected_sha256=trusted_task_sha256,
    )
    bad_patch, bad_patch_sha256 = _stable_patch_text(args.bad_patch)
    task_id = trusted_task.name
    _validate_bad_patch(bad_patch, task_id)
    (bad_task / "solution" / "oracle.patch").write_text(bad_patch, encoding="utf-8")
    good_patch_sha256 = _sha256_file(good_task / "solution" / "oracle.patch")
    bad_task_sha256 = replay_worker.hash_tree(bad_task)

    good = _run_case(
        name="good", task=good_task, task_sif=args.task_sif.resolve(),
        task_sif_sha256=actual_sif_sha256, tdb=args.tdb.resolve(),
        harbor=args.harbor.resolve(), out_root=args.out,
        timeout_sec=args.harbor_timeout,
    )
    bad = _run_case(
        name="bad", task=bad_task, task_sif=args.task_sif.resolve(),
        task_sif_sha256=actual_sif_sha256, tdb=args.tdb.resolve(),
        harbor=args.harbor.resolve(), out_root=args.out,
        timeout_sec=args.harbor_timeout,
    )
    test_edit = _test_edit_rejected(task_id)
    source_after_sha256 = replay_worker.hash_tree(trusted_task)
    behavior_ok = (
        good["returncode"] == 0 and good["independent_reward"] == 1.0
        and bad["returncode"] == 0 and bad["independent_reward"] == 0.0
        and test_edit["rejected"] is True
        and source_after_sha256 == trusted_task_sha256
        and good["task_tree_sha256"] == good_task_sha256
        and bad["task_tree_sha256"] == bad_task_sha256
    )
    report = {
        "schema": SCHEMA,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "scope": "real protected Harbor good/bad diagnostic; not receipt authority",
        "status": "SUCCESS" if behavior_ok else "FAILED",
        "eligible_for_leaderboard": False,
        "receipt_minted": False,
        "promotion_attempted": False,
        "semantic_false_accept_claim": None,
        "worker_euid": os.geteuid(),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "slurm_node": os.environ.get("SLURMD_NODENAME"),
        "inputs": {
            "task": task_id,
            "trusted_task_tree_sha256": trusted_task_sha256,
            "trusted_task_tree_sha256_after": source_after_sha256,
            "good_task_tree_sha256": good_task_sha256,
            "bad_task_tree_sha256": bad_task_sha256,
            "task_sif_sha256": actual_sif_sha256,
            "good_patch_sha256": good_patch_sha256,
            "bad_patch_sha256": bad_patch_sha256,
            "runner_sha256": replay_worker._runner_code_sha256(),
        },
        "authority_surface": {
            "tdb": _artifact_facts(args.tdb),
            "harbor": _artifact_facts(args.harbor),
            "container_runtime": _artifact_facts(args.runtime),
            "production_receipt_allowed": False,
            "reason": "diagnostic permits mutable Harbor; production replay policy does not",
        },
        "cases": {"good": good, "bad": bad, "test_edit": test_edit},
    }
    report_path = args.out / "result.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.chmod(0o600)
    print(json.dumps({
        "status": report["status"], "result": str(report_path),
        "good_reward": good["independent_reward"],
        "bad_reward": bad["independent_reward"],
        "receipt_minted": False,
    }, sort_keys=True))
    return 0 if behavior_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
