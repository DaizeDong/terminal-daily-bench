#!/usr/bin/env python3
"""Community result submission + un-gameable ingest for the Terminal Daily leaderboard.

A community member runs the day's task set with their own model/scaffold; the harness
POSTs one submission record per (model, task) cell here. The IRON discipline: a
submitted ``reward_claimed`` is ADVISORY ONLY. Nothing a submitter sends is ever read
as a score — only ``verified_reward``, written by a replay of the submitted PATCH
through the execution gate, counts toward any rate.

DEPLOYMENT NOTE — read this before quoting any property of this module.  The replay
worker is implemented in ``web/replay_worker.py`` but a source file is not evidence
that an official worker is deployed.  A submission remains in the separate unranked
queue until an execution receipt exists.  Never describe a pending row as replayed,
failed, or safe.

Flow:
  1. ``validate(sub)``  — schema + required fields + patch present.
  2. ``record(sub)``    — store the patch by SHA-256 and append a pending queue row.
  3. ``replay_worker``  — pin suite/task/verifier bytes, replay offline on a compute
                          node, and emit an append-only receipt.
  4. ``stage_signed_receipt`` — leave the signed result unranked for a separate
                                promoter identity.
  5. ``promote_ready_receipt`` — re-verify and promote under a non-signer UID.
  6. ``rebuild_leaderboard`` — emit verified ranking + pending review separately.

CLI:
  python submit_result.py validate  < submission.json
  python submit_result.py record    < submission.json   [--store DIR]
  python submit_result.py promote    --store DIR --id ID --manifest FILE \
                                     --trusted-keys FILE
  python submit_result.py rebuild    --store DIR --out leaderboard_data.json
"""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import json
import math
import sys
import hashlib
import os
import re
import secrets
import shlex
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import receipt_auth

REQUIRED = (
    "date", "submitter", "model", "model_build", "scaffold",
    "harness_version", "task", "patch",
)
STORE_DEFAULT = "community_submissions"
MAX_PATCH_BYTES = 2 * 1024 * 1024
MAX_LABEL_CHARS = 200
VERIFY_STATES = frozenset({
    "pending", "running", "receipt_ready", "verified", "rejected", "error",
})
_TASK_RE = re.compile(r"^td-[a-z0-9]{8,64}$")
_AUTH_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:@/-]{1,199}$")
RECEIPT_SCHEMA = "terminal-daily-replay-receipt/v2"
MANIFEST_SCHEMA = "terminal-daily-replay-suite/v2"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _patch_paths(patch: str) -> List[str]:
    """Return every path named by a git patch, rejecting malformed headers."""
    paths: List[str] = []
    prefixes = ("diff --git ", "--- ", "+++ ", "rename from ", "rename to ",
                "copy from ", "copy to ")
    for line in patch.splitlines():
        prefix = next((item for item in prefixes if line.startswith(item)), None)
        if prefix is None:
            continue
        try:
            tokens = shlex.split(line[len(prefix):])
        except ValueError as exc:
            raise ValueError(f"malformed patch path header: {exc}") from exc
        if prefix == "diff --git ":
            if len(tokens) != 2:
                raise ValueError("malformed diff --git header")
            paths.extend(tokens)
        elif tokens:
            paths.append(tokens[0])
    return paths


def _normalise_patch_path(raw: str) -> Optional[str]:
    value = raw.strip()
    if value == "/dev/null":
        return None
    if value.startswith(("a/", "b/")):
        value = value[2:]
    value = value.replace("\\", "/")
    parts = [part for part in value.split("/") if part not in ("", ".")]
    if value.startswith("/") or not parts or ".." in parts:
        raise ValueError(f"unsafe patch path: {raw!r}")
    if parts[0] in {".git", ".gitmodules"} or ".git" in parts:
        raise ValueError(f"git metadata may not be edited: {raw!r}")
    return "/".join(parts)


def _is_test_path(path: str) -> bool:
    parts = path.lower().split("/")
    name = parts[-1]
    return (
        any(part in {"test", "tests", "__tests__", "testing"} for part in parts[:-1])
        or name.startswith("test_")
        or name.endswith(("_test.py", ".spec.js", ".spec.ts", ".test.js", ".test.ts"))
        or name in {"conftest.py", "pytest.ini"}
    )


