#!/usr/bin/env python3
"""Portable, fail-closed hand-off from the HPC replay signer to a promoter.

The replay signer and the promoter do not need a shared writable filesystem.
``export`` snapshots the staged queue row, patch, frozen suite and Ed25519 receipt
into a content-addressed directory.  ``verify`` reads every untrusted file through
one ``O_NOFOLLOW`` file descriptor, compares the bundled suite byte-for-byte with
an independently supplied suite, and reuses the normal receipt validator in a
private synthetic store.

Verification deliberately emits a *promotion candidate*, not a promoted score.
The candidate says ``eligible_for_leaderboard=false`` until an independent service
attests it and the publisher imports that attestation.  This module therefore
cannot turn a local dry run or a same-UID process into leaderboard authority.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

import submit_result as submissions


BUNDLE_SCHEMA = "terminal-daily-replay-promotion-bundle/v1"
SUBMISSION_SCHEMA = "terminal-daily-replay-submission-snapshot/v1"
PROMOTION_SCHEMA = "terminal-daily-replay-promotion-candidate/v1"
BUNDLE_DOMAIN = b"terminal-daily-replay-promotion-bundle/v1\0"

PAYLOAD_FILES = (
    "frozen-suite.json",
    "patch.diff",
    "receipt.json",
    "submission.json",
)
ALL_FILES = frozenset((*PAYLOAD_FILES, "bundle.json"))
MAX_BUNDLE_FILE_BYTES = submissions.MAX_PATCH_BYTES + 4 * 1024 * 1024

# A queue row is safe to export only while its schema remains explicitly known.
# Future recorder fields fail closed rather than accidentally shipping a secret.
EXPORTABLE_ENTRY_FIELDS = frozenset({
    "id", "date", "submitter", "authenticated_submitter", "model",
    "model_build", "scaffold", "harness_version", "task", "reward_claimed",
    "patch_sha256", "patch_bytes", "received_at", "verify_status",
    "verified_reward", "receipt_sha256", "receipt_key_id", "suite_sha256",
    "replay_provenance", "signer_euid", "promoter_euid", "claim_mismatch",
    "last_error", "attempt_count", "attempt_id", "lease_expires_at",
    "replay_started_at", "replay_finished_at", "verified_at", "false_accept",
})

# The portable snapshot is deliberately smaller than the recorder row.  In
# particular it never exports advisory claims, timestamps, lease state or raw
# diagnostic text.  These are the only fields needed to recompute the original
# content id and validate the staged receipt against independently pinned
# authority inputs.
SNAPSHOT_ENTRY_FIELDS = frozenset({
    "id", "date", "submitter", "authenticated_submitter", "model",
    "model_build", "scaffold", "harness_version", "task", "patch_sha256",
    "verify_status", "verified_reward", "receipt_sha256", "receipt_key_id",
    "suite_sha256", "replay_provenance", "signer_euid", "promoter_euid",
    "attempt_id",
})
CANONICAL_NULL_ENTRY_FIELDS = (
    "verified_reward", "promoter_euid", "claim_mismatch", "last_error",
    "lease_expires_at", "verified_at", "false_accept",
)
BUNDLE_FIELDS = frozenset({
    "schema", "created_at", "submission_id", "attempt_id", "suite_sha256",
    "receipt_sha256", "receipt_key_id", "reward", "files", "bundle_sha256",
})

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_RUN_ID_RE = re.compile(r"^[1-9][0-9]{0,39}$")
_ATTEMPT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_TASK_RE = re.compile(r"^td-[a-z0-9]{8,64}$")
_KEY_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{2,127}$")

DEPLOYMENT_CONTROLS = (
    "main_branch_protection_verified",
    "replay_promoter_environment_verified",
    "trusted_signer_registry_verified",
    "trusted_workflow_registry_verified",
    "artifact_attestation_importer_verified",
    "publisher_import_boundary_verified",
)


class ReceiptBundleError(ValueError):
    """A portable receipt bundle is incomplete, mutable, or inconsistent."""


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReceiptBundleError("portable receipt data is not canonical JSON") from exc


def _strict_json(payload: bytes, *, label: str) -> Any:
    def no_duplicates(pairs: Iterable[tuple[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ReceiptBundleError(f"{label} contains duplicate JSON key {key!r}")
            result[key] = value
        return result

    def no_constants(value: str) -> Any:
        raise ReceiptBundleError(
            f"{label} contains non-standard JSON constant {value!r}"
        )

    try:
        return json.loads(
            payload, object_pairs_hook=no_duplicates,
            parse_constant=no_constants,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptBundleError(f"{label} is not valid UTF-8 JSON") from exc


def _stable_file_bytes(path: Path, *, label: str,
                       limit: int = MAX_BUNDLE_FILE_BYTES) -> bytes:
    """Read one regular, non-symlink file from the same fd that was inspected."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ReceiptBundleError(f"{label} is unavailable or is a symlink") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ReceiptBundleError(f"{label} must be a single-link regular file")
        if before.st_size < 1 or before.st_size > limit:
            raise ReceiptBundleError(f"{label} has an invalid size")
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(fd)
        identity_before = (
            before.st_dev, before.st_ino, before.st_mode, before.st_nlink,
            before.st_size, before.st_mtime_ns, before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev, after.st_ino, after.st_mode, after.st_nlink,
            after.st_size, after.st_mtime_ns, after.st_ctime_ns,
        )
        if identity_before != identity_after or len(payload) != before.st_size:
            raise ReceiptBundleError(f"{label} changed while it was read")
        return payload
    finally:
        os.close(fd)


