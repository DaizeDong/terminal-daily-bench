#!/usr/bin/env python3
"""Run the production replay worker's paired egress canary and persist evidence.

This is an operator probe, not a replay receipt.  It exercises the exact
control/isolated container commands used by ``web/replay_worker.py`` while
keeping the output on the operator-selected shared data root.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pwd
import re
import socket
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

import replay_worker  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stage_sif(
    source: Path,
    work_root: Path,
    *,
    _after_chunk: Callable[[], None] | None = None,
) -> tuple[Path, str, dict[str, Any]]:
    """Copy one fd-stable source snapshot into the private canary work root."""
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise RuntimeError("runtime_sif_nofollow_unavailable")
    try:
        source_fd = os.open(source, os.O_RDONLY | nofollow)
    except OSError as exc:
        raise RuntimeError("runtime_sif_source_symlink_or_unavailable") from exc

    destination_dir = work_root / "runtime-image"
    destination = destination_dir / "canary.sif"
    digest = hashlib.sha256()
    try:
        before = os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError("runtime_sif_source_not_regular")
        destination_dir.mkdir(mode=0o700)
        destination_fd = os.open(
            destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400,
        )
        try:
            with os.fdopen(source_fd, "rb", closefd=False) as source_handle, \
                    os.fdopen(destination_fd, "wb") as destination_handle:
                for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
                    digest.update(chunk)
                    destination_handle.write(chunk)
                    if _after_chunk is not None:
                        _after_chunk()
                destination_handle.flush()
                os.fsync(destination_handle.fileno())
        finally:
            try:
                os.close(destination_fd)
            except OSError:
                pass
        after = os.fstat(source_fd)
    finally:
        os.close(source_fd)

    stable_fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_uid",
                     "st_gid", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, key) != getattr(after, key) for key in stable_fields):
        raise RuntimeError("runtime_sif_source_changed_during_staging")
    staged_stat = destination.lstat()
    if (destination.is_symlink() or not stat.S_ISREG(staged_stat.st_mode)
            or staged_stat.st_size != before.st_size):
        raise RuntimeError("runtime_sif_staged_snapshot_invalid")
    os.chmod(destination, 0o400)
    staged_sha256 = digest.hexdigest()
    if _sha256(destination) != staged_sha256:
        raise RuntimeError("runtime_sif_staged_digest_mismatch")
    return destination, staged_sha256, {
        "source_device": before.st_dev,
        "source_inode": before.st_ino,
        "source_size": before.st_size,
        "source_stat_stable": True,
        "staged_mode": destination.stat().st_mode & 0o777,
        "staged_size": staged_stat.st_size,
    }


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
    raise ValueError("canary artifacts must not live under account HOME")


def _prepare_private_empty_dir(path: Path) -> None:
    """Require a fresh, worker-owned root before creating runtime state below it."""
    try:
        path.mkdir(parents=True, mode=0o700)
    except FileExistsError:
        pass
    try:
        path_stat = path.lstat()
    except OSError as exc:
        raise ValueError("canary work root is unavailable") from exc
    if (path.is_symlink() or not path.is_dir()
            or path_stat.st_uid != os.geteuid()
            or path_stat.st_mode & 0o077):
        raise ValueError("canary work root must be a private worker-owned directory")
    if any(path.iterdir()):
        raise ValueError("canary work root must be empty")


def _safe_error(exc: BaseException) -> str:
    raw = str(exc).strip().lower() or type(exc).__name__.lower()
    return re.sub(r"[^a-z0-9_.-]+", "_", raw).strip("_.-")[:120]


def _write_new(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, default=Path("/usr/bin/apptainer"))
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    image_source = Path(os.path.abspath(os.path.expanduser(args.image)))
    try:
        runtime = args.runtime.resolve(strict=True)
    except OSError:
        raise SystemExit("container runtime is unavailable") from None
    try:
        work_root = _outside_home(args.work_root)
        out = _outside_home(args.out)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    if image_source.suffix.lower() != ".sif":
        raise SystemExit("--image must name a prebuilt .sif")
    runtime_kind = runtime.name
    if runtime_kind not in {"apptainer", "singularity"}:
        raise SystemExit("--runtime must resolve to canonical apptainer or singularity")
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")

    try:
        runtime_sha256 = _sha256(runtime)
        version_run = subprocess.run(
            [str(runtime), "--version"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise SystemExit("container runtime preflight failed") from None
    version = (version_run.stdout or "").strip().splitlines()
    if version_run.returncode != 0 or not version:
        raise SystemExit("container runtime did not report a version")
    policy = {
        "container_runtime_kind": runtime_kind,
        "container_runtime_path": str(runtime),
        "container_runtime_binary_sha256": runtime_sha256,
        "container_runtime_version": version[0][:500],
    }
    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    report: dict[str, Any] = {
        "schema": "terminal-daily-paired-egress-canary-v1",
        "status": "FAILED",
        "started_at": started_at,
        "finished_at": None,
        "job_id": os.environ.get("SLURM_JOB_ID"),
        "hostname": socket.gethostname(),
        "image_source_path": str(image_source),
        "image_path": None,
        "image_sha256": None,
        "image_staging": None,
        "target_sha256": hashlib.sha256(
            f"{args.host}:{args.port}".encode("utf-8")
        ).hexdigest(),
        "evidence": None,
        "error": None,
        "scope": "paired canary only; not a replay receipt or semantic verifier claim",
    }
    try:
        _prepare_private_empty_dir(work_root)
        image, image_sha256, staging = _stage_sif(image_source, work_root)
        report["image_path"] = str(image)
        report["image_sha256"] = image_sha256
        report["image_staging"] = staging
        os.environ["TDB_EGRESS_CANARY_HOST"] = args.host
        os.environ["TDB_EGRESS_CANARY_PORT"] = str(args.port)
        clean_env = replay_worker._runner_env(work_root)
        evidence = replay_worker._run_egress_canary(
            image=image,
            image_sha256=image_sha256,
            env=clean_env,
            execution_policy=policy,
        )
        if _sha256(image) != image_sha256:
            raise RuntimeError("runtime_sif_staged_digest_changed_after_canary")
        report["status"] = "SUCCESS"
        report["evidence"] = evidence
    except Exception as exc:  # Persist a fail-closed result for operator audit.
        report["error"] = _safe_error(exc)
    finally:
        report["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        _write_new(out, report)

    print(json.dumps({
        "status": report["status"],
        "job_id": report["job_id"],
        "hostname": report["hostname"],
        "out": str(out),
        "error": report["error"],
    }, sort_keys=True))
    return 0 if report["status"] == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