def validate(sub: Dict[str, Any]) -> List[str]:
    """Return a list of problems ([] = valid). Structural only; trust nothing semantic."""
    errs: List[str] = []
    if not isinstance(sub, dict):
        return ["submission must be a JSON object"]
    for k in REQUIRED:
        if not sub.get(k):
            errs.append(f"missing required field: {k}")
    for key in ("date", "submitter", "model", "model_build", "scaffold",
                "harness_version", "task"):
        value = sub.get(key)
        if value is not None and not isinstance(value, str):
            errs.append(f"{key} must be a string")
        elif isinstance(value, str) and len(value) > MAX_LABEL_CHARS:
            errs.append(f"{key} is too long")
    try:
        dt.date.fromisoformat(str(sub.get("date", "")))
    except ValueError:
        errs.append("date must be ISO YYYY-MM-DD")
    patch = sub.get("patch")
    if patch and not isinstance(patch, str):
        errs.append("patch must be a unified-diff string")
    elif isinstance(patch, str):
        if len(patch.encode("utf-8")) > MAX_PATCH_BYTES:
            errs.append(f"patch exceeds {MAX_PATCH_BYTES} bytes")
        if "\x00" in patch:
            errs.append("patch contains a NUL byte")
        if "GIT binary patch" in patch:
            errs.append("binary patches are not accepted")
        try:
            paths = [p for raw in _patch_paths(patch)
                     if (p := _normalise_patch_path(raw)) is not None]
            if not paths:
                errs.append("patch has no parseable file path")
            touched_tests = sorted({p for p in paths if _is_test_path(p)})
            if touched_tests:
                errs.append("patch may not edit tests: " + ", ".join(touched_tests[:5]))
        except ValueError as exc:
            errs.append(str(exc))
    if not _TASK_RE.fullmatch(str(sub.get("task", ""))):
        errs.append("task must be a Terminal Daily task id (td-...)")
    # reward_claimed is advisory; it is NOT validated against anything — it is
    # overwritten by the re-scored verified_reward on ingest.
    return errs


def content_id(sub: Dict[str, Any], authenticated_submitter: str) -> str:
    """Content-addressed id of the submission (dedup + tamper-evidence)."""
    body = {k: sub.get(k) for k in REQUIRED}
    body["authenticated_submitter"] = authenticated_submitter
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def _cell_identity(entry: Dict[str, Any]) -> tuple:
    """One immutable community attempt per authenticated suite/model/harness cell."""
    return (
        entry.get("date"), entry.get("authenticated_submitter"),
        entry.get("model_build"), entry.get("harness_version"), entry.get("task"),
    )


