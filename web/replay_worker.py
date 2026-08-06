#!/usr/bin/env python3
"""Official community-submission replay worker.

The worker is deliberately separate from the HTTP-facing recorder.  It consumes
content-addressed patches from a private store, checks them against a frozen suite
manifest, runs a fresh Harbor oracle replay with egress disabled, and emits an
append-only receipt.  The signer stops at ``receipt_ready``; a separate promoter
UID must re-verify that receipt before a row can become ``verified``.

The receipt proves which bytes and execution result were used.  It does *not* claim
that a task verifier is semantically complete; that separate false-accept question
is measured with the benchmark's labeled exploit corpus.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

import receipt_auth
import submit_result as submissions

MANIFEST_SCHEMA = "terminal-daily-replay-suite/v2"
POLICY_SCHEMA = "terminal-daily-replay-execution-policy/v1"
RECEIPT_SCHEMA = "terminal-daily-replay-receipt/v2"


class PermanentReplayError(ValueError):
    """A submission cannot become valid by retrying the same frozen suite."""


class TransientReplayError(RuntimeError):
    """Infrastructure failed before a trustworthy reward was produced."""


def _validate_container_runtime_policy(policy: Dict[str, Any], *,
                                       error_type: type[Exception]) -> None:
    kind = policy.get("container_runtime_kind")
    raw_path = policy.get("container_runtime_path")
    digest = policy.get("container_runtime_binary_sha256")
    version = policy.get("container_runtime_version")
    if kind not in {"apptainer", "singularity"}:
        raise error_type("execution policy lacks a pinned container runtime kind")
    if (not isinstance(raw_path, str) or not Path(raw_path).is_absolute()
            or Path(raw_path).name != kind or str(Path(raw_path)) != raw_path):
        raise error_type("execution policy container runtime path must be canonical absolute")
    if not re.fullmatch(r"[0-9a-f]{64}", str(digest or "")):
        raise error_type("execution policy lacks container runtime binary SHA-256")
    if not isinstance(version, str) or not version.strip() or len(version) > 500:
        raise error_type("execution policy lacks a bounded container runtime version")


def _validate_harbor_policy(policy: Dict[str, Any], *,
                            error_type: type[Exception]) -> None:
    binary_path = policy.get("harbor_binary_path")
    package_root = policy.get("harbor_package_root")
    if (not isinstance(binary_path, str) or not Path(binary_path).is_absolute()
            or Path(binary_path).name != "harbor"
            or str(Path(binary_path)) != binary_path):
        raise error_type("execution policy Harbor binary path must be canonical absolute")
    if (not isinstance(package_root, str) or not Path(package_root).is_absolute()
            or Path(package_root).name != "harbor"
            or str(Path(package_root)) != package_root):
        raise error_type("execution policy Harbor package root must be canonical absolute")
    if not re.fullmatch(r"[0-9a-f]{64}", str(policy.get("harbor_package_sha256", ""))):
        raise error_type("execution policy lacks Harbor package-tree SHA-256")


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def hash_tree(root: Path) -> str:
    """Hash relative path, mode, size and bytes of a symlink-free file tree."""
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise PermanentReplayError(f"not a directory: {root}")
    digest = hashlib.sha256(b"terminal-daily-tree/v1\0")
    for path in sorted(root.rglob("*"), key=lambda value: value.relative_to(root).as_posix()):
        if path.is_symlink():
            raise PermanentReplayError(f"trusted task contains a symlink: {path}")
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix().encode("utf-8")
        data = path.read_bytes()
        mode = path.stat().st_mode & 0o777
        digest.update(len(rel).to_bytes(4, "big"))
        digest.update(rel)
        digest.update(mode.to_bytes(2, "big"))
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def hash_harbor_package_tree(root: Path) -> str:
    """Hash all Harbor package bytes and reject unpinned bytecode caches."""
    root = root.resolve(strict=True)
    if not root.is_dir() or root.name != "harbor":
        raise TransientReplayError("harbor_package_root_invalid")
    digest = hashlib.sha256(b"terminal-daily-harbor-package/v1\0")
    paths = sorted(root.rglob("*"), key=lambda value: value.relative_to(root).as_posix())
    for path in paths:
        rel_path = path.relative_to(root)
        if path.is_symlink():
            raise TransientReplayError("harbor_package_contains_symlink")
        if "__pycache__" in rel_path.parts or path.suffix in {".pyc", ".pyo"}:
            raise TransientReplayError("harbor_package_contains_bytecode_cache")
        if not path.is_file():
            continue
        rel = rel_path.as_posix().encode("utf-8")
        data = path.read_bytes()
        mode = path.stat().st_mode & 0o777
        digest.update(len(rel).to_bytes(4, "big"))
        digest.update(rel)
        digest.update(mode.to_bytes(2, "big"))
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _copy_frozen_task(*, source: Path, destination: Path,
                      expected_sha256: str) -> str:
    """Copy a trusted task, then validate the copy before any task byte executes.

    ``symlinks=True`` is intentional: a symlink introduced during the copy race is
    preserved and rejected by :func:`hash_tree`, rather than followed outside the
    frozen task tree.  The source-side preflight in ``process_submission`` is not
    treated as authority for the later copy.
    """
    try:
        shutil.copytree(source, destination, symlinks=True)
        actual_sha256 = hash_tree(destination)
    except (OSError, shutil.Error, PermanentReplayError) as exc:
        raise TransientReplayError("trusted_copy_unavailable_or_unsafe") from exc
    if actual_sha256 != expected_sha256:
        raise TransientReplayError("trusted_copy_manifest_digest_mismatch")
    return actual_sha256


def _task_path(root: Path, task: str, mode: Optional[str] = None) -> Path:
    if not submissions._TASK_RE.fullmatch(task):
        raise PermanentReplayError("invalid task id in suite manifest")
    candidates: List[Path] = []
    if mode in {"live", "archive"}:
        candidates.append(root / mode / task)
    candidates.append(root / task)
    if mode is None:
        candidates.extend((root / "live" / task, root / "archive" / task))
    found = [path.resolve() for path in candidates if path.is_dir()]
    unique = list(dict.fromkeys(found))
    if len(unique) != 1:
        raise PermanentReplayError(
            f"expected one trusted package for {task}, found {len(unique)}"
        )
    try:
        unique[0].relative_to(root.resolve())
    except ValueError as exc:
        raise PermanentReplayError("trusted task escapes suite root") from exc
    return unique[0]


def _load_execution_policy(path: Path, trusted_keys: Path) -> Dict[str, Any]:
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PermanentReplayError("execution policy is unreadable") from exc
    if not isinstance(policy, dict) or policy.get("schema") != POLICY_SCHEMA:
        raise PermanentReplayError("unsupported replay execution policy")
    for key in ("runner_sha256", "harbor_binary_sha256", "harbor_package_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(policy.get(key, ""))):
            raise PermanentReplayError(f"execution policy lacks {key}")
    if policy.get("runner_sha256") != _runner_code_sha256():
        raise PermanentReplayError("execution policy does not pin this runner code")
    keys = receipt_auth.load_trusted_keys(trusted_keys)
    authority_key_id = policy.get("receipt_key_id")
    authority_key_sha = policy.get("receipt_public_key_sha256")
    if authority_key_id not in keys:
        raise PermanentReplayError("execution policy receipt key_id is not pinned")
    if keys[authority_key_id]["public_key_sha256"] != authority_key_sha:
        raise PermanentReplayError("execution policy public-key digest mismatch")
    if not isinstance(policy.get("harbor_version"), str) or not policy["harbor_version"].strip():
        raise PermanentReplayError("execution policy lacks a Harbor version")
    _validate_harbor_policy(policy, error_type=PermanentReplayError)
    if policy.get("backend") != "singularity":
        raise PermanentReplayError("only the canary-checked singularity backend is supported")
    if policy.get("network_policy") != "no-network":
        raise PermanentReplayError("execution policy must require no-network")
    if policy.get("canary_required") is not True:
        raise PermanentReplayError("execution policy must require an egress canary")
    _validate_container_runtime_policy(policy, error_type=PermanentReplayError)
    images = policy.get("task_images")
    if not isinstance(images, dict) or not images:
        raise PermanentReplayError("execution policy lacks pinned task image digests")
    for task, digest in images.items():
        if (not submissions._TASK_RE.fullmatch(str(task))
                or not re.fullmatch(r"[0-9a-f]{64}", str(digest))):
            raise PermanentReplayError("execution policy has an invalid task image pin")
    return policy


def freeze_manifest(*, date: str, membership: Path, trusted_root: Path,
                    execution_policy: Path, trusted_keys: Path,
                    out: Path) -> Dict[str, Any]:
    """Pin every trusted task and verifier tree before accepting replays."""
    try:
        dt.date.fromisoformat(date)
    except ValueError as exc:
        raise PermanentReplayError("manifest date must be ISO YYYY-MM-DD") from exc
    raw = json.loads(membership.read_text(encoding="utf-8"))
    policy = _load_execution_policy(execution_policy, trusted_keys)
    members = raw.get("tasks") if isinstance(raw, dict) else raw
    if not isinstance(members, list) or not members:
        raise PermanentReplayError("suite membership must be a non-empty list")
    frozen: List[Dict[str, Any]] = []
    seen = set()
    for item in members:
        task = item.get("task") if isinstance(item, dict) else item
        mode = item.get("mode") if isinstance(item, dict) else None
        if not isinstance(task, str) or task in seen:
            raise PermanentReplayError("suite task ids must be unique strings")
        seen.add(task)
        package = _task_path(trusted_root, task, mode)
        verifier = package / "tests"
        solution = package / "solution" / "solve.sh"
        if not verifier.is_dir() or not solution.is_file():
            raise PermanentReplayError(f"{task} is not a full trusted task package")
        image_sha256 = policy["task_images"].get(task)
        if not re.fullmatch(r"[0-9a-f]{64}", str(image_sha256 or "")):
            raise PermanentReplayError(f"{task} lacks a pinned runtime image digest")
        frozen.append({
            "task": task,
            "mode": mode,
            "task_sha256": hash_tree(package),
            "verifier_sha256": hash_tree(verifier),
            "image_sha256": image_sha256,
        })
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "date": date,
        "created_at": _utc_now(),
        "execution_policy": policy,
        "tasks": frozen,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    try:
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError as exc:
        raise PermanentReplayError("frozen manifest already exists; refusing overwrite") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return manifest


def load_manifest(path: Path) -> tuple[Dict[str, Any], str, Dict[str, Dict[str, Any]]]:
    payload = path.read_bytes()
    data = json.loads(payload)
    if data.get("schema") != MANIFEST_SCHEMA:
        raise PermanentReplayError("unsupported replay manifest schema")
    try:
        dt.date.fromisoformat(data["date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PermanentReplayError("invalid replay manifest date") from exc
    policy = data.get("execution_policy")
    if not isinstance(policy, dict) or policy.get("schema") != POLICY_SCHEMA:
        raise PermanentReplayError("replay manifest lacks an execution policy")
    for key in ("runner_sha256", "harbor_binary_sha256", "harbor_package_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(policy.get(key, ""))):
            raise PermanentReplayError(f"manifest execution policy lacks {key}")
    if (not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{2,127}",
                         str(policy.get("receipt_key_id", "")))
            or not re.fullmatch(r"[0-9a-f]{64}",
                                str(policy.get("receipt_public_key_sha256", "")))):
        raise PermanentReplayError("manifest execution policy lacks receipt authority pin")
    if (policy.get("backend") != "singularity"
            or policy.get("network_policy") != "no-network"
            or policy.get("canary_required") is not True):
        raise PermanentReplayError("manifest execution policy is not fail-closed")
    _validate_harbor_policy(policy, error_type=PermanentReplayError)
    _validate_container_runtime_policy(policy, error_type=PermanentReplayError)
    tasks: Dict[str, Dict[str, Any]] = {}
    for item in data.get("tasks", []):
        if not isinstance(item, dict) or not submissions._TASK_RE.fullmatch(str(item.get("task", ""))):
            raise PermanentReplayError("invalid replay manifest task entry")
        for key in ("task_sha256", "verifier_sha256", "image_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(item.get(key, ""))):
                raise PermanentReplayError(f"manifest task lacks {key}")
        if item["task"] in tasks:
            raise PermanentReplayError("duplicate task in replay manifest")
        if policy.get("task_images", {}).get(item["task"]) != item["image_sha256"]:
            raise PermanentReplayError("manifest image pin disagrees with execution policy")
        tasks[item["task"]] = item
    if not tasks:
        raise PermanentReplayError("empty replay manifest")
    return data, _sha256_bytes(payload), tasks


def _force_offline(task_toml: Path) -> None:
    """Set offline policy *only* inside ``[environment]`` and reparse it.

    This deliberately rejects ambiguous/duplicate tables instead of appending a
    top-level key that Harbor would ignore while an existing public network_mode
    remains effective.
    """
    text = task_toml.read_text(encoding="utf-8")
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise PermanentReplayError("task.toml is malformed") from exc
    if not isinstance(parsed.get("environment"), dict):
        raise PermanentReplayError("task.toml lacks [environment]")
    lines = text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines)
              if line.strip() == "[environment]"]
    if len(starts) != 1:
        raise PermanentReplayError("task.toml must contain one [environment] table")
    start = starts[0]
    end = next(
        (index for index in range(start + 1, len(lines))
         if re.match(r"^\s*\[", lines[index])),
        len(lines),
    )
    saw_allow = 0
    saw_mode = 0
    for index in range(start + 1, end):
        line = lines[index]
        allow_match = re.match(
            r"^(\s*allow_internet\s*=\s*)(true|false)(\s*(?:#.*)?)(\r?\n)?$",
            line,
        )
        if allow_match:
            saw_allow += 1
            lines[index] = (
                allow_match.group(1) + "false" + allow_match.group(3)
                + (allow_match.group(4) or "")
            )
            continue
        mode_match = re.match(
            r'^(\s*network_mode\s*=\s*)"(?:public|no-network|allowlist)"'
            r'(\s*(?:#.*)?)(\r?\n)?$',
            line,
        )
        if mode_match:
            saw_mode += 1
            lines[index] = (
                mode_match.group(1) + '"no-network"' + mode_match.group(2)
                + (mode_match.group(3) or "")
            )
    if saw_allow > 1 or saw_mode > 1:
        raise PermanentReplayError("task.toml contains duplicate network policy keys")
    if saw_allow == 0:
        if end > 0 and not lines[end - 1].endswith(("\n", "\r")):
            lines[end - 1] += "\n"
        lines.insert(end, "allow_internet = false\n")
    updated = "".join(lines)
    try:
        effective = tomllib.loads(updated)["environment"]
    except (tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
        raise PermanentReplayError("offline task.toml rewrite failed validation") from exc
    if effective.get("allow_internet") is not False:
        raise PermanentReplayError("offline task policy did not set allow_internet=false")
    if effective.get("network_mode", "no-network") != "no-network":
        raise PermanentReplayError("offline task policy left a public network_mode")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{task_toml.name}.", dir=str(task_toml.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, task_toml)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def _set_environment_docker_image(task_toml: Path, image: Path) -> None:
    text = task_toml.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines)
              if line.strip() == "[environment]"]
    if len(starts) != 1:
        raise PermanentReplayError("task.toml must contain one [environment] table")
    start = starts[0]
    end = next(
        (index for index in range(start + 1, len(lines))
         if re.match(r"^\s*\[", lines[index])), len(lines),
    )
    matches = []
    for index in range(start + 1, end):
        match = re.match(
            r"^(\s*docker_image\s*=\s*)\"(?:[^\"\\]|\\.)*\""
            r"(\s*(?:#.*)?)(\r?\n)?$",
            lines[index],
        )
        if match:
            matches.append((index, match))
    if len(matches) != 1:
        raise PermanentReplayError("task.toml must have one environment.docker_image")
    index, match = matches[0]
    lines[index] = (
        match.group(1) + json.dumps(str(image)) + match.group(2)
        + (match.group(3) or "")
    )
    updated = "".join(lines)
    try:
        effective = tomllib.loads(updated)["environment"]["docker_image"]
    except (tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
        raise PermanentReplayError("runtime image TOML rewrite failed") from exc
    if effective != str(image):
        raise PermanentReplayError("runtime image TOML rewrite did not take effect")
    task_toml.write_text(updated, encoding="utf-8")


def _pin_runtime_sif(*, run_task: Path, attempt: Path,
                     expected_sha256: str) -> tuple[Path, str]:
    """Copy the exact pre-execution SIF bytes into worker-private immutable storage."""
    try:
        config = tomllib.loads((run_task / "task.toml").read_text(encoding="utf-8"))
        image_ref = config["environment"]["docker_image"]
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
        raise PermanentReplayError("task lacks a structured runtime image reference") from exc
    if not isinstance(image_ref, str) or not image_ref.strip():
        raise PermanentReplayError("task runtime image reference is invalid")
    source = Path(image_ref)
    if not source.is_absolute():
        source = run_task / source
    if source.suffix.lower() != ".sif":
        raise PermanentReplayError("runtime image must be a prebuilt SIF artifact")
    try:
        source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise TransientReplayError("runtime_sif_source_unavailable") from exc
    destination_dir = attempt / "runtime-image"
    destination_dir.mkdir(mode=0o700)
    destination = destination_dir / "task.sif"
    digest = hashlib.sha256()
    try:
        source_stat = os.fstat(source_fd)
        if not stat.S_ISREG(source_stat.st_mode):
            raise PermanentReplayError("runtime SIF source is not a regular file")
        destination_fd = os.open(
            destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400,
        )
        try:
            with os.fdopen(source_fd, "rb", closefd=False) as source_handle, \
                    os.fdopen(destination_fd, "wb") as destination_handle:
                for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
                    digest.update(chunk)
                    destination_handle.write(chunk)
                destination_handle.flush()
                os.fsync(destination_handle.fileno())
        finally:
            # destination_fd is closed by fdopen on the success path.
            try:
                os.close(destination_fd)
            except OSError:
                pass
    finally:
        os.close(source_fd)
    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        raise TransientReplayError("runtime_sif_digest_mismatch_before_execution")
    os.chmod(destination, 0o400)
    _set_environment_docker_image(run_task / "task.toml", destination)
    return destination, actual_sha256


def _runner_code_sha256() -> str:
    digest = hashlib.sha256(b"terminal-daily-replay-runner/v2\0")
    root = Path(__file__).resolve().parents[1]
    paths = [
        Path(__file__).resolve(),
        root / "web" / "submit_result.py",
        root / "web" / "receipt_auth.py",
        *sorted((root / "terminal_daily_bench").rglob("*.py")),
    ]
    for path in paths:
        data = path.read_bytes()
        rel = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(rel).to_bytes(4, "big") + rel)
        digest.update(len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()


def _sha256_file(path: Path) -> str:
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or path.is_symlink():
        raise TransientReplayError("pinned runtime artifact is not a regular file")
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _result_snapshot_sha256(snapshot: Any) -> str:
    rel = str(snapshot.relative_path).encode("utf-8")
    data = bytes(snapshot.data)
    digest = hashlib.sha256(b"terminal-daily-harbor-result/v2\0")
    digest.update(len(rel).to_bytes(4, "big") + rel)
    digest.update(len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()


def _run_process(cmd: List[str], *, env: Dict[str, str], cwd: Path,
                 timeout_sec: int) -> tuple[int, str]:
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_sec)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
        raise TransientReplayError("harbor_timeout") from exc
    return process.returncode, (stdout or "") + (stderr or "")


def _runner_env(work_root: Path) -> Dict[str, str]:
    from terminal_daily_bench.harbor_score import clean_subprocess_env

    cleaned = clean_subprocess_env(os.environ)
    # Explicit allowlist, not a denylist: AWS/GCP/SSH/scheduler credentials often
    # have names that contain none of API_KEY/TOKEN/PASSWORD.
    allowed = (
        "PATH", "VIRTUAL_ENV", "LANG", "LC_ALL", "LC_CTYPE", "TZ",
        "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
    )
    env = {key: cleaned[key] for key in allowed if cleaned.get(key)}
    private_home = work_root / "worker-home"
    private_tmp = work_root / "worker-tmp"
    private_xdg = work_root / "worker-xdg"
    for path in (private_home, private_tmp, private_xdg):
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(path, 0o700)
    env.update({
        "HOME": str(private_home),
        "TMPDIR": str(private_tmp),
        "XDG_CACHE_HOME": str(private_xdg),
        "RCVH_DISABLE_INTERNET": "1",
        "TDB_SIF_CACHE": str(work_root / "cache" / "sif"),
        "TDB_OVERLAY_DIR": str(work_root / "cache" / "overlays"),
        "APPTAINER_CACHEDIR": str(work_root / "cache" / "apptainer"),
        "APPTAINER_TMPDIR": str(work_root / "cache" / "apptainer-tmp"),
        "SINGULARITY_CACHEDIR": str(work_root / "cache" / "apptainer"),
        "SINGULARITY_TMPDIR": str(work_root / "cache" / "apptainer-tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    for path in (
        work_root / "cache" / "sif", work_root / "cache" / "overlays",
        work_root / "cache" / "apptainer", work_root / "cache" / "apptainer-tmp",
    ):
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
    return env


def _worker_can_write(path: Path) -> bool:
    try:
        return os.access(path, os.W_OK, effective_ids=True)
    except (NotImplementedError, TypeError):
        return os.access(path, os.W_OK)


def _harbor_immutable_control_facts(*, binary: Path,
                                    package_root: Path) -> Dict[str, Any]:
    """Require Harbor code and every containing directory outside worker control."""
    worker_uid = os.geteuid()
    if worker_uid == 0:
        raise TransientReplayError("harbor_worker_must_not_be_root")
    inspected: List[Path] = [binary, package_root]
    inspected.extend(path for path in package_root.rglob("*"))
    for start in (binary.parent, package_root.parent):
        current = start
        while True:
            inspected.append(current)
            if current == current.parent:
                break
            current = current.parent
    unique = list(dict.fromkeys(inspected))
    regular_files = 0
    directories = 0
    for path in unique:
        try:
            path_stat = path.lstat()
        except OSError as exc:
            raise TransientReplayError("harbor_controlled_path_unavailable") from exc
        if path.is_symlink():
            raise TransientReplayError("harbor_controlled_path_contains_symlink")
        if stat.S_ISREG(path_stat.st_mode):
            regular_files += 1
        elif stat.S_ISDIR(path_stat.st_mode):
            directories += 1
        else:
            raise TransientReplayError("harbor_controlled_path_not_regular_or_directory")
        if path_stat.st_uid == worker_uid:
            raise TransientReplayError("harbor_code_owned_by_worker")
        if path_stat.st_mode & 0o022:
            raise TransientReplayError("harbor_code_group_world_writable")
        if _worker_can_write(path):
            raise TransientReplayError("harbor_code_writable_by_worker")
    return {
        "worker_euid": worker_uid,
        "worker_writable": False,
        "worker_owned_entries": 0,
        "symlinks": 0,
        "regular_files_checked": regular_files,
        "directories_checked": directories,
        "path_resolution": "absolute-no-path-no-symlink",
        "python_resolution": "pathfinder-without-import",
    }


def _resolved_harbor_package_root(env: Dict[str, str]) -> Path:
    """Resolve Harbor through Python's PathFinder without importing Harbor code."""
    probe = (
        "import importlib.machinery,json\n"
        "s=importlib.machinery.PathFinder.find_spec('harbor')\n"
        "print(json.dumps({'origin':None if s is None else s.origin,"
        "'locations':[] if s is None else list(s.submodule_search_locations or [])}))\n"
    )
    probe_env = dict(env)
    probe_env["PYTHONNOUSERSITE"] = "1"
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", probe], env=probe_env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            check=False, timeout=15,
        )
        payload = json.loads(completed.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise TransientReplayError("harbor_package_resolution_unavailable") from exc
    locations = payload.get("locations") if isinstance(payload, dict) else None
    origin = payload.get("origin") if isinstance(payload, dict) else None
    if completed.returncode != 0 or not isinstance(locations, list) or len(locations) != 1:
        raise TransientReplayError("harbor_package_resolution_ambiguous")
    try:
        root = Path(locations[0]).resolve(strict=True)
        resolved_origin = Path(origin).resolve(strict=True)
        resolved_origin.relative_to(root)
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise TransientReplayError("harbor_package_resolution_invalid") from exc
    return root


def _harbor_runtime_facts(policy: Dict[str, Any], *,
                          env: Dict[str, str]) -> Dict[str, Any]:
    _validate_harbor_policy(policy, error_type=TransientReplayError)
    binary = Path(policy["harbor_binary_path"])
    package_root = Path(policy["harbor_package_root"])
    try:
        if (binary.resolve(strict=True) != binary
                or package_root.resolve(strict=True) != package_root
                or binary.is_symlink() or package_root.is_symlink()):
            raise TransientReplayError("harbor_pinned_path_uses_symlink")
        binary_stat = binary.lstat()
    except OSError as exc:
        raise TransientReplayError("harbor_pinned_path_unavailable") from exc
    if not stat.S_ISREG(binary_stat.st_mode) or not binary_stat.st_mode & 0o111:
        raise TransientReplayError("harbor_binary_not_executable_regular_file")
    binary_sha256 = _sha256_file(binary)
    if binary_sha256 != policy["harbor_binary_sha256"]:
        raise TransientReplayError("harbor_binary_digest_mismatch")
    package_sha256 = hash_harbor_package_tree(package_root)
    if package_sha256 != policy["harbor_package_sha256"]:
        raise TransientReplayError("harbor_package_digest_mismatch")
    control = _harbor_immutable_control_facts(
        binary=binary, package_root=package_root,
    )
    try:
        with binary.open("rb") as handle:
            first_line = handle.readline(4096).decode("utf-8").strip()
        interpreter_argv = shlex.split(first_line[2:]) if first_line.startswith("#!") else []
        if (len(interpreter_argv) != 1
                or Path(interpreter_argv[0]).resolve(strict=True)
                != Path(sys.executable).resolve(strict=True)):
            raise TransientReplayError("harbor_launcher_interpreter_mismatch")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise TransientReplayError("harbor_launcher_interpreter_unavailable") from exc
    if _resolved_harbor_package_root(env) != package_root:
        raise TransientReplayError("harbor_import_resolution_mismatch")
    try:
        version_run = subprocess.run(
            [str(binary), "--version"], env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, check=False, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TransientReplayError("harbor_version_unavailable") from exc
    version = (version_run.stdout or "").strip().splitlines()
    if version_run.returncode != 0 or not version:
        raise TransientReplayError("harbor_version_unavailable")
    if version[0][:500] != policy["harbor_version"]:
        raise TransientReplayError("harbor_version_mismatch")
    return {
        "harbor_binary_path": str(binary),
        "harbor_binary_sha256": binary_sha256,
        "harbor_version": version[0][:500],
        "harbor_package_root": str(package_root),
        "harbor_package_sha256": package_sha256,
        "harbor_runtime_control": control,
    }


_CANARY_SCRIPT = (
    "import socket,sys\n"
    "s=socket.socket(); s.settimeout(5)\n"
    "try:\n"
    " s.connect((sys.argv[1],int(sys.argv[2]))); print('TDB_CANARY_CONNECTED'); sys.exit(0)\n"
    "except OSError as e:\n"
    " print('TDB_CANARY_BLOCKED:'+type(e).__name__); sys.exit(23)\n"
)


def _pinned_container_runtime_facts(policy: Dict[str, Any], *,
                                    env: Dict[str, str]) -> Dict[str, Any]:
    """Resolve no PATH entries: execute only the immutable policy-pinned binary."""
    _validate_container_runtime_policy(policy, error_type=TransientReplayError)
    raw_path = str(policy["container_runtime_path"])
    path = Path(raw_path)
    try:
        resolved = path.resolve(strict=True)
        file_stat = path.lstat()
        parent_stat = path.parent.lstat()
    except OSError as exc:
        raise TransientReplayError("container_runtime_pinned_path_unavailable") from exc
    if resolved != path or path.is_symlink() or path.parent.is_symlink():
        raise TransientReplayError("container_runtime_path_uses_symlink")
    if not stat.S_ISREG(file_stat.st_mode) or not file_stat.st_mode & 0o111:
        raise TransientReplayError("container_runtime_not_executable_regular_file")
    worker_uid = os.geteuid()
    if worker_uid == 0:
        raise TransientReplayError("container_runtime_worker_must_not_be_root")
    if file_stat.st_uid == worker_uid or parent_stat.st_uid == worker_uid:
        raise TransientReplayError("container_runtime_owned_by_worker")
    if file_stat.st_mode & 0o022 or parent_stat.st_mode & 0o022:
        raise TransientReplayError("container_runtime_or_parent_group_world_writable")
    # Covers ACLs and supplementary groups that mode/owner checks alone miss.
    if _worker_can_write(path) or _worker_can_write(path.parent):
        raise TransientReplayError("container_runtime_writable_by_worker")
    digest = _sha256_file(path)
    if digest != policy["container_runtime_binary_sha256"]:
        raise TransientReplayError("container_runtime_binary_digest_mismatch")
    try:
        version_run = subprocess.run(
            [raw_path, "--version"], env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, check=False, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TransientReplayError("container_runtime_version_unavailable") from exc
    lines = (version_run.stdout or "").strip().splitlines()
    if version_run.returncode != 0 or not lines:
        raise TransientReplayError("container_runtime_version_unavailable")
    version = lines[0][:500]
    if version != policy["container_runtime_version"]:
        raise TransientReplayError("container_runtime_version_mismatch")
    return {
        "container_runtime_kind": policy["container_runtime_kind"],
        "container_runtime_path": raw_path,
        "container_runtime_binary_sha256": digest,
        "container_runtime_version": version,
        "container_runtime_control": {
            "worker_euid": worker_uid,
            "binary_uid": file_stat.st_uid,
            "binary_mode": file_stat.st_mode & 0o777,
            "parent_uid": parent_stat.st_uid,
            "parent_mode": parent_stat.st_mode & 0o777,
            "worker_writable": False,
            "path_resolution": "absolute-no-path-no-symlink",
        },
    }


def _install_container_runtime_shims(*, runtime_path: Path,
                                     attempt: Path) -> Path:
    """Make Harbor's name-based lookup resolve to the pinned absolute runtime.

    The patched Harbor Singularity backend invokes ``singularity`` by name, while
    ancillary code may invoke ``apptainer``.  Both private PATH entries therefore
    resolve to the same already-validated binary; ambient PATH entries cannot win.
    """
    shim_dir = attempt / "runtime-bin"
    shim_dir.mkdir(mode=0o700)
    pinned = runtime_path.resolve(strict=True)
    if pinned != runtime_path:
        raise TransientReplayError("container_runtime_path_uses_symlink")
    for name in ("singularity", "apptainer"):
        shim = shim_dir / name
        os.symlink(str(pinned), shim)
        if shim.resolve(strict=True) != pinned:
            raise TransientReplayError("container_runtime_shim_resolution_failed")
    return shim_dir


def _install_harbor_shim(*, shim_dir: Path, harbor_path: Path) -> None:
    """Make eval's name-based Harbor lookup reach the policy-pinned launcher."""
    pinned = harbor_path.resolve(strict=True)
    if pinned != harbor_path:
        raise TransientReplayError("harbor_pinned_path_uses_symlink")
    shim = shim_dir / "harbor"
    os.symlink(str(pinned), shim)
    if shim.resolve(strict=True) != pinned:
        raise TransientReplayError("harbor_shim_resolution_failed")


def _run_egress_canary(*, image: Path, image_sha256: str, env: Dict[str, str],
                       execution_policy: Dict[str, Any],
                       timeout_sec: int = 45) -> Dict[str, Any]:
    host = (os.environ.get("TDB_EGRESS_CANARY_HOST") or "").strip()
    port_raw = (os.environ.get("TDB_EGRESS_CANARY_PORT") or "").strip()
    if not host or not port_raw.isdigit() or not 1 <= int(port_raw) <= 65535:
        raise TransientReplayError("egress_canary_endpoint_not_configured")
    runtime_facts = _pinned_container_runtime_facts(execution_policy, env=env)
    runtime_name = runtime_facts["container_runtime_path"]
    base = [
        runtime_name, "exec", "--cleanenv", "--containall", str(image),
        "python3", "-c", _CANARY_SCRIPT, host, port_raw,
    ]
    control_code, control_trace = _run_process(
        base, env=env, cwd=image.parent, timeout_sec=timeout_sec,
    )
    isolated = [
        runtime_name, "exec", "--cleanenv", "--containall", "--net", "--network",
        "none", str(image), "python3", "-c", _CANARY_SCRIPT, host, port_raw,
    ]
    isolated_code, isolated_trace = _run_process(
        isolated, env=env, cwd=image.parent, timeout_sec=timeout_sec,
    )
    control_reachable = control_code == 0 and "TDB_CANARY_CONNECTED" in control_trace
    isolated_blocked = (
        isolated_code == 23 and "TDB_CANARY_BLOCKED:" in isolated_trace
        and "TDB_CANARY_CONNECTED" not in isolated_trace
    )
    if not control_reachable:
        raise TransientReplayError("egress_canary_control_unreachable")
    if not isolated_blocked:
        raise TransientReplayError("egress_canary_isolation_not_proven")
    target_sha256 = _sha256_bytes(f"{host}:{port_raw}".encode("utf-8"))
    evidence = {
        "control_returncode": control_code,
        "isolated_returncode": isolated_code,
        "control_marker": "connected",
        "isolated_marker": "blocked",
        "target_sha256": target_sha256,
        "image_sha256": image_sha256,
        "container_runtime_binary_sha256": runtime_facts["container_runtime_binary_sha256"],
        "container_runtime_path": runtime_facts["container_runtime_path"],
        "container_runtime_version": runtime_facts["container_runtime_version"],
        "container_runtime_kind": runtime_facts["container_runtime_kind"],
    }
    return {
        "control_reachable": True,
        "isolated_blocked": True,
        "target_sha256": target_sha256,
        "image_sha256": image_sha256,
        "evidence_sha256": _sha256_bytes(_canonical_json(evidence)),
        **runtime_facts,
    }


def _authority_runtime_facts(*, signing_key: Path, store: Path, work_root: Path,
                             trusted_root: Path, manifest: Path,
                             trusted_keys: Path) -> Dict[str, Any]:
    """Reject obvious secret co-location and record auditable ownership facts.

    Mode bits are not presented as proof of a separate security principal.  The
    deployment must still run ingest/promoter and signer under distinct UIDs with
    read-only mounts; these facts make that external check possible.
    """
    key = signing_key.resolve(strict=True)
    key_stat = key.stat()
    if signing_key.is_symlink() or not key.is_file():
        raise PermanentReplayError("signing_key_must_be_regular_non_symlink")
    if key_stat.st_uid != os.geteuid() or key_stat.st_mode & 0o777 != 0o600:
        raise PermanentReplayError("signing_key_must_be_worker_owned_mode_0600")
    mutable_roots = {
        "submission_store": store.resolve(),
        "work_root": work_root.resolve(),
        "trusted_task_root": trusted_root.resolve(),
        "source_checkout": Path(__file__).resolve().parents[1],
    }
    for label, root in mutable_roots.items():
        try:
            key.relative_to(root)
        except ValueError:
            continue
        raise PermanentReplayError(f"signing_key_inside_{label}")

    def public_file_facts(path: Path) -> Dict[str, Any]:
        stat = path.lstat()
        if path.is_symlink() or not path.is_file() or stat.st_mode & 0o222:
            raise PermanentReplayError("authority_public_input_not_read_only")
        return {"uid": stat.st_uid, "mode": stat.st_mode & 0o777}

    return {
        "worker_euid": os.geteuid(),
        "signing_key_uid": key_stat.st_uid,
        "signing_key_mode": key_stat.st_mode & 0o777,
        "signing_key_outside_mutable_trees": True,
        "manifest": public_file_facts(manifest),
        "trusted_keys": public_file_facts(trusted_keys),
    }


def harbor_runner(*, entry: Dict[str, Any], patch: str, trusted_task: Path,
                  work_root: Path, timeout_sec: int,
                  execution_policy: Dict[str, Any],
                  expected_task_sha256: str,
                  expected_image_sha256: str) -> Dict[str, Any]:
    """Run the submitted patch through the public Harbor execution boundary."""
    from terminal_daily_bench.harbor_score import (
        authoritative_harbor_result_snapshot,
        reward_from_harbor_result_snapshot,
    )

    work_root.mkdir(parents=True, exist_ok=True)
    attempt = work_root / "runs" / f"{entry['id'][:16]}-{secrets.token_hex(6)}"
    run_task = attempt / "trusted-task"
    eval_work = attempt / "eval-work"
    attempt.mkdir(parents=True, mode=0o700)
    _copy_frozen_task(
        source=trusted_task, destination=run_task,
        expected_sha256=expected_task_sha256,
    )
    pinned_sif, pinned_image_sha256 = _pin_runtime_sif(
        run_task=run_task, attempt=attempt,
        expected_sha256=expected_image_sha256,
    )
    oracle_patch = run_task / "solution" / "oracle.patch"
    if not oracle_patch.is_file():
        raise PermanentReplayError("trusted_task_missing_oracle_patch")
    oracle_patch.write_text(patch, encoding="utf-8")
    _force_offline(run_task / "task.toml")

    result_path = attempt / "eval-result.json"
    cmd = [
        sys.executable, "-m", "terminal_daily_bench.eval",
        "--model", "oracle",
        "--task", str(run_task),
        "--out", str(result_path),
        "--work", str(eval_work),
        "--harbor-timeout", str(timeout_sec),
    ]
    started_at = _utc_now()
    child_env = _runner_env(work_root)
    runtime_before = _pinned_container_runtime_facts(execution_policy, env=child_env)
    # Harbor itself resolves `singularity` by name.  A private two-name shim makes
    # both Harbor and ancillary context extraction reach the exact absolute binary
    # validated above; the canary itself never uses PATH.
    runtime_shims = _install_container_runtime_shims(
        runtime_path=Path(runtime_before["container_runtime_path"]),
        attempt=attempt,
    )
    _install_harbor_shim(
        shim_dir=runtime_shims,
        harbor_path=Path(execution_policy["harbor_binary_path"]),
    )
    child_env["PATH"] = (
        str(runtime_shims)
        + os.pathsep + child_env["PATH"]
    )
    for runtime_name in ("singularity", "apptainer"):
        resolved_name = shutil.which(runtime_name, path=child_env["PATH"])
        if (resolved_name is None
                or Path(resolved_name).resolve(strict=True)
                != Path(runtime_before["container_runtime_path"])):
            raise TransientReplayError("container_runtime_path_lookup_not_pinned")
    selected_harbor = shutil.which("harbor", path=child_env["PATH"])
    if (selected_harbor is None
            or Path(selected_harbor).resolve(strict=True)
            != Path(execution_policy["harbor_binary_path"])):
        raise TransientReplayError("harbor_path_lookup_not_pinned")
    harbor_facts = _harbor_runtime_facts(execution_policy, env=child_env)
    if _sha256_file(pinned_sif) != pinned_image_sha256:
        raise TransientReplayError("runtime_sif_drift_before_execution")
    returncode, trace = _run_process(
        cmd, env=child_env, cwd=Path(__file__).resolve().parents[1],
        timeout_sec=timeout_sec + 60,
    )
    harbor_after = _harbor_runtime_facts(execution_policy, env=child_env)
    if harbor_after != harbor_facts:
        raise TransientReplayError("harbor_runtime_changed_during_replay")
    log_path = attempt / "worker.log"
    log_path.write_text(trace[-2_000_000:], encoding="utf-8")
    os.chmod(log_path, 0o600)
    if not result_path.is_file():
        raise TransientReplayError("eval_result_missing")
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TransientReplayError("eval_result_malformed") from exc
    if returncode != 0 or result.get("error"):
        raise TransientReplayError("harbor_replay_failed")
    try:
        jobs_dir = Path(result["jobs_dir"]).resolve(strict=True)
        jobs_dir.relative_to(attempt.resolve())
    except (KeyError, FileNotFoundError, ValueError) as exc:
        raise TransientReplayError("jobs_dir_outside_attempt") from exc
    result_snapshot = authoritative_harbor_result_snapshot(str(jobs_dir))
    if result_snapshot is None:
        raise TransientReplayError("harbor_result_missing_ambiguous_or_racy")
    independent_reward = reward_from_harbor_result_snapshot(result_snapshot)
    if independent_reward is None:
        raise TransientReplayError("harbor_reward_unreadable")
    reported_reward = float(result.get("reward"))
    if abs(reported_reward - float(independent_reward)) > 1e-12:
        raise TransientReplayError("reward_crosscheck_mismatch")
    image_value = result.get("image")
    if not isinstance(image_value, str) or not image_value:
        raise TransientReplayError("runtime_image_path_unavailable")
    image = Path(image_value)
    if not image.is_absolute():
        image = run_task / image
    try:
        image = image.resolve(strict=True)
    except FileNotFoundError as exc:
        raise TransientReplayError("runtime_image_artifact_unavailable") from exc
    if image != pinned_sif:
        raise TransientReplayError("runtime_image_path_not_worker_pinned_sif")
    image_sha256 = _sha256_file(image)
    if image_sha256 != expected_image_sha256:
        raise TransientReplayError("runtime_sif_drift_after_execution")
    canary = _run_egress_canary(
        image=image, image_sha256=image_sha256, env=child_env,
        execution_policy=execution_policy,
    )
    runtime_keys = (
        "container_runtime_kind", "container_runtime_path",
        "container_runtime_binary_sha256", "container_runtime_version",
        "container_runtime_control",
    )
    runtime_after = {key: canary[key] for key in runtime_keys}
    if runtime_after != runtime_before:
        raise TransientReplayError("container_runtime_changed_during_replay")
    return {
        "reward": float(independent_reward),
        "result_sha256": _result_snapshot_sha256(result_snapshot),
        "runner_sha256": _runner_code_sha256(),
        **harbor_facts,
        "image_sha256": image_sha256,
        "backend": "singularity",
        **runtime_after,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "network_isolation": {
            "requested": True,
            "enforced": True,
            "task_policy": "network_mode=no-network",
            "backend_capability": "singularity_disable_internet=true",
            "credentials_forwarded": False,
            "egress_canary": canary,
        },
        "private_attempt_dir": str(attempt),
    }


@contextlib.contextmanager
def _worker_lock(store: Path) -> Iterator[None]:
    store.mkdir(parents=True, exist_ok=True)
    path = store / ".replay-worker.lock"
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise TransientReplayError("another_replay_worker_is_active") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_receipt(store: Path, receipt: Dict[str, Any]) -> Path:
    receipt_dir = store / "receipts" / receipt["submission_id"]
    receipt_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    path = receipt_dir / f"{receipt['receipt_sha256']}.json"
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != receipt:
            raise TransientReplayError("receipt_digest_collision")
    else:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    return path


def _safe_error_code(exc: BaseException) -> str:
    raw = str(exc).strip().lower() or type(exc).__name__.lower()
    code = re.sub(r"[^a-z0-9_.-]+", "_", raw).strip("_.-")[:80]
    return code or "replay_error"


def process_submission(*, store: Path, manifest_data: Dict[str, Any],
                       suite_sha256: str, manifest_tasks: Dict[str, Dict[str, Any]],
                       manifest_path: Path,
                       trusted_root: Path, work_root: Path, entry: Dict[str, Any],
                       timeout_sec: int, signing_key: Path, key_id: str,
                       trusted_keys: Path,
                       runner: Callable[..., Dict[str, Any]] = harbor_runner) -> Dict[str, Any]:
    """Claim, validate, replay and receipt one queued submission."""
    sub_id = entry["id"]
    claimed = submissions.claim_for_replay(
        str(store), sub_id, lease_seconds=max(60, timeout_sec + 180)
    )
    attempt_id = claimed["attempt_id"]
    try:
        if entry.get("date") != manifest_data["date"]:
            raise PermanentReplayError("submission_date_not_in_frozen_suite")
        task_spec = manifest_tasks.get(str(entry.get("task")))
        if task_spec is None:
            raise PermanentReplayError("task_not_in_frozen_suite")
        try:
            patch = submissions._assert_entry_content(str(store), claimed)
        except ValueError as exc:
            raise PermanentReplayError("submission_content_binding_failed") from exc
        trusted_task = _task_path(
            trusted_root, task_spec["task"], task_spec.get("mode")
        )
        current_task_sha = hash_tree(trusted_task)
        current_verifier_sha = hash_tree(trusted_task / "tests")
        if current_task_sha != task_spec["task_sha256"]:
            raise TransientReplayError("trusted_task_drift")
        if current_verifier_sha != task_spec["verifier_sha256"]:
            raise TransientReplayError("trusted_verifier_drift")
        policy = manifest_data.get("execution_policy")
        if not isinstance(policy, dict):
            raise PermanentReplayError("manifest_execution_policy_missing")
        if policy.get("runner_sha256") != _runner_code_sha256():
            raise TransientReplayError("runner_code_drift")
        if key_id != policy.get("receipt_key_id"):
            raise PermanentReplayError("worker_key_id_not_pinned_by_manifest")
        trusted_authorities = receipt_auth.load_trusted_keys(trusted_keys)
        authority = trusted_authorities.get(key_id)
        if (authority is None or authority["public_key_sha256"]
                != policy.get("receipt_public_key_sha256")):
            raise PermanentReplayError("worker_public_key_not_pinned_by_manifest")
        authority_runtime = _authority_runtime_facts(
            signing_key=signing_key, store=store, work_root=work_root,
            trusted_root=trusted_root, manifest=manifest_path,
            trusted_keys=trusted_keys,
        )
        if policy.get("task_images", {}).get(entry["task"]) != task_spec["image_sha256"]:
            raise PermanentReplayError("manifest_task_image_binding_mismatch")
        run_result = runner(
            entry=claimed,
            patch=patch,
            trusted_task=trusted_task,
            work_root=work_root,
            timeout_sec=timeout_sec,
            execution_policy=policy,
            expected_task_sha256=task_spec["task_sha256"],
            expected_image_sha256=task_spec["image_sha256"],
        )
        run_result.pop("private_attempt_dir", None)
        required_run = (
            "reward", "result_sha256", "runner_sha256", "harbor_binary_path",
            "harbor_binary_sha256", "harbor_version", "harbor_package_root",
            "harbor_package_sha256", "harbor_runtime_control",
            "image_sha256", "backend", "started_at",
            "finished_at", "network_isolation", "container_runtime_kind",
            "container_runtime_path", "container_runtime_binary_sha256",
            "container_runtime_version", "container_runtime_control",
        )
        if any(run_result.get(key) is None for key in required_run):
            raise TransientReplayError("runner_returned_incomplete_evidence")
        for key in (
            "runner_sha256", "harbor_binary_path", "harbor_binary_sha256",
            "harbor_version", "harbor_package_root", "harbor_package_sha256",
            "backend",
        ):
            if run_result.get(key) != policy.get(key):
                raise TransientReplayError(f"runtime_{key}_drift")
        for key in (
            "container_runtime_kind", "container_runtime_path",
            "container_runtime_binary_sha256", "container_runtime_version",
        ):
            if run_result.get(key) != policy.get(key):
                raise TransientReplayError(f"runtime_{key}_drift")
        if run_result.get("image_sha256") != task_spec["image_sha256"]:
            raise TransientReplayError("runtime_image_digest_drift")
        submissions._require_network_evidence(run_result)
        execution_policy_sha256 = _sha256_bytes(_canonical_json(policy))
        signed_body: Dict[str, Any] = {
            **run_result,
            "schema": RECEIPT_SCHEMA,
            "submission_id": sub_id,
            "attempt_id": attempt_id,
            "date": entry["date"],
            "task": entry["task"],
            "patch_sha256": entry["patch_sha256"],
            "suite_sha256": suite_sha256,
            "task_sha256": task_spec["task_sha256"],
            "verifier_sha256": task_spec["verifier_sha256"],
            "execution_policy_sha256": execution_policy_sha256,
            "authority_runtime": authority_runtime,
        }
        signature = receipt_auth.sign_body(
            signed_body, private_key=signing_key, key_id=key_id,
            trusted_keys=trusted_keys,
        )
        receipt: Dict[str, Any] = {**signed_body, "signature": signature}
        receipt["receipt_sha256"] = receipt_auth.receipt_sha256(receipt)
        receipt_path = _write_receipt(store, receipt)
        staged = submissions.stage_signed_receipt(
            str(store), sub_id, receipt, attempt_id=attempt_id,
            trusted_keys=trusted_keys, manifest_path=manifest_path,
        )
        return {
            "id": sub_id,
            "status": staged["verify_status"],
            "reward": None,
            "receipt": str(receipt_path),
        }
    except PermanentReplayError as exc:
        failed = submissions.mark_replay_failure(
            str(store), sub_id, rejected=True, code=_safe_error_code(exc),
            attempt_id=attempt_id,
        )
        return {"id": sub_id, "status": failed["verify_status"],
                "error": failed["last_error"]}
    except Exception as exc:  # fail closed; a missing proof never becomes a zero score
        failed = submissions.mark_replay_failure(
            str(store), sub_id, rejected=False, code=_safe_error_code(exc),
            attempt_id=attempt_id,
        )
        return {"id": sub_id, "status": failed["verify_status"],
                "error": failed["last_error"]}


def run_queue(*, store: Path, manifest: Path, trusted_root: Path, work_root: Path,
              timeout_sec: int = 1800, limit: Optional[int] = None,
              retry_errors: bool = False, signing_key: Path,
              key_id: str, trusted_keys: Path,
              runner: Callable[..., Dict[str, Any]] = harbor_runner) -> List[Dict[str, Any]]:
    manifest_data, suite_sha256, manifest_tasks = load_manifest(manifest)
    eligible = {"pending", "error"} if retry_errors else {"pending"}
    with _worker_lock(store):
        submissions.recover_expired_leases(str(store))
        queue = [entry for entry in submissions.iter_entries(str(store))
                 if entry.get("verify_status") in eligible]
        if limit is not None:
            queue = queue[:max(0, limit)]
        return [
            process_submission(
                store=store,
                manifest_data=manifest_data,
                suite_sha256=suite_sha256,
                manifest_tasks=manifest_tasks,
                manifest_path=manifest,
                trusted_root=trusted_root,
                work_root=work_root,
                entry=entry,
                timeout_sec=timeout_sec,
                signing_key=signing_key,
                key_id=key_id,
                trusted_keys=trusted_keys,
                runner=runner,
            )
            for entry in queue
        ]


def _outside_home(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(Path.home().resolve())
    except ValueError:
        return resolved
    raise SystemExit(f"official replay data must not live under HOME: {resolved}")


def _main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    freeze = commands.add_parser("freeze", help="pin a trusted suite before replay")
    freeze.add_argument("--date", required=True)
    freeze.add_argument("--membership", type=Path, required=True)
    freeze.add_argument("--trusted-root", type=Path, required=True)
    freeze.add_argument("--execution-policy", type=Path, required=True)
    freeze.add_argument("--trusted-keys", type=Path, required=True)
    freeze.add_argument("--out", type=Path, required=True)

    run = commands.add_parser("run", help="process pending submissions")
    run.add_argument("--store", type=Path, required=True)
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--trusted-root", type=Path, required=True)
    run.add_argument("--work-root", type=Path, required=True)
    run.add_argument("--timeout", type=int, default=1800)
    run.add_argument("--limit", type=int)
    run.add_argument("--retry-errors", action="store_true")
    run.add_argument("--signing-key", type=Path, required=True)
    run.add_argument("--key-id", required=True)
    run.add_argument("--trusted-keys", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "freeze":
        result = freeze_manifest(
            date=args.date,
            membership=args.membership,
            trusted_root=args.trusted_root,
            execution_policy=args.execution_policy,
            trusted_keys=args.trusted_keys,
            out=args.out,
        )
        print(json.dumps({"date": result["date"], "tasks": len(result["tasks"]),
                          "out": str(args.out)}, indent=2))
        return 0

    store = _outside_home(args.store)
    work_root = _outside_home(args.work_root)
    results = run_queue(
        store=store,
        manifest=args.manifest.resolve(),
        trusted_root=args.trusted_root.resolve(),
        work_root=work_root,
        timeout_sec=args.timeout,
        limit=args.limit,
        retry_errors=args.retry_errors,
        signing_key=args.signing_key.resolve(),
        key_id=args.key_id,
        trusted_keys=args.trusted_keys.resolve(),
    )
    print(json.dumps({"processed": len(results), "results": results}, indent=2))
    return 1 if any(item["status"] == "error" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(_main())