def _stable_bundle_files(root: Path) -> Dict[str, bytes]:
    # O_NOFOLLOW protects the final component.  Rejecting a difference between
    # the lexical absolute path and its resolved form also prevents an untrusted
    # checkout from smuggling an intermediate symlink into the bundle path.
    lexical_root = Path(os.path.abspath(root))
    try:
        resolved_root = root.resolve(strict=True)
        resolved_stat = resolved_root.stat()
    except OSError as exc:
        raise ReceiptBundleError("bundle root is unavailable or is a symlink") from exc
    if resolved_root != lexical_root:
        raise ReceiptBundleError(
            "bundle root path is non-canonical or contains a symlink"
        )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    try:
        root_fd = os.open(lexical_root, flags)
    except OSError as exc:
        raise ReceiptBundleError("bundle root is unavailable or is a symlink") from exc
    try:
        before = os.fstat(root_fd)
        if not stat.S_ISDIR(before.st_mode):
            raise ReceiptBundleError("bundle root is not a directory")
        if (before.st_dev, before.st_ino) != (resolved_stat.st_dev, resolved_stat.st_ino):
            raise ReceiptBundleError("bundle root changed before it was opened")
        names = set(os.listdir(root_fd))
        if names != ALL_FILES:
            missing = sorted(ALL_FILES - names)
            extra = sorted(names - ALL_FILES)
            raise ReceiptBundleError(
                f"bundle file set mismatch (missing={missing}, extra={extra})"
            )
        payloads: Dict[str, bytes] = {}
        for name in sorted(names):
            file_flags = (
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            try:
                fd = os.open(name, file_flags, dir_fd=root_fd)
            except OSError as exc:
                raise ReceiptBundleError(f"bundle file is unavailable: {name}") from exc
            try:
                file_before = os.fstat(fd)
                if (not stat.S_ISREG(file_before.st_mode)
                        or file_before.st_nlink != 1
                        or file_before.st_size < 1
                        or file_before.st_size > MAX_BUNDLE_FILE_BYTES):
                    raise ReceiptBundleError(f"unsafe bundle file: {name}")
                chunks = []
                remaining = MAX_BUNDLE_FILE_BYTES + 1
                while remaining:
                    chunk = os.read(fd, min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                payload = b"".join(chunks)
                file_after = os.fstat(fd)
                if (
                    (file_before.st_dev, file_before.st_ino, file_before.st_mode,
                     file_before.st_nlink, file_before.st_size,
                     file_before.st_mtime_ns, file_before.st_ctime_ns)
                    !=
                    (file_after.st_dev, file_after.st_ino, file_after.st_mode,
                     file_after.st_nlink, file_after.st_size,
                     file_after.st_mtime_ns, file_after.st_ctime_ns)
                    or len(payload) != file_before.st_size
                ):
                    raise ReceiptBundleError(f"bundle file changed while read: {name}")
                payloads[name] = payload
            finally:
                os.close(fd)
        after = os.fstat(root_fd)
        if ((before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns)):
            raise ReceiptBundleError("bundle directory changed while it was read")
        try:
            path_after = os.stat(lexical_root, follow_symlinks=False)
        except OSError as exc:
            raise ReceiptBundleError("bundle root changed while it was read") from exc
        if (path_after.st_dev, path_after.st_ino) != (before.st_dev, before.st_ino):
            raise ReceiptBundleError("bundle root changed while it was read")
        return payloads
    finally:
        os.close(root_fd)


def _write_exclusive(path: Path, payload: bytes, mode: int = 0o444) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _bundle_digest(body: Mapping[str, Any]) -> str:
    return hashlib.sha256(BUNDLE_DOMAIN + _canonical_json(body)).hexdigest()


def _file_record(payload: bytes) -> Dict[str, Any]:
    return {"sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}


def _validate_snapshot_entry(entry: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate every path-bearing field before materialising untrusted data."""
    if set(entry) != SNAPSHOT_ENTRY_FIELDS:
        missing = sorted(SNAPSHOT_ENTRY_FIELDS - set(entry))
        extra = sorted(set(entry) - SNAPSHOT_ENTRY_FIELDS)
        raise ReceiptBundleError(
            f"submission snapshot field mismatch (missing={missing}, extra={extra})"
        )
    checked = dict(entry)
    if not isinstance(checked["id"], str) or not _SHA256_RE.fullmatch(checked["id"]):
        raise ReceiptBundleError("submission snapshot id is invalid")
    date = checked["date"]
    if not isinstance(date, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", date):
        raise ReceiptBundleError("submission snapshot date is invalid")
    try:
        parsed_date = dt.date.fromisoformat(date)
    except ValueError as exc:
        raise ReceiptBundleError("submission snapshot date is invalid") from exc
    if parsed_date.isoformat() != date:
        raise ReceiptBundleError("submission snapshot date is not canonical")
    if not isinstance(checked["task"], str) or not _TASK_RE.fullmatch(checked["task"]):
        raise ReceiptBundleError("submission snapshot task is invalid")
    for name in ("patch_sha256", "receipt_sha256", "suite_sha256"):
        value = checked[name]
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise ReceiptBundleError(f"submission snapshot {name} is invalid")
    attempt_id = checked["attempt_id"]
    if not isinstance(attempt_id, str) or not _ATTEMPT_ID_RE.fullmatch(attempt_id):
        raise ReceiptBundleError("submission snapshot attempt id is invalid")
    key_id = checked["receipt_key_id"]
    if not isinstance(key_id, str) or not _KEY_ID_RE.fullmatch(key_id):
        raise ReceiptBundleError("submission snapshot receipt key id is invalid")
    for name in (
        "submitter", "authenticated_submitter", "model", "model_build",
        "scaffold", "harness_version",
    ):
        value = checked[name]
        if (not isinstance(value, str) or not value
                or len(value) > submissions.MAX_LABEL_CHARS or "\x00" in value):
            raise ReceiptBundleError(f"submission snapshot {name} is invalid")
    signer_euid = checked["signer_euid"]
    if (isinstance(signer_euid, bool) or not isinstance(signer_euid, int)
            or signer_euid < 0):
        raise ReceiptBundleError("submission snapshot signer UID is invalid")
    if (checked["verify_status"] != "receipt_ready"
            or checked["verified_reward"] is not None
            or checked["promoter_euid"] is not None
            or checked["replay_provenance"]
            != "community_replay_signed_pending_promotion"):
        raise ReceiptBundleError("submission snapshot is not an unpromoted receipt")
    return checked


def _export_snapshot_entry(entry: Mapping[str, Any]) -> Dict[str, Any]:
    unknown = sorted(set(entry) - EXPORTABLE_ENTRY_FIELDS)
    if unknown:
        raise ReceiptBundleError(f"queue row has unreviewed export fields: {unknown}")
    noncanonical = [
        name for name in CANONICAL_NULL_ENTRY_FIELDS if entry.get(name) is not None
    ]
    if noncanonical:
        raise ReceiptBundleError(
            "staged queue row retains non-canonical diagnostic/promotion state: "
            + ", ".join(noncanonical)
        )
    snapshot = {name: entry.get(name) for name in SNAPSHOT_ENTRY_FIELDS}
    return _validate_snapshot_entry(snapshot)


def export_bundle(*, store: Path, submission_id: str, manifest_path: Path,
                  trusted_keys: Path, out: Path) -> Dict[str, Any]:
    """Export one already-staged receipt without granting promotion authority."""
    entry = submissions.get_entry(str(store), submission_id)
    if entry is None:
        raise ReceiptBundleError("submission does not exist")
    snapshot_entry = _export_snapshot_entry(entry)
    receipt_digest = snapshot_entry["receipt_sha256"]
    receipt_path = store / "receipts" / snapshot_entry["id"] / f"{receipt_digest}.json"
    try:
        receipt = _strict_json(
            _stable_file_bytes(receipt_path, label="staged receipt"),
            label="staged receipt",
        )
    except ReceiptBundleError:
        raise
    if not isinstance(receipt, dict):
        raise ReceiptBundleError("staged receipt is not a JSON object")
    attempt_id = str(entry.get("attempt_id", ""))
    reward, checked_digest, key_id = submissions._validate_receipt_evidence(
        str(store), submission_id, entry, receipt, attempt_id=attempt_id,
        trusted_keys=trusted_keys, manifest_path=manifest_path,
    )
    if checked_digest != receipt_digest:
        raise ReceiptBundleError("staged receipt digest changed during export")
    signer_euid = receipt.get("authority_runtime", {}).get("worker_euid")
    if (snapshot_entry["receipt_key_id"] != key_id
            or snapshot_entry["suite_sha256"] != receipt.get("suite_sha256")
            or snapshot_entry["signer_euid"] != signer_euid):
        raise ReceiptBundleError(
            "staged queue metadata disagrees with signed receipt authority"
        )
    patch = submissions.load_patch(str(store), entry).encode("utf-8")
    suite = _stable_file_bytes(manifest_path, label="frozen suite")
    if hashlib.sha256(suite).hexdigest() != receipt.get("suite_sha256"):
        raise ReceiptBundleError("frozen suite is not the receipt-pinned suite")

    snapshot = {
        "schema": SUBMISSION_SCHEMA,
        "entry": snapshot_entry,
    }
    payloads = {
        "frozen-suite.json": suite,
        "patch.diff": patch,
        "receipt.json": _canonical_json(receipt) + b"\n",
        "submission.json": _canonical_json(snapshot) + b"\n",
    }
    body: Dict[str, Any] = {
        "schema": BUNDLE_SCHEMA,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "submission_id": submission_id,
        "attempt_id": attempt_id,
        "suite_sha256": receipt["suite_sha256"],
        "receipt_sha256": checked_digest,
        "receipt_key_id": key_id,
        "reward": reward,
        "files": {name: _file_record(payloads[name]) for name in PAYLOAD_FILES},
    }
    bundle = {**body, "bundle_sha256": _bundle_digest(body)}
    payloads["bundle.json"] = _canonical_json(bundle) + b"\n"

    if out.exists() or out.is_symlink():
        raise ReceiptBundleError("bundle output already exists")
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{out.name}.", dir=str(out.parent)))
    try:
        os.chmod(staging, 0o700)
        for name in sorted(payloads):
            _write_exclusive(staging / name, payloads[name])
        os.chmod(staging, 0o555)
        os.replace(staging, out)
    except Exception:
        os.chmod(staging, 0o700)
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return bundle


def _materialize_validation_store(*, root: Path, entry: Dict[str, Any],
                                  patch: bytes, receipt: Dict[str, Any],
                                  suite: bytes, trusted_keys: bytes) -> tuple[Path, Path, Path]:
    # This function writes paths derived from the snapshot.  Keep validation
    # inside the sink as defense in depth so a future caller cannot bypass it.
    entry = _validate_snapshot_entry(entry)
    store = root / "store"
    patch_dir = store / "patches"
    receipt_dir = store / "receipts" / str(entry["id"])
    patch_dir.mkdir(parents=True)
    receipt_dir.mkdir(parents=True)
    _write_exclusive(patch_dir / f"{entry['patch_sha256']}.diff", patch, 0o600)
    receipt_payload = json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    _write_exclusive(
        receipt_dir / f"{entry['receipt_sha256']}.json", receipt_payload, 0o600,
    )
    queue_payload = _canonical_json(entry) + b"\n"
    _write_exclusive(store / f"{entry['date']}.jsonl", queue_payload, 0o600)
    manifest_path = root / "frozen-suite.json"
    keys_path = root / "trusted-keys.json"
    _write_exclusive(manifest_path, suite)
    _write_exclusive(keys_path, trusted_keys)
    return store, manifest_path, keys_path


def _github_context(expected_repository: str) -> Dict[str, Any]:
    values = {
        "repository": os.environ.get("GITHUB_REPOSITORY", ""),
        "ref": os.environ.get("GITHUB_REF", ""),
        "source_commit": os.environ.get("GITHUB_SHA", ""),
        "workflow_commit": os.environ.get("TDB_AUTHORITY_WORKFLOW_SHA", ""),
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        "event_name": os.environ.get("GITHUB_EVENT_NAME", ""),
        # The workflow explicitly maps the runner context into this variable;
        # do not assume an undocumented/default runner environment variable.
        "runner_environment": os.environ.get("TDB_RUNNER_ENVIRONMENT", ""),
    }
    expected_workflow = (
        f"{expected_repository}/.github/workflows/promote-receipt.yml@refs/heads/main"
    )
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise ReceiptBundleError("independent verification requires GitHub Actions")
    if values["repository"] != expected_repository:
        raise ReceiptBundleError("GitHub promoter repository is not the pinned repository")
    if values["ref"] != "refs/heads/main" or values["workflow_ref"] != expected_workflow:
        raise ReceiptBundleError("GitHub promoter is not the main-branch workflow")
    if not _COMMIT_RE.fullmatch(values["source_commit"]):
        raise ReceiptBundleError("GitHub promoter source commit is invalid")
    if (not _COMMIT_RE.fullmatch(values["workflow_commit"])
            or values["workflow_commit"] != values["source_commit"]):
        raise ReceiptBundleError("GitHub promoter workflow commit is not source-pinned")
    if not _RUN_ID_RE.fullmatch(values["run_id"]):
        raise ReceiptBundleError("GitHub promoter run id is invalid")
    if not _RUN_ID_RE.fullmatch(values["run_attempt"]):
        raise ReceiptBundleError("GitHub promoter run attempt is invalid")
    if values["event_name"] != "workflow_dispatch":
        raise ReceiptBundleError("GitHub promoter event is not workflow_dispatch")
    if values["runner_environment"] != "github-hosted":
        raise ReceiptBundleError("GitHub promoter must use a GitHub-hosted runner")
    ambient_runner = os.environ.get("RUNNER_ENVIRONMENT")
    if ambient_runner and ambient_runner != values["runner_environment"]:
        raise ReceiptBundleError("GitHub runner environment facts disagree")
    return {"kind": "github_actions_keyless_candidate", **values}


def verify_bundle(*, bundle_root: Path, expected_manifest: Path,
                  trusted_keys: Path, expected_bundle_sha256: Optional[str] = None,
                  expected_repository: Optional[str] = None) -> Dict[str, Any]:
    """Verify a bundle and return a still-unranked promotion candidate."""
    payloads = _stable_bundle_files(bundle_root)
    bundle = _strict_json(payloads["bundle.json"], label="bundle manifest")
    if not isinstance(bundle, dict) or bundle.get("schema") != BUNDLE_SCHEMA:
        raise ReceiptBundleError("unsupported receipt bundle")
    if set(bundle) != BUNDLE_FIELDS:
        raise ReceiptBundleError("receipt bundle has an unreviewed manifest shape")
    for name in ("submission_id", "suite_sha256", "receipt_sha256", "bundle_sha256"):
        value = bundle.get(name)
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise ReceiptBundleError(f"receipt bundle {name} is invalid")
    attempt_value = bundle.get("attempt_id")
    if not isinstance(attempt_value, str) or not _ATTEMPT_ID_RE.fullmatch(attempt_value):
        raise ReceiptBundleError("receipt bundle attempt id is invalid")
    key_value = bundle.get("receipt_key_id")
    if not isinstance(key_value, str) or not _KEY_ID_RE.fullmatch(key_value):
        raise ReceiptBundleError("receipt bundle receipt key id is invalid")
    # JSON booleans compare equal to 0/1 in Python.  Export always writes a
    # finite floating-point reward, so require that exact representation before
    # any equality check with signed receipt evidence.
    reward_value = bundle.get("reward")
    if (not isinstance(reward_value, float) or isinstance(reward_value, bool)
            or not math.isfinite(reward_value) or not 0.0 <= reward_value <= 1.0):
        raise ReceiptBundleError("receipt bundle reward is invalid")
    if not isinstance(bundle.get("files"), dict):
        raise ReceiptBundleError("receipt bundle payload inventory is invalid")
    created_at = bundle.get("created_at")
    if not isinstance(created_at, str) or len(created_at) > 80:
        raise ReceiptBundleError("receipt bundle creation time is invalid")
    try:
        created_timestamp = dt.datetime.fromisoformat(created_at)
    except ValueError as exc:
        raise ReceiptBundleError("receipt bundle creation time is invalid") from exc
    if (created_timestamp.tzinfo is None
            or created_timestamp.utcoffset() != dt.timedelta(0)
            or created_timestamp.isoformat() != created_at):
        raise ReceiptBundleError(
            "receipt bundle creation time is not canonical UTC"
        )
    supplied_digest = bundle.get("bundle_sha256")
    body = {key: value for key, value in bundle.items() if key != "bundle_sha256"}
    actual_bundle_digest = _bundle_digest(body)
    if (not isinstance(supplied_digest, str)
            or not _SHA256_RE.fullmatch(supplied_digest)
            or supplied_digest != actual_bundle_digest):
        raise ReceiptBundleError("bundle content digest mismatch")
    if expected_bundle_sha256 is not None:
        if (not _SHA256_RE.fullmatch(expected_bundle_sha256)
                or expected_bundle_sha256 != actual_bundle_digest):
            raise ReceiptBundleError("bundle does not match the operator-pinned digest")
    records = bundle.get("files")
    if not isinstance(records, dict) or set(records) != set(PAYLOAD_FILES):
        raise ReceiptBundleError("bundle payload inventory is invalid")
    for name in PAYLOAD_FILES:
        record = records.get(name)
        expected = _file_record(payloads[name])
        if (not isinstance(record, dict) or set(record) != {"sha256", "size"}
                or not isinstance(record.get("sha256"), str)
                or not _SHA256_RE.fullmatch(record["sha256"])
                or type(record.get("size")) is not int
                or not 1 <= record["size"] <= MAX_BUNDLE_FILE_BYTES
                or record != expected):
            raise ReceiptBundleError(f"bundle payload digest mismatch: {name}")

    independently_pinned_suite = _stable_file_bytes(
        expected_manifest, label="independently pinned frozen suite",
    )
    if payloads["frozen-suite.json"] != independently_pinned_suite:
        raise ReceiptBundleError("bundled suite differs from the promoter-pinned suite")
    trusted_key_bytes = _stable_file_bytes(
        trusted_keys, label="independently pinned trusted keys",
    )
    receipt = _strict_json(payloads["receipt.json"], label="receipt")
    snapshot = _strict_json(payloads["submission.json"], label="submission snapshot")
    if not isinstance(receipt, dict):
        raise ReceiptBundleError("receipt is not a JSON object")
    if (not isinstance(snapshot, dict) or set(snapshot) != {"schema", "entry"}
            or snapshot.get("schema") != SUBMISSION_SCHEMA
            or not isinstance(snapshot.get("entry"), dict)):
        raise ReceiptBundleError("submission snapshot is invalid")
    # Validate ids, dates and digests before they can reach the temporary-store
    # path construction below.
    entry = _validate_snapshot_entry(snapshot["entry"])
    if (entry.get("id") != bundle.get("submission_id")
            or entry.get("attempt_id") != bundle.get("attempt_id")
            or entry.get("receipt_sha256") != bundle.get("receipt_sha256")
            or entry.get("suite_sha256") != bundle.get("suite_sha256")
            or entry.get("receipt_key_id") != bundle.get("receipt_key_id")):
        raise ReceiptBundleError("bundle and staged queue metadata disagree")
    if (entry.get("verify_status") != "receipt_ready"
            or entry.get("verified_reward") is not None
            or entry.get("promoter_euid") is not None
            or entry.get("replay_provenance")
            != "community_replay_signed_pending_promotion"):
        raise ReceiptBundleError("portable row is not an unpromoted staged receipt")

    with tempfile.TemporaryDirectory(prefix="tdb-promotion-verify-") as temp:
        store, manifest_path, key_path = _materialize_validation_store(
            root=Path(temp), entry=entry, patch=payloads["patch.diff"],
            receipt=receipt, suite=independently_pinned_suite,
            trusted_keys=trusted_key_bytes,
        )
        try:
            reward, receipt_digest, key_id = submissions._validate_receipt_evidence(
                str(store), str(entry["id"]), entry, receipt,
                attempt_id=str(entry["attempt_id"]), trusted_keys=key_path,
                manifest_path=manifest_path,
            )
        except (OSError, ValueError):
            raise ReceiptBundleError(
                "portable receipt failed independently pinned authority validation"
            ) from None
    if (receipt_digest != bundle.get("receipt_sha256")
            or key_id != bundle.get("receipt_key_id")
            or reward != bundle.get("reward")):
        raise ReceiptBundleError("bundle summary disagrees with receipt authority")
    signer_euid = receipt.get("authority_runtime", {}).get("worker_euid")
    if entry["signer_euid"] != signer_euid:
        raise ReceiptBundleError("staged signer UID disagrees with receipt authority")

    if expected_repository is None:
        verifier: Dict[str, Any] = {
            "kind": "local_diagnostic",
            "independent_authority": False,
        }
    else:
        verifier = _github_context(expected_repository)
        verifier["independent_authority"] = True
    return {
        "schema": PROMOTION_SCHEMA,
        "status": "receipt_validated_pending_external_attestation",
        "eligible_for_leaderboard": False,
        "attestation_required": "github_actions_artifact_attestation",
        "bundle_sha256": actual_bundle_digest,
        "submission_id": entry["id"],
        "attempt_id": entry["attempt_id"],
        "suite_sha256": receipt["suite_sha256"],
        "receipt_sha256": receipt_digest,
        "receipt_key_id": key_id,
        "reward": reward,
        "signer_euid": receipt["authority_runtime"]["worker_euid"],
        "verified_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "verifier": verifier,
        # This verifier has not queried or cryptographically established any of
        # the external deployment controls below.  A future importer must create
        # a separately attested promotion record after verifying all of them;
        # it must never mutate these false values in an already-attested file.
        "deployment_gate": {
            "status": "blocked_external_authority_not_deployed",
            "ready": False,
            "controls": {name: False for name in DEPLOYMENT_CONTROLS},
        },
    }


def _write_candidate(path: Path, candidate: Dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise ReceiptBundleError("promotion-candidate output already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_exclusive(path, _canonical_json(candidate) + b"\n")


def _main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="create an unpromoted portable bundle")
    export.add_argument("--store", type=Path, required=True)
    export.add_argument("--id", required=True)
    export.add_argument("--manifest", type=Path, required=True)
    export.add_argument("--trusted-keys", type=Path, required=True)
    export.add_argument("--out", type=Path, required=True)
    verify = commands.add_parser("verify", help="verify and emit an unranked candidate")
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--expected-manifest", type=Path, required=True)
    verify.add_argument("--trusted-keys", type=Path, required=True)
    verify.add_argument("--expected-bundle-sha256")
    verify.add_argument("--expected-repository")
    verify.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "export":
        bundle = export_bundle(
            store=args.store, submission_id=args.id, manifest_path=args.manifest,
            trusted_keys=args.trusted_keys, out=args.out,
        )
        print(json.dumps({
            "bundle": str(args.out),
            "bundle_sha256": bundle["bundle_sha256"],
            "status": "receipt_ready_unpromoted",
        }, sort_keys=True))
        return 0
    candidate = verify_bundle(
        bundle_root=args.bundle, expected_manifest=args.expected_manifest,
        trusted_keys=args.trusted_keys,
        expected_bundle_sha256=args.expected_bundle_sha256,
        expected_repository=args.expected_repository,
    )
    _write_candidate(args.out, candidate)
    print(json.dumps({
        "candidate": str(args.out),
        "bundle_sha256": candidate["bundle_sha256"],
        "status": candidate["status"],
        "eligible_for_leaderboard": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