@contextlib.contextmanager
def _locked_store(store: str) -> Iterator[Path]:
    root = Path(store)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".submissions.lock"
    with lock.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield root
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def iter_entries(store: str = STORE_DEFAULT) -> Iterator[Dict[str, Any]]:
    for path in sorted(Path(store).glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield json.loads(line)


def get_entry(store: str, sub_id: str) -> Optional[Dict[str, Any]]:
    return next((entry for entry in iter_entries(store) if entry.get("id") == sub_id), None)


def record(sub: Dict[str, Any], store: str = STORE_DEFAULT, *,
           authenticated_submitter: Optional[str] = None) -> Dict[str, Any]:
    """Persist one authenticated, immutable cell and enqueue it for replay.

    ``authenticated_submitter`` must come from the surrounding auth layer/CLI,
    never from the JSON body.  Labels such as model/scaffold remain self-reported
    and are marked as such on the community-only board.
    """
    errs = validate(sub)
    if errs:
        raise ValueError("invalid submission: " + "; ".join(errs))
    if not isinstance(authenticated_submitter, str) or not _AUTH_ID_RE.fullmatch(
        authenticated_submitter
    ):
        raise ValueError("authenticated_submitter must be supplied by a trusted auth layer")
    if "authenticated_submitter" in sub:
        raise ValueError("authenticated_submitter may not be supplied in the submission body")
    patch_bytes = sub["patch"].encode("utf-8")
    patch_sha256 = hashlib.sha256(patch_bytes).hexdigest()
    entry = {
        "id": content_id(sub, authenticated_submitter),
        "date": sub["date"], "submitter": sub["submitter"],
        "authenticated_submitter": authenticated_submitter,
        "model": sub["model"], "model_build": sub["model_build"],
        "scaffold": sub["scaffold"], "harness_version": sub["harness_version"],
        "task": sub["task"],
        "reward_claimed": sub.get("reward_claimed"),   # advisory only
        "patch_sha256": patch_sha256,
        "patch_bytes": len(patch_bytes),
        "received_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "verify_status": "pending",                    # until a node re-scores the patch
        "verified_reward": None,                       # the ONLY figure the board trusts
        "receipt_sha256": None,
        "claim_mismatch": None,
        "last_error": None,
        "attempt_count": 0,
        "attempt_id": None,
        "lease_expires_at": None,
        # Semantic verifier false-accept is measured by a labeled cheat corpus, not
        # inferred from the mere fact that a protected test process ran.
        "false_accept": None,
    }
    with _locked_store(store) as root:
        previous = get_entry(store, entry["id"])
        if previous is not None:
            return previous
        same_cell = [
            item for item in iter_entries(store)
            if _cell_identity(item) == _cell_identity(entry)
        ]
        if same_cell:
            raise ValueError(
                "a submission already exists for this authenticated "
                "suite/model-build/harness-version/task cell"
            )
        patch_dir = root / "patches"
        patch_dir.mkdir(mode=0o700, exist_ok=True)
        blob = patch_dir / f"{patch_sha256}.diff"
        try:
            fd = os.open(blob, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if blob.read_bytes() != patch_bytes:
                raise RuntimeError("content-addressed patch collision")
        else:
            with os.fdopen(fd, "wb") as handle:
                handle.write(patch_bytes)
                handle.flush()
                os.fsync(handle.fileno())
        queue = root / f"{sub['date']}.jsonl"
        with queue.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return entry


def load_patch(store: str, entry: Dict[str, Any]) -> str:
    """Load a queued patch and prove it still matches the recorded digest."""
    digest = str(entry.get("patch_sha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("submission has no valid patch digest")
    blob = Path(store) / "patches" / f"{digest}.diff"
    data = blob.read_bytes()
    if len(data) > MAX_PATCH_BYTES or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("stored patch failed its size/digest check")
    return data.decode("utf-8")


def _assert_entry_content(store: str, entry: Dict[str, Any]) -> str:
    """Recompute the authenticated content id from queue metadata + patch bytes."""
    patch = load_patch(store, entry)
    payload = {key: entry.get(key) for key in REQUIRED}
    payload["patch"] = patch
    auth_id = entry.get("authenticated_submitter")
    if not isinstance(auth_id, str) or content_id(payload, auth_id) != entry.get("id"):
        raise ValueError("submission queue metadata failed its content-address binding")
    problems = validate(payload)
    if problems:
        raise ValueError("stored submission no longer validates")
    return patch


def _rewrite_entry(store: str, sub_id: str, update: Dict[str, Any], *,
                   expected_status: Optional[set[str]] = None,
                   expected_attempt_id: Optional[str] = None) -> Dict[str, Any]:
    """Atomically compare-and-swap exactly one queue row."""
    with _locked_store(store):
        matches = 0
        updated: Optional[Dict[str, Any]] = None
        for path in sorted(Path(store).glob("*.jsonl")):
            lines = path.read_text(encoding="utf-8").splitlines()
            changed = False
            for index, line in enumerate(lines):
                entry = json.loads(line)
                if entry.get("id") != sub_id:
                    continue
                matches += 1
                if (expected_status is not None
                        and entry.get("verify_status") not in expected_status):
                    raise ValueError(
                        f"submission state changed: {entry.get('verify_status')!r}"
                    )
                if (expected_attempt_id is not None
                        and entry.get("attempt_id") != expected_attempt_id):
                    raise ValueError("replay attempt/lease token changed")
                entry.update(update)
                lines[index] = json.dumps(entry, sort_keys=True)
                updated = entry
                changed = True
            if changed:
                fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        handle.write("\n".join(lines) + "\n")
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(tmp_name, path)
                finally:
                    try:
                        os.unlink(tmp_name)
                    except FileNotFoundError:
                        pass
        if matches != 1 or updated is None:
            raise KeyError(f"expected one submission {sub_id!r}, found {matches}")
        return updated


def claim_for_replay(store: str, sub_id: str, *, lease_seconds: int = 2100) -> Dict[str, Any]:
    if lease_seconds < 60:
        raise ValueError("replay lease must be at least 60 seconds")
    now = dt.datetime.now(dt.timezone.utc)
    attempt_id = secrets.token_hex(16)
    current = get_entry(store, sub_id)
    if current is None:
        raise KeyError(sub_id)
    return _rewrite_entry(store, sub_id, {
        "verify_status": "running",
        "replay_started_at": now.isoformat(),
        "lease_expires_at": (now + dt.timedelta(seconds=lease_seconds)).isoformat(),
        "attempt_id": attempt_id,
        "attempt_count": int(current.get("attempt_count") or 0) + 1,
        "last_error": None,
    }, expected_status={"pending", "error"})


def recover_expired_leases(store: str, *, now: Optional[dt.datetime] = None) -> int:
    """Return crashed ``running`` attempts to pending without accepting a score."""
    current_time = now or dt.datetime.now(dt.timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=dt.timezone.utc)
    recovered = 0
    with _locked_store(store):
        for path in sorted(Path(store).glob("*.jsonl")):
            lines = path.read_text(encoding="utf-8").splitlines()
            changed = False
            for index, line in enumerate(lines):
                entry = json.loads(line)
                if entry.get("verify_status") != "running":
                    continue
                try:
                    expiry = dt.datetime.fromisoformat(str(entry["lease_expires_at"]))
                except (KeyError, TypeError, ValueError):
                    expiry = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=dt.timezone.utc)
                if expiry > current_time:
                    continue
                entry.update({
                    "verify_status": "pending",
                    "last_error": "lease_expired",
                    "attempt_id": None,
                    "lease_expires_at": None,
                    "replay_finished_at": current_time.isoformat(),
                })
                lines[index] = json.dumps(entry, sort_keys=True)
                recovered += 1
                changed = True
            if changed:
                fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        handle.write("\n".join(lines) + "\n")
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(tmp_name, path)
                finally:
                    try:
                        os.unlink(tmp_name)
                    except FileNotFoundError:
                        pass
    return recovered


def _load_pinned_manifest(path: Path) -> tuple[Dict[str, Any], str]:
    try:
        stat = path.lstat()
    except OSError as exc:
        raise ValueError("pinned replay manifest is unreadable") from exc
    if path.is_symlink() or not path.is_file() or stat.st_mode & 0o222:
        raise ValueError("pinned replay manifest must be a read-only regular file")
    try:
        payload = path.read_bytes()
        manifest = json.loads(payload)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("pinned replay manifest is unreadable") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("unsupported pinned replay manifest")
    return manifest, hashlib.sha256(payload).hexdigest()


def _require_network_evidence(receipt: Dict[str, Any]) -> None:
    network = receipt.get("network_isolation")
    if not isinstance(network, dict):
        raise ValueError("receipt lacks network-isolation evidence")
    required = {
        "requested": True,
        "enforced": True,
        "credentials_forwarded": False,
        "task_policy": "network_mode=no-network",
    }
    for key, expected in required.items():
        value = network.get(key)
        if ((isinstance(expected, bool) and value is not expected)
                or (not isinstance(expected, bool) and value != expected)):
            raise ValueError(f"receipt network evidence failed: {key}")
    canary = network.get("egress_canary")
    if not isinstance(canary, dict):
        raise ValueError("receipt lacks an egress canary")
    if canary.get("control_reachable") is not True:
        raise ValueError("egress canary control was not reachable")
    if canary.get("isolated_blocked") is not True:
        raise ValueError("egress canary did not prove the isolated cut")
    if canary.get("image_sha256") != receipt.get("image_sha256"):
        raise ValueError("egress canary ran against a different image")
    if (canary.get("container_runtime_binary_sha256")
            != receipt.get("container_runtime_binary_sha256")
            or canary.get("container_runtime_path")
            != receipt.get("container_runtime_path")):
        raise ValueError("egress canary used a different container runtime")
    for key in ("target_sha256", "evidence_sha256", "image_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(canary.get(key, ""))):
            raise ValueError(f"invalid egress-canary digest: {key}")


def _validate_receipt_evidence(store: str, sub_id: str, entry: Dict[str, Any],
                               receipt: Dict[str, Any], *, attempt_id: str,
                               trusted_keys: Path,
                               manifest_path: Path) -> tuple[float, str, str]:
    """Validate persisted authority evidence without changing queue state."""
    _assert_entry_content(store, entry)
    required = (
        "schema", "submission_id", "attempt_id", "date", "patch_sha256", "task",
        "suite_sha256", "task_sha256", "verifier_sha256", "runner_sha256",
        "execution_policy_sha256", "harbor_binary_path", "harbor_binary_sha256",
        "harbor_version", "harbor_package_root", "harbor_package_sha256",
        "harbor_runtime_control",
        "image_sha256", "backend", "result_sha256", "reward", "started_at",
        "finished_at", "network_isolation", "signature", "receipt_sha256",
        "authority_runtime",
        "container_runtime_kind", "container_runtime_path",
        "container_runtime_binary_sha256", "container_runtime_version",
        "container_runtime_control",
    )
    missing = [key for key in required if receipt.get(key) is None]
    if missing:
        raise ValueError("receipt missing: " + ", ".join(missing))
    if (receipt["submission_id"] != sub_id
            or receipt["patch_sha256"] != entry["patch_sha256"]
            or receipt["attempt_id"] != attempt_id):
        raise ValueError("receipt is not bound to this submission/patch")
    if receipt["schema"] != RECEIPT_SCHEMA:
        raise ValueError("unsupported verification receipt schema")
    if receipt["task"] != entry["task"] or receipt["date"] != entry["date"]:
        raise ValueError("receipt task/date mismatch")
    for key in (
        "suite_sha256", "task_sha256", "verifier_sha256", "runner_sha256",
        "execution_policy_sha256", "harbor_binary_sha256", "harbor_package_sha256",
        "image_sha256", "result_sha256", "container_runtime_binary_sha256",
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", str(receipt[key])):
            raise ValueError(f"invalid receipt digest: {key}")
    if isinstance(receipt["reward"], bool):
        raise ValueError("verified reward must be numeric")
    reward = float(receipt["reward"])
    if not math.isfinite(reward) or not 0.0 <= reward <= 1.0:
        raise ValueError("verified reward must be in [0,1]")
    for key in ("started_at", "finished_at"):
        try:
            timestamp = dt.datetime.fromisoformat(str(receipt[key]))
        except ValueError as exc:
            raise ValueError(f"invalid receipt timestamp: {key}") from exc
        if timestamp.tzinfo is None:
            raise ValueError(f"receipt timestamp lacks timezone: {key}")

    manifest, manifest_sha = _load_pinned_manifest(manifest_path)
    if receipt["suite_sha256"] != manifest_sha or receipt["date"] != manifest.get("date"):
        raise ValueError("receipt is not bound to the pinned suite manifest")
    task_specs = [item for item in manifest.get("tasks", [])
                  if isinstance(item, dict) and item.get("task") == entry["task"]]
    if len(task_specs) != 1:
        raise ValueError("receipt task is not unique in the pinned suite manifest")
    task_spec = task_specs[0]
    for key in ("task_sha256", "verifier_sha256", "image_sha256"):
        if receipt[key] != task_spec.get(key):
            raise ValueError(f"receipt {key} disagrees with pinned suite manifest")
    policy = manifest.get("execution_policy")
    if not isinstance(policy, dict):
        raise ValueError("pinned suite lacks an execution policy")
    policy_sha = hashlib.sha256(_canonical_json(policy)).hexdigest()
    if receipt["execution_policy_sha256"] != policy_sha:
        raise ValueError("receipt execution-policy digest mismatch")
    policy_bindings = {
        "runner_sha256": "runner_sha256",
        "harbor_binary_path": "harbor_binary_path",
        "harbor_binary_sha256": "harbor_binary_sha256",
        "harbor_version": "harbor_version",
        "harbor_package_root": "harbor_package_root",
        "harbor_package_sha256": "harbor_package_sha256",
        "backend": "backend",
        "container_runtime_kind": "container_runtime_kind",
        "container_runtime_path": "container_runtime_path",
        "container_runtime_binary_sha256": "container_runtime_binary_sha256",
        "container_runtime_version": "container_runtime_version",
    }
    for receipt_key, policy_key in policy_bindings.items():
        if receipt[receipt_key] != policy.get(policy_key):
            raise ValueError(f"receipt {receipt_key} disagrees with execution policy")
    harbor_control = receipt.get("harbor_runtime_control")
    if (not isinstance(harbor_control, dict)
            or harbor_control.get("worker_writable") is not False
            or harbor_control.get("worker_owned_entries") != 0
            or harbor_control.get("symlinks") != 0
            or harbor_control.get("path_resolution") != "absolute-no-path-no-symlink"
            or harbor_control.get("python_resolution") != "pathfinder-without-import"
            or not isinstance(harbor_control.get("regular_files_checked"), int)
            or harbor_control["regular_files_checked"] < 2
            or not isinstance(harbor_control.get("directories_checked"), int)
            or harbor_control["directories_checked"] < 2):
        raise ValueError("receipt Harbor package control facts are invalid")
    runtime_control = receipt.get("container_runtime_control")
    if (not isinstance(runtime_control, dict)
            or runtime_control.get("worker_writable") is not False
            or runtime_control.get("path_resolution") != "absolute-no-path-no-symlink"
            or runtime_control.get("worker_euid") == runtime_control.get("binary_uid")
            or runtime_control.get("worker_euid") == runtime_control.get("parent_uid")
            or not isinstance(runtime_control.get("binary_mode"), int)
            or runtime_control["binary_mode"] & 0o022
            or not isinstance(runtime_control.get("parent_mode"), int)
            or runtime_control["parent_mode"] & 0o022):
        raise ValueError("receipt container runtime control facts are invalid")
    if policy.get("network_policy") != "no-network" or policy.get("canary_required") is not True:
        raise ValueError("pinned execution policy does not require offline canary proof")
    _require_network_evidence(receipt)

    authority_runtime = receipt.get("authority_runtime")
    if not isinstance(authority_runtime, dict):
        raise ValueError("receipt lacks authority runtime ownership facts")
    if (authority_runtime.get("worker_euid") != authority_runtime.get("signing_key_uid")
            or authority_runtime.get("signing_key_mode") != 0o600
            or authority_runtime.get("signing_key_outside_mutable_trees") is not True):
        raise ValueError("receipt signing-key runtime boundary is invalid")
    for name in ("manifest", "trusted_keys"):
        facts = authority_runtime.get(name)
        if (not isinstance(facts, dict) or not isinstance(facts.get("uid"), int)
                or not isinstance(facts.get("mode"), int)
                or facts["mode"] & 0o222):
            raise ValueError(f"receipt authority runtime facts invalid: {name}")

    signature = receipt.get("signature")
    if not isinstance(signature, dict) or signature.get("key_id") != policy.get("receipt_key_id"):
        raise ValueError("receipt signer is not pinned by the execution policy")
    trusted_authorities = receipt_auth.load_trusted_keys(trusted_keys)
    authority = trusted_authorities.get(str(signature["key_id"]))
    if (authority is None or authority["public_key_sha256"]
            != policy.get("receipt_public_key_sha256")):
        raise ValueError("receipt public key is not pinned by the execution policy")
    signed_body = {key: value for key, value in receipt.items()
                   if key not in {"signature", "receipt_sha256"}}
    receipt_auth.verify_body(signed_body, signature, trusted_keys=trusted_keys)
    digest_body = dict(receipt)
    supplied_digest = digest_body.pop("receipt_sha256", None)
    receipt_sha256 = receipt_auth.receipt_sha256(digest_body)
    if supplied_digest != receipt_sha256:
        raise ValueError("receipt digest mismatch")
    receipt_path = Path(store) / "receipts" / sub_id / f"{receipt_sha256}.json"
    try:
        persisted = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("verification receipt is not durably persisted") from exc
    if persisted != receipt:
        raise ValueError("persisted verification receipt mismatch")
    return reward, receipt_sha256, str(signature["key_id"])


def stage_signed_receipt(store: str, sub_id: str, receipt: Dict[str, Any], *,
                         attempt_id: str, trusted_keys: Path,
                         manifest_path: Path) -> Dict[str, Any]:
    """Persist a verified signature without granting leaderboard authority.

    This transition is deliberately callable by the signer.  It records only
    that a cryptographically valid receipt is ready for review; it never copies
    the receipt reward into the queue row.  A second process running under a
    different UID must call :func:`promote_ready_receipt`.
    """
    entry = get_entry(store, sub_id)
    if entry is None:
        raise KeyError(sub_id)
    if entry.get("verify_status") != "running" or entry.get("attempt_id") != attempt_id:
        raise ValueError("a signed receipt can only complete a claimed running row")
    _, receipt_sha256, key_id = _validate_receipt_evidence(
        store, sub_id, entry, receipt, attempt_id=attempt_id,
        trusted_keys=trusted_keys, manifest_path=manifest_path,
    )
    signer_euid = receipt.get("authority_runtime", {}).get("worker_euid")
    if not isinstance(signer_euid, int) or signer_euid < 0:
        raise ValueError("receipt lacks a valid signer UID")
    return _rewrite_entry(store, sub_id, {
        "verify_status": "receipt_ready",
        "verified_reward": None,
        "receipt_sha256": receipt_sha256,
        "receipt_key_id": key_id,
        "suite_sha256": receipt["suite_sha256"],
        "replay_provenance": "community_replay_signed_pending_promotion",
        "signer_euid": signer_euid,
        "promoter_euid": None,
        "replay_finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "last_error": None,
        "lease_expires_at": None,
    }, expected_status={"running"}, expected_attempt_id=attempt_id)


def _require_separate_promoter(receipt: Dict[str, Any]) -> tuple[int, int]:
    authority = receipt.get("authority_runtime")
    signer_euid = authority.get("worker_euid") if isinstance(authority, dict) else None
    promoter_euid = os.geteuid()
    if not isinstance(signer_euid, int) or signer_euid < 0:
        raise ValueError("receipt lacks a valid signer UID")
    if promoter_euid == 0:
        raise ValueError("receipt promoter must be an unprivileged service identity")
    if promoter_euid == signer_euid:
        raise ValueError("receipt signer and promoter must use distinct UIDs")
    return signer_euid, promoter_euid


def apply_verification(store: str, sub_id: str, receipt: Dict[str, Any], *,
                       attempt_id: str, trusted_keys: Path,
                       manifest_path: Path) -> Dict[str, Any]:
    """Promote a staged receipt under an identity distinct from its signer."""
    entry = get_entry(store, sub_id)
    if entry is None:
        raise KeyError(sub_id)
    if (entry.get("verify_status") != "receipt_ready"
            or entry.get("attempt_id") != attempt_id):
        raise ValueError("promotion requires a staged signed receipt")
    reward, receipt_sha256, key_id = _validate_receipt_evidence(
        store, sub_id, entry, receipt, attempt_id=attempt_id,
        trusted_keys=trusted_keys, manifest_path=manifest_path,
    )
    if (entry.get("receipt_sha256") != receipt_sha256
            or entry.get("receipt_key_id") != key_id
            or entry.get("suite_sha256") != receipt.get("suite_sha256")
            or entry.get("replay_provenance")
            != "community_replay_signed_pending_promotion"):
        raise ValueError("staged receipt metadata does not match authority evidence")
    signer_euid, promoter_euid = _require_separate_promoter(receipt)
    if entry.get("signer_euid") != signer_euid:
        raise ValueError("staged signer UID does not match authority evidence")
    claimed = entry.get("reward_claimed")
    mismatch = None
    if isinstance(claimed, (int, float)):
        mismatch = bool((float(claimed) >= 0.999) != (reward >= 0.999))
    return _rewrite_entry(store, sub_id, {
        "verify_status": "verified",
        "verified_reward": reward,
        "verified_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "receipt_sha256": receipt_sha256,
        "receipt_key_id": key_id,
        "suite_sha256": receipt["suite_sha256"],
        "replay_provenance": "community_replay_verified",
        "signer_euid": signer_euid,
        "promoter_euid": promoter_euid,
        "claim_mismatch": mismatch,
        "last_error": None,
        "false_accept": None,
        "lease_expires_at": None,
    }, expected_status={"receipt_ready"}, expected_attempt_id=attempt_id)


def promote_ready_receipt(store: str, sub_id: str, *, trusted_keys: Path,
                          manifest_path: Path) -> Dict[str, Any]:
    """Load and promote one staged receipt; intended for the promoter service."""
    entry = get_entry(store, sub_id)
    if entry is None:
        raise KeyError(sub_id)
    if entry.get("verify_status") != "receipt_ready":
        raise ValueError("submission has no signed receipt awaiting promotion")
    digest = str(entry.get("receipt_sha256", ""))
    attempt_id = str(entry.get("attempt_id", ""))
    if (not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not re.fullmatch(r"[0-9a-f]{32}", attempt_id)):
        raise ValueError("staged receipt reference is invalid")
    receipt_path = Path(store) / "receipts" / sub_id / f"{digest}.json"
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("staged verification receipt is unreadable") from exc
    return apply_verification(
        store, sub_id, receipt, attempt_id=attempt_id,
        trusted_keys=trusted_keys, manifest_path=manifest_path,
    )


def mark_replay_failure(store: str, sub_id: str, *, rejected: bool,
                        code: str, attempt_id: str) -> Dict[str, Any]:
    """Record a bounded public error code; raw verifier logs stay in private storage."""
    status = "rejected" if rejected else "error"
    if not re.fullmatch(r"[a-z0-9_.-]{1,80}", code):
        raise ValueError("failure code must be a short machine-readable token")
    return _rewrite_entry(store, sub_id, {
        "verify_status": status,
        "verified_reward": None,
        "last_error": code,
        "replay_finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "lease_expires_at": None,
    }, expected_status={"running"}, expected_attempt_id=attempt_id)


def apply_verified(store: str, sub_id: str, verified_reward: float) -> None:
    """Removed unsafe promotion seam; callers must provide a full replay receipt."""
    raise RuntimeError("direct score promotion is disabled; use promote_ready_receipt()")


def rebuild_leaderboard(store: str, out: str, *,
                        manifest_path: Optional[Path] = None,
                        trusted_keys: Optional[Path] = None) -> Dict[str, Any]:
    """Build a community-only board, ranking complete frozen-roster coverage only."""
    board = json.loads(Path(out).read_text(encoding="utf-8")) if Path(out).exists() else {"community": []}
    manifest: Optional[Dict[str, Any]] = None
    suite_sha256: Optional[str] = None
    expected_tasks: set[str] = set()
    target_date: Optional[str] = None
    if manifest_path is not None:
        manifest, suite_sha256 = _load_pinned_manifest(manifest_path)
        target_date = str(manifest.get("date"))
        expected_tasks = {
            str(item["task"]) for item in manifest.get("tasks", [])
            if isinstance(item, dict) and _TASK_RE.fullmatch(str(item.get("task", "")))
        }
        if not expected_tasks or len(expected_tasks) != len(manifest.get("tasks", [])):
            raise ValueError("pinned community roster is empty or contains duplicates")

    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for entry in iter_entries(store):
        if target_date is not None and entry.get("date") != target_date:
            continue  # never mix suites/dates into one table
        key = (
            entry.get("date"), entry.get("authenticated_submitter"),
            entry.get("model_build"), entry.get("harness_version"),
        )
        groups.setdefault(key, []).append(entry)

    verified_rows: List[Dict[str, Any]] = []
    pending_rows: List[Dict[str, Any]] = []
    for key, entries in sorted(groups.items(), key=lambda item: tuple(str(v) for v in item[0])):
        first = entries[0]
        identity = {
            "date": first.get("date"),
            "submitter": first.get("submitter"),
            "authenticated_submitter": first.get("authenticated_submitter"),
            "model": first.get("model"),
            "model_build": first.get("model_build"),
            "scaffold": first.get("scaffold"),
            "harness_version": first.get("harness_version"),
            "identity_source": "authenticated_submitter; model/scaffold labels self-reported",
            "provenance": "community_replay_verified",
        }
        by_task: Dict[str, List[Dict[str, Any]]] = {}
        for entry in entries:
            by_task.setdefault(str(entry.get("task")), []).append(entry)
        duplicate_tasks = sorted(task for task, rows in by_task.items() if len(rows) != 1)
        submitted_tasks = set(by_task)
        missing = sorted(expected_tasks - submitted_tasks) if expected_tasks else []
        extra = sorted(submitted_tasks - expected_tasks) if expected_tasks else []
        exact_roster = bool(expected_tasks) and not missing and not extra and not duplicate_tasks
        cells = [rows[0] for task, rows in by_task.items() if len(rows) == 1]
        identity_fields = (
            "submitter", "authenticated_submitter", "model", "model_build",
            "scaffold", "harness_version", "date",
        )
        labels_consistent = all(
            all(cell.get(field) == first.get(field) for field in identity_fields)
            for cell in cells
        )
        verified_rewards: Dict[str, float] = {}
        if manifest_path is not None and trusted_keys is not None:
            for cell in cells:
                if cell.get("verify_status") != "verified":
                    continue
                digest = str(cell.get("receipt_sha256", ""))
                if not re.fullmatch(r"[0-9a-f]{64}", digest):
                    continue
                receipt_path = Path(store) / "receipts" / str(cell["id"]) / f"{digest}.json"
                try:
                    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                    reward, _, key_id = _validate_receipt_evidence(
                        store, str(cell["id"]), cell, receipt,
                        attempt_id=str(cell.get("attempt_id", "")),
                        trusted_keys=trusted_keys, manifest_path=manifest_path,
                    )
                except (OSError, json.JSONDecodeError, ValueError):
                    continue
                if key_id != cell.get("receipt_key_id"):
                    continue
                authority = receipt.get("authority_runtime")
                signer_euid = (
                    authority.get("worker_euid") if isinstance(authority, dict) else None
                )
                promoter_euid = cell.get("promoter_euid")
                if (not isinstance(signer_euid, int)
                        or not isinstance(promoter_euid, int)
                        or signer_euid == promoter_euid
                        or cell.get("signer_euid") != signer_euid):
                    continue
                verified_rewards[str(cell["task"])] = reward
        all_verified = (
            exact_roster and labels_consistent and trusted_keys is not None
            and len(verified_rewards) == len(expected_tasks)
            and all(
                cell.get("suite_sha256") == suite_sha256
                and cell.get("replay_provenance") == "community_replay_verified"
                for cell in cells
            )
        )
        if all_verified:
            solved = sum(
                int(reward >= 0.999) for reward in verified_rewards.values()
            )
            row = {
                **identity,
                "suite_sha256": suite_sha256,
                "n": len(expected_tasks),
                "roster_n": len(expected_tasks),
                "coverage": 1.0,
                "solved": solved,
                "verified": len(cells),
                "claim_mismatches": sum(
                    int(cell.get("claim_mismatch") is True) for cell in cells
                ),
                "false_accept": None,
                "rate": round(solved / len(expected_tasks), 3),
                "status": "ranked-community-replay-verified",
            }
            verified_rows.append(row)
            continue

        counts = {state: 0 for state in VERIFY_STATES}
        for cell in cells:
            status = str(cell.get("verify_status", "error"))
            counts[status if status in VERIFY_STATES else "error"] += 1
        pending_rows.append({
            **identity,
            "provenance": "community_unranked",
            "status": "unranked",
            "reason": (
                "missing_pinned_roster" if not expected_tasks else
                "duplicate_cells" if duplicate_tasks else
                "inconsistent_self_reported_identity" if not labels_consistent else
                "incomplete_roster" if missing or extra else
                "signed_receipt_awaiting_separate_promoter"
                if any(cell.get("verify_status") == "receipt_ready" for cell in cells) else
                "replay_incomplete_or_authority_mismatch"
            ),
            "n": len(entries),
            "roster_n": len(expected_tasks) if expected_tasks else None,
            "coverage": (
                round(len(submitted_tasks & expected_tasks) / len(expected_tasks), 3)
                if expected_tasks else None
            ),
            "missing_tasks": missing,
            "extra_tasks": extra,
            "duplicate_tasks": duplicate_tasks,
            **counts,
        })

    verified_rows.sort(key=lambda row: (
        -row["rate"], str(row["model_build"]), str(row["harness_version"]),
    ))
    board["community_verified"] = verified_rows
    board["community_replay_verified"] = verified_rows
    board["community_pending"] = pending_rows
    board["community_suite"] = {
        "date": target_date,
        "suite_sha256": suite_sha256,
        "roster_n": len(expected_tasks) if expected_tasks else None,
        "ranking_requires_complete_roster": True,
        "official_results_included": False,
    }
    # Backward compatibility for old clients: community is now verified-only.
    board["community"] = verified_rows
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{out_path.name}.", dir=str(out_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(board, indent=1) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, out_path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
    return board


def _main(argv: List[str]) -> int:
    if not argv:
        print(__doc__); return 2
    cmd = argv[0]
    store = STORE_DEFAULT
    if "--store" in argv:
        store = argv[argv.index("--store") + 1]
    if cmd == "validate":
        sub = json.load(sys.stdin)
        errs = validate(sub)
        print(json.dumps({"valid": not errs, "errors": errs}, indent=1))
        return 0 if not errs else 1
    if cmd == "record":
        sub = json.load(sys.stdin)
        if "--authenticated-submitter" not in argv:
            raise SystemExit("record requires --authenticated-submitter from the auth layer")
        auth_id = argv[argv.index("--authenticated-submitter") + 1]
        print(json.dumps(record(sub, store, authenticated_submitter=auth_id), indent=1))
        return 0
    if cmd == "rebuild":
        out = argv[argv.index("--out") + 1] if "--out" in argv else "leaderboard_data.json"
        if "--manifest" not in argv:
            raise SystemExit("rebuild requires --manifest for a frozen roster")
        if "--trusted-keys" not in argv:
            raise SystemExit("rebuild requires --trusted-keys for receipt authority")
        manifest = Path(argv[argv.index("--manifest") + 1])
        keys = Path(argv[argv.index("--trusted-keys") + 1])
        b = rebuild_leaderboard(
            store, out, manifest_path=manifest, trusted_keys=keys,
        )
        print(f"community rows: {len(b.get('community', []))} -> {out}")
        return 0
    if cmd == "promote":
        if "--id" not in argv:
            raise SystemExit("promote requires --id")
        if "--manifest" not in argv:
            raise SystemExit("promote requires --manifest")
        if "--trusted-keys" not in argv:
            raise SystemExit("promote requires --trusted-keys")
        promoted = promote_ready_receipt(
            store, argv[argv.index("--id") + 1],
            manifest_path=Path(argv[argv.index("--manifest") + 1]),
            trusted_keys=Path(argv[argv.index("--trusted-keys") + 1]),
        )
        print(json.dumps({
            "id": promoted["id"],
            "status": promoted["verify_status"],
            "receipt_sha256": promoted["receipt_sha256"],
        }, indent=1))
        return 0
    print(f"unknown command {cmd!r}"); return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
