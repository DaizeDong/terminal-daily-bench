#!/usr/bin/env python3
"""Fail-closed importer and publisher boundary for replay receipts.

This module is deliberately separate from :mod:`receipt_bundle`.  The bundle
verifier can only create an unranked candidate.  ``import`` verifies the
candidate's GitHub artifact attestation itself, checks the live deployment
boundary and main-pinned registries, and emits an attested import record.
``publish`` verifies that second attestation and atomically appends the record
to a dedicated Git authority-ledger branch.

The committed deployment registry is inactive.  Merely installing this source
therefore grants no authority: all six controls must be both declared in the
main-pinned registry and independently established by this process at runtime.
Caller-supplied "probe results" are intentionally not accepted.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import fcntl
import hashlib
import http.client
import json
import math
import os
import re
import selectors
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional
from urllib.parse import quote

import receipt_auth
import receipt_bundle


REGISTRY_SCHEMA = "terminal-daily-receipt-authority-deployment/v1"
IMPORT_SCHEMA = "terminal-daily-receipt-authority-import/v1"
BLOCKED_SCHEMA = "terminal-daily-receipt-authority-blocked/v1"
PUBLISH_SCHEMA = "terminal-daily-receipt-authority-publication/v1"
IMPORT_DOMAIN = b"terminal-daily-receipt-authority-import/v1\0"
PUBLISH_DOMAIN = b"terminal-daily-receipt-authority-publication/v1\0"
SLSA_PREDICATE = "https://slsa.dev/provenance/v1"
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_VERIFIER_VERSION_BYTES = 4096

CONTROLS = receipt_bundle.DEPLOYMENT_CONTROLS
ROLES = ("candidate", "importer", "publisher")

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_GIT_OBJECT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_RUN_ID_RE = re.compile(r"^[1-9][0-9]{0,39}$")
_ATTEMPT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{2,127}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_WORKFLOW_PATH_RE = re.compile(r"^\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml$")
_REGISTRY_PATH_RE = re.compile(
    r"^\.github/(?:replay-suites|receipt-authorities)/[A-Za-z0-9_.-]+\.json$"
)
_LEDGER_PATH_RE = re.compile(r"^\.github/receipt-authority/[A-Za-z0-9_./-]+$")

CANDIDATE_FIELDS = frozenset({
    "schema", "status", "eligible_for_leaderboard", "attestation_required",
    "bundle_sha256", "submission_id", "attempt_id", "suite_sha256",
    "receipt_sha256", "receipt_key_id", "reward", "signer_euid",
    "verified_at", "verifier", "deployment_gate",
})
CANDIDATE_VERIFIER_FIELDS = frozenset({
    "kind", "repository", "ref", "source_commit", "workflow_commit",
    "workflow_ref", "run_id", "run_attempt", "event_name",
    "runner_environment", "independent_authority",
})
IMPORT_FIELDS = frozenset({
    "schema", "status", "eligible_for_leaderboard", "candidate_sha256",
    "bundle_sha256", "submission_id", "attempt_id", "suite_sha256",
    "receipt_sha256", "receipt_key_id", "receipt_public_key_sha256",
    "reward", "signer_euid", "candidate_attestation_sha256",
    "source_commit", "registry_sha256", "importer", "actor_separation",
    "deployment_gate",
    "imported_at", "import_id",
})
IMPORTER_FIELDS = frozenset({
    "repository", "ref", "workflow_ref", "run_id", "run_attempt",
    "environment", "runner_environment",
})
PUBLISH_FIELDS = frozenset({
    "schema", "status", "eligible_for_leaderboard", "import_id",
    "import_record_sha256", "candidate_sha256", "bundle_sha256",
    "submission_id", "attempt_id", "suite_sha256", "receipt_sha256",
    "receipt_key_id", "reward", "candidate_attestation_sha256",
    "import_attestation_sha256", "source_commit", "registry_sha256",
    "publisher", "actor_separation", "deployment_gate", "published_at",
    "publication_id",
})

IMPORT_ACTOR_FIELDS = frozenset({
    "candidate_run_id", "candidate_run_attempt", "candidate_actor_ids",
    "importer_run_id", "importer_run_attempt", "importer_actor_ids",
    "importer_reviewer_ids",
})
PUBLISH_ACTOR_FIELDS = frozenset({
    *IMPORT_ACTOR_FIELDS,
    "publisher_run_id", "publisher_run_attempt", "publisher_actor_ids",
    "publisher_reviewer_ids",
})

REGISTRY_FIELDS = frozenset({
    "schema", "active", "deployment_status", "repository", "main_ref", "candidate_workflow",
    "importer_workflow", "publisher_workflow", "importer_environment",
    "publisher_environment", "attestation_verifier", "workflow_files",
    "branch_protection", "environments", "signers", "suites",
    "receipt_keys", "publisher_ledger", "deployment_declarations",
})


class AuthorityError(ValueError):
    """An authority input or independently observed control failed closed."""

    def __init__(self, code: str, message: str):
        if not re.fullmatch(r"[a-z0-9_]{3,80}", code):
            raise ValueError("invalid authority error code")
        super().__init__(message)
        self.code = code


def _fail(code: str, message: str) -> None:
    raise AuthorityError(code, message)


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AuthorityError("noncanonical_json", "authority data is not canonical JSON") from exc


def _strict_json(payload: bytes, *, label: str) -> Any:
    def pairs(values: Iterable[tuple[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in values:
            if key in result:
                _fail("duplicate_json_key", f"{label} contains a duplicate JSON key")
            result[key] = value
        return result

    def constant(_: str) -> Any:
        _fail("nonstandard_json_number", f"{label} contains a non-standard number")

    try:
        return json.loads(
            payload, object_pairs_hook=pairs, parse_constant=constant,
        )
    except AuthorityError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthorityError("invalid_json", f"{label} is not valid UTF-8 JSON") from exc


def _stable_file(path: Path, *, label: str, limit: int = MAX_JSON_BYTES) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise AuthorityError("unsafe_file", f"{label} is unavailable or is a symlink") from exc
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size < 1 or before.st_size > limit):
            _fail("unsafe_file", f"{label} is not a bounded single-link regular file")
        chunks = []
        left = limit + 1
        while left:
            chunk = os.read(fd, min(left, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            left -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(fd)
        identity = lambda item: (
            item.st_dev, item.st_ino, item.st_mode, item.st_nlink,
            item.st_size, item.st_mtime_ns, item.st_ctime_ns,
        )
        if identity(before) != identity(after) or len(payload) != before.st_size:
            _fail("mutable_file", f"{label} changed while it was read")
        return payload
    finally:
        os.close(fd)


def _write_exclusive(path: Path, payload: bytes, mode: int = 0o444) -> None:
    if path.exists() or path.is_symlink():
        _fail("output_exists", "authority output already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        os.fchmod(fd, mode)
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


def _exact_fields(value: Any, fields: frozenset[str], *, code: str, label: str) -> Dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        _fail(code, f"{label} has an unreviewed shape")
    return value


def _utc_timestamp(value: Any, *, code: str, label: str) -> str:
    if not isinstance(value, str) or len(value) > 80:
        _fail(code, f"{label} is invalid")
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise AuthorityError(code, f"{label} is invalid") from exc
    if (parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0)
            or parsed.isoformat() != value):
        _fail(code, f"{label} is not canonical UTC")
    return value


def _safe_authority_file(root: Path, relative: str, *, label: str) -> tuple[Path, bytes]:
    if (not isinstance(relative, str) or relative.startswith("/")
            or ".." in Path(relative).parts or "\x00" in relative):
        _fail("unsafe_registry_path", f"{label} path is unsafe")
    try:
        resolved_root = root.resolve(strict=True)
        lexical_root = Path(os.path.abspath(root))
    except OSError as exc:
        raise AuthorityError("unsafe_authority_root", "authority checkout is unavailable") from exc
    if resolved_root != lexical_root:
        _fail("unsafe_authority_root", "authority checkout path contains a symlink")
    target = lexical_root / relative
    try:
        resolved_target = target.resolve(strict=True)
    except OSError as exc:
        raise AuthorityError("missing_registry_file", f"{label} is unavailable") from exc
    if resolved_target != Path(os.path.abspath(target)):
        _fail("unsafe_registry_path", f"{label} path contains a symlink")
    try:
        resolved_target.relative_to(resolved_root)
    except ValueError:
        _fail("unsafe_registry_path", f"{label} escapes the authority checkout")
    return target, _stable_file(target, label=label)


def _validate_workflow_path(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _WORKFLOW_PATH_RE.fullmatch(value):
        _fail("invalid_registry", f"{label} is invalid")
    return value


def _validate_registry(data: Any, payload: bytes) -> Dict[str, Any]:
    registry = _exact_fields(
        data, REGISTRY_FIELDS, code="invalid_registry", label="deployment registry",
    )
    if registry["schema"] != REGISTRY_SCHEMA or type(registry["active"]) is not bool:
        _fail("invalid_registry", "unsupported deployment registry")
    deployment_status = _exact_fields(
        registry["deployment_status"], frozenset({"state", "observed_at", "blockers"}),
        code="invalid_registry", label="deployment status",
    )
    _utc_timestamp(
        deployment_status["observed_at"], code="invalid_registry",
        label="deployment status observation time",
    )
    blockers = deployment_status["blockers"]
    if (type(blockers) is not list
            or any(not isinstance(item, str)
                   or not re.fullmatch(r"[a-z0-9_]{3,100}", item) for item in blockers)
            or len(blockers) != len(set(blockers))):
        _fail("invalid_registry", "deployment blocker registry is invalid")
    if registry["active"]:
        if deployment_status["state"] != "active" or blockers:
            _fail("invalid_registry", "active registry still reports deployment blockers")
    elif deployment_status["state"] != "blocked" or not blockers:
        _fail("invalid_registry", "inactive registry must report concrete deployment blockers")
    if (not isinstance(registry["repository"], str)
            or not _REPOSITORY_RE.fullmatch(registry["repository"])):
        _fail("invalid_registry", "deployment repository is invalid")
    if registry["main_ref"] != "refs/heads/main":
        _fail("invalid_registry", "deployment registry is not main-pinned")
    role_paths = {
        role: _validate_workflow_path(registry[f"{role}_workflow"], label=f"{role} workflow")
        for role in ROLES
    }
    for name in ("importer_environment", "publisher_environment"):
        value = registry[name]
        if (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{3,80}", value)):
            _fail("invalid_registry", f"{name} is invalid")
    if registry["importer_environment"] == registry["publisher_environment"]:
        _fail("invalid_registry", "importer and publisher environments must be distinct")

    verifier = _exact_fields(
        registry["attestation_verifier"], frozenset({"path", "sha256", "version"}),
        code="invalid_registry", label="attestation verifier registry",
    )
    if registry["active"]:
        if (not isinstance(verifier["path"], str) or not verifier["path"].startswith("/")
                or not isinstance(verifier["sha256"], str)
                or not _SHA256_RE.fullmatch(verifier["sha256"])
                or not isinstance(verifier["version"], str)
                or not re.fullmatch(
                    r"gh version [0-9]+\.[0-9]+\.[0-9]+(?: \([0-9]{4}-[0-9]{2}-[0-9]{2}\))?",
                    verifier["version"],
                )):
            _fail("invalid_registry", "active attestation verifier is not exactly pinned")
    elif any(value is not None for value in verifier.values()):
        _fail("invalid_registry", "inactive verifier template must not claim deployment pins")

    workflow_files = registry["workflow_files"]
    if type(workflow_files) is not list or len(workflow_files) != len(ROLES):
        _fail("invalid_registry", "workflow registry must contain exactly three roles")
    seen_roles: set[str] = set()
    for item in workflow_files:
        record = _exact_fields(
            item, frozenset({"role", "path", "sha256", "active"}),
            code="invalid_registry", label="workflow registry row",
        )
        role = record["role"]
        if role not in ROLES or role in seen_roles or record["path"] != role_paths.get(role):
            _fail("invalid_registry", "workflow registry role/path is invalid")
        seen_roles.add(role)
        if type(record["active"]) is not bool:
            _fail("invalid_registry", "workflow registry active flag is invalid")
        if record["active"]:
            if not isinstance(record["sha256"], str) or not _SHA256_RE.fullmatch(record["sha256"]):
                _fail("invalid_registry", "active workflow lacks an exact digest")
        elif record["sha256"] is not None:
            _fail("invalid_registry", "inactive workflow must not claim a digest")
    if seen_roles != set(ROLES):
        _fail("invalid_registry", "workflow registry roles are incomplete")

    branch = _exact_fields(
        registry["branch_protection"], frozenset({
            "branch", "strict_status_checks", "required_status_checks",
            "enforce_admins", "dismiss_stale_reviews", "require_code_owner_reviews",
            "minimum_approvals", "require_linear_history", "block_force_pushes",
            "block_deletions",
        }), code="invalid_registry", label="branch protection policy",
    )
    required_checks = branch["required_status_checks"]
    if (branch["branch"] != "main"
            or type(required_checks) is not list
            or type(branch["minimum_approvals"]) is not int
            or isinstance(branch["minimum_approvals"], bool)
            or branch["minimum_approvals"] < 1
            or any(branch[name] is not True for name in (
                "strict_status_checks", "enforce_admins", "dismiss_stale_reviews",
                "require_code_owner_reviews", "require_linear_history",
                "block_force_pushes", "block_deletions",
            ))):
        _fail("invalid_registry", "branch protection policy is not fail-closed")
    check_identities: set[tuple[str, Optional[int]]] = set()
    for item in required_checks:
        check = _exact_fields(
            item, frozenset({"context", "app_id"}), code="invalid_registry",
            label="required status check",
        )
        context = check["context"]
        app_id = check["app_id"]
        if (not isinstance(context, str) or not context or len(context) > 200
                or "\x00" in context
                or (app_id is not None and (type(app_id) is not int or app_id < 1))):
            _fail("invalid_registry", "required status-check identity is invalid")
        identity = (context, app_id)
        if identity in check_identities:
            _fail("invalid_registry", "required status-check identity is duplicated")
        check_identities.add(identity)
        if registry["active"] and app_id is None:
            _fail("invalid_registry", "active status check is not bound to a GitHub App")
    if registry["active"] and not required_checks:
        _fail("invalid_registry", "active authority requires pinned status checks")

    environments = registry["environments"]
    if type(environments) is not list or len(environments) != 2:
        _fail("invalid_registry", "environment registry must contain importer and publisher")
    expected_environments = {
        "importer": registry["importer_environment"],
        "publisher": registry["publisher_environment"],
    }
    seen_env: set[str] = set()
    for item in environments:
        record = _exact_fields(
            item, frozenset({
                "role", "name", "minimum_reviewers", "prevent_self_review",
                "protected_branches_only", "minimum_approvals", "reviewer_ids",
            }), code="invalid_registry", label="environment registry row",
        )
        role = record["role"]
        if role not in expected_environments or role in seen_env:
            _fail("invalid_registry", "environment registry role is invalid")
        seen_env.add(role)
        if (record["name"] != expected_environments[role]
                or type(record["minimum_reviewers"]) is not int
                or isinstance(record["minimum_reviewers"], bool)
                or record["minimum_reviewers"] < 1
                or type(record["minimum_approvals"]) is not int
                or isinstance(record["minimum_approvals"], bool)
                or record["minimum_approvals"] < 1
                or record["minimum_approvals"] > record["minimum_reviewers"]
                or type(record["reviewer_ids"]) is not list
                or any(type(item) is not int or item < 1 for item in record["reviewer_ids"])
                or len(record["reviewer_ids"]) != len(set(record["reviewer_ids"]))
                or record["prevent_self_review"] is not True
                or record["protected_branches_only"] is not True):
            _fail("invalid_registry", "environment registry policy is unsafe")
        if registry["active"] and len(record["reviewer_ids"]) < record["minimum_reviewers"]:
            _fail("invalid_registry", "active environment lacks pinned reviewer identities")
        if not registry["active"] and record["reviewer_ids"]:
            _fail("invalid_registry", "inactive environment dishonestly pins reviewers")

    for collection, fields in (
        ("signers", frozenset({"signer_euid", "key_id", "public_key_sha256", "active"})),
        ("suites", frozenset({"suite_sha256", "manifest_path", "active"})),
        ("receipt_keys", frozenset({"key_id", "public_key_sha256", "registry_path", "active"})),
    ):
        rows = registry[collection]
        if type(rows) is not list:
            _fail("invalid_registry", f"{collection} registry is not a list")
        for row in rows:
            _exact_fields(row, fields, code="invalid_registry", label=f"{collection} row")
            if type(row["active"]) is not bool:
                _fail("invalid_registry", f"{collection} active flag is invalid")
    for row in registry["signers"]:
        if (type(row["signer_euid"]) is not int or isinstance(row["signer_euid"], bool)
                or row["signer_euid"] < 1 or not _KEY_ID_RE.fullmatch(str(row["key_id"]))
                or not _SHA256_RE.fullmatch(str(row["public_key_sha256"]))):
            _fail("invalid_registry", "signer registry row is invalid")
    for row in registry["suites"]:
        if (not _SHA256_RE.fullmatch(str(row["suite_sha256"]))
                or not isinstance(row["manifest_path"], str)
                or not _REGISTRY_PATH_RE.fullmatch(row["manifest_path"])
                or not row["manifest_path"].startswith(".github/replay-suites/")):
            _fail("invalid_registry", "suite registry row is invalid")
    for row in registry["receipt_keys"]:
        if (not _KEY_ID_RE.fullmatch(str(row["key_id"]))
                or not _SHA256_RE.fullmatch(str(row["public_key_sha256"]))
                or not isinstance(row["registry_path"], str)
                or not _REGISTRY_PATH_RE.fullmatch(row["registry_path"])
                or not row["registry_path"].startswith(".github/receipt-authorities/")):
            _fail("invalid_registry", "receipt-key registry row is invalid")

    ledger = _exact_fields(
        registry["publisher_ledger"], frozenset({
            "active", "branch", "path_prefix", "genesis_commit",
            "trusted_writer_app_id", "ruleset_id", "enforce_admins", "require_linear_history",
            "block_force_pushes", "block_deletions",
        }),
        code="invalid_registry", label="publisher ledger registry",
    )
    if (type(ledger["active"]) is not bool
            or ledger["branch"] != "receipt-authority-ledger"
            or not isinstance(ledger["path_prefix"], str)
            or not _LEDGER_PATH_RE.fullmatch(ledger["path_prefix"])
            or ".." in Path(ledger["path_prefix"]).parts
            or any(ledger[name] is not True for name in (
                "enforce_admins", "require_linear_history", "block_force_pushes",
                "block_deletions",
            ))):
        _fail("invalid_registry", "publisher ledger registry is invalid")
    if ledger["active"]:
        if (not isinstance(ledger["genesis_commit"], str)
                or not _COMMIT_RE.fullmatch(ledger["genesis_commit"])
                or type(ledger["trusted_writer_app_id"]) is not int
                or ledger["trusted_writer_app_id"] < 1
                or type(ledger["ruleset_id"]) is not int
                or ledger["ruleset_id"] < 1):
            _fail("invalid_registry", "active publisher ledger lacks immutable authority pins")
    elif (ledger["genesis_commit"] is not None
          or ledger["trusted_writer_app_id"] is not None
          or ledger["ruleset_id"] is not None):
        _fail("invalid_registry", "inactive publisher ledger must not claim authority pins")

    declarations = _exact_fields(
        registry["deployment_declarations"], frozenset(CONTROLS),
        code="invalid_registry", label="deployment declarations",
    )
    if any(type(value) is not bool for value in declarations.values()):
        _fail("invalid_registry", "deployment declaration has a non-boolean value")
    if registry["active"]:
        if (not all(declarations.values()) or not all(item["active"] for item in workflow_files)
                or not ledger["active"] or not registry["signers"]
                or not registry["suites"] or not registry["receipt_keys"]):
            _fail("invalid_registry", "active registry has incomplete deployment declarations")
    else:
        if any(declarations.values()) or any(item["active"] for item in workflow_files) or ledger["active"]:
            _fail("invalid_registry", "inactive registry dishonestly claims deployed controls")
        if any(row["active"] for name in ("signers", "suites", "receipt_keys") for row in registry[name]):
            _fail("invalid_registry", "inactive registry dishonestly activates authority rows")
    registry["_sha256"] = hashlib.sha256(payload).hexdigest()
    return registry


def load_registry(path: Path) -> Dict[str, Any]:
    payload = _stable_file(path, label="deployment registry")
    return _validate_registry(_strict_json(payload, label="deployment registry"), payload)


def _runtime_context(registry: Mapping[str, Any], role: str,
                     environ: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    if role not in ("importer", "publisher"):
        _fail("invalid_runtime", "invalid authority runtime role")
    env = os.environ if environ is None else environ
    repository = registry["repository"]
    workflow_path = registry[f"{role}_workflow"]
    expected_workflow_ref = f"{repository}/{workflow_path}@{registry['main_ref']}"
    expected_environment = registry[f"{role}_environment"]
    values = {
        "repository": env.get("GITHUB_REPOSITORY", ""),
        "ref": env.get("GITHUB_REF", ""),
        "source_commit": env.get("GITHUB_SHA", ""),
        "workflow_commit": env.get("TDB_AUTHORITY_WORKFLOW_SHA", ""),
        "workflow_ref": env.get("GITHUB_WORKFLOW_REF", ""),
        "run_id": env.get("GITHUB_RUN_ID", ""),
        "run_attempt": env.get("GITHUB_RUN_ATTEMPT", ""),
        "event_name": env.get("GITHUB_EVENT_NAME", ""),
        "runner_environment": env.get("TDB_RUNNER_ENVIRONMENT", ""),
        "environment": env.get("TDB_AUTHORITY_ENVIRONMENT", ""),
    }
    if env.get("GITHUB_ACTIONS") != "true":
        _fail("invalid_runtime", "authority must run in GitHub Actions")
    if values["repository"] != repository or values["ref"] != registry["main_ref"]:
        _fail("wrong_repository_or_branch", "authority runtime is not the pinned main repository")
    if (not _COMMIT_RE.fullmatch(values["source_commit"])
            or values["workflow_commit"] != values["source_commit"]):
        _fail("wrong_source_commit", "authority workflow is not pinned to its source commit")
    if values["workflow_ref"] != expected_workflow_ref:
        _fail("wrong_workflow", "authority runtime uses the wrong main workflow")
    if (not _RUN_ID_RE.fullmatch(values["run_id"])
            or not _RUN_ID_RE.fullmatch(values["run_attempt"])):
        _fail("invalid_runtime", "authority run identity is invalid")
    if values["event_name"] != "workflow_dispatch":
        _fail("wrong_event", "authority is not an explicit workflow dispatch")
    if values["runner_environment"] != "github-hosted":
        _fail("self_hosted_runner", "authority requires a GitHub-hosted runner")
    ambient = env.get("RUNNER_ENVIRONMENT", "")
    if ambient and ambient != values["runner_environment"]:
        _fail("runner_context_mismatch", "runner environment facts disagree")
    if values["environment"] != expected_environment:
        _fail("wrong_environment", "authority runtime uses the wrong protected environment")
    return values


def _validate_candidate(payload: bytes, registry: Mapping[str, Any], runtime: Mapping[str, str],
                        *, expected_run_id: str, expected_run_attempt: str) -> Dict[str, Any]:
    candidate = _exact_fields(
        _strict_json(payload, label="promotion candidate"), CANDIDATE_FIELDS,
        code="invalid_candidate_schema", label="promotion candidate",
    )
    if payload != _canonical_json(candidate) + b"\n":
        _fail("noncanonical_candidate", "promotion candidate bytes are not canonical")
    if (candidate["schema"] != receipt_bundle.PROMOTION_SCHEMA
            or candidate["status"] != "receipt_validated_pending_external_attestation"
            or candidate["eligible_for_leaderboard"] is not False
            or candidate["attestation_required"] != "github_actions_artifact_attestation"):
        _fail("invalid_candidate_state", "promotion candidate is not strictly unranked")
    for name in ("bundle_sha256", "submission_id", "suite_sha256", "receipt_sha256"):
        if not isinstance(candidate[name], str) or not _SHA256_RE.fullmatch(candidate[name]):
            _fail("invalid_candidate_schema", f"promotion candidate {name} is invalid")
    if (not isinstance(candidate["attempt_id"], str)
            or not _ATTEMPT_ID_RE.fullmatch(candidate["attempt_id"])
            or not isinstance(candidate["receipt_key_id"], str)
            or not _KEY_ID_RE.fullmatch(candidate["receipt_key_id"])):
        _fail("invalid_candidate_schema", "promotion candidate authority identity is invalid")
    reward = candidate["reward"]
    if (type(reward) is not float or not math.isfinite(reward) or not 0.0 <= reward <= 1.0):
        _fail("candidate_type_confusion", "promotion candidate reward must be a finite float")
    if (type(candidate["signer_euid"]) is not int or isinstance(candidate["signer_euid"], bool)
            or candidate["signer_euid"] < 1):
        _fail("candidate_type_confusion", "promotion candidate signer UID is invalid")
    _utc_timestamp(candidate["verified_at"], code="invalid_candidate_schema", label="candidate verification time")

    verifier = _exact_fields(
        candidate["verifier"], CANDIDATE_VERIFIER_FIELDS,
        code="invalid_candidate_schema", label="candidate verifier",
    )
    expected_workflow = (
        f"{registry['repository']}/{registry['candidate_workflow']}@{registry['main_ref']}"
    )
    expected = {
        "kind": "github_actions_keyless_candidate",
        "repository": registry["repository"],
        "ref": registry["main_ref"],
        "source_commit": runtime["source_commit"],
        "workflow_commit": runtime["source_commit"],
        "workflow_ref": expected_workflow,
        "run_id": expected_run_id,
        "run_attempt": expected_run_attempt,
        "event_name": "workflow_dispatch",
        "runner_environment": "github-hosted",
        "independent_authority": True,
    }
    if verifier != expected:
        _fail("wrong_candidate_workflow", "candidate did not originate from the exact pinned workflow run")
    gate = _exact_fields(
        candidate["deployment_gate"], frozenset({"status", "ready", "controls"}),
        code="invalid_candidate_schema", label="candidate deployment gate",
    )
    controls = _exact_fields(
        gate["controls"], frozenset(CONTROLS),
        code="invalid_candidate_schema", label="candidate controls",
    )
    if (gate["status"] != "blocked_external_authority_not_deployed"
            or gate["ready"] is not False or any(value is not False for value in controls.values())):
        _fail("candidate_claims_authority", "candidate improperly claims deployment authority")
    return candidate


class GitHubAPI:
    """Small fixed-host GitHub REST client; it never follows redirects."""

    def __init__(self, token: str, *, repository: str):
        if not token:
            _fail("missing_github_token", "GitHub API token is unavailable")
        if not _REPOSITORY_RE.fullmatch(repository):
            _fail("invalid_registry", "GitHub repository is invalid")
        self._token = token
        self.repository = repository

    def request(self, method: str, path: str, payload: Optional[Mapping[str, Any]] = None,
                *, allow_not_found: bool = False) -> Any:
        prefix = f"/repos/{self.repository}/"
        if method not in {"GET", "POST", "PATCH"} or not path.startswith(prefix):
            _fail("unsafe_api_request", "authority attempted an unapproved GitHub API request")
        body = None if payload is None else _canonical_json(payload)
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "terminal-daily-receipt-authority/1",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPSConnection("api.github.com", timeout=20)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read(MAX_JSON_BYTES + 1)
        except OSError as exc:
            raise AuthorityError("github_api_unavailable", "GitHub control API is unavailable") from exc
        finally:
            connection.close()
        if allow_not_found and response.status == 404:
            return None
        expected = {"GET": {200}, "POST": {201}, "PATCH": {200}}[method]
        if response.status not in expected or len(raw) > MAX_JSON_BYTES:
            _fail("github_api_rejected", f"GitHub control API rejected {method} ({response.status})")
        return _strict_json(raw, label="GitHub API response")

    def get(self, suffix: str, *, allow_not_found: bool = False) -> Any:
        return self.request("GET", f"/repos/{self.repository}/{suffix}", allow_not_found=allow_not_found)

    def post(self, suffix: str, payload: Mapping[str, Any]) -> Any:
        return self.request("POST", f"/repos/{self.repository}/{suffix}", payload)

    def patch(self, suffix: str, payload: Mapping[str, Any]) -> Any:
        return self.request("PATCH", f"/repos/{self.repository}/{suffix}", payload)


def _bool_field(container: Any, name: str) -> Optional[bool]:
    if type(container) is not dict:
        return None
    value = container.get(name)
    if type(value) is dict:
        value = value.get("enabled")
    return value if type(value) is bool else None


def _verify_live_main_head(api: Any, registry: Mapping[str, Any],
                           source_commit: str) -> None:
    data = api.get("git/ref/heads/main")
    obj = data.get("object") if type(data) is dict else None
    sha = obj.get("sha") if type(obj) is dict and obj.get("type") == "commit" else None
    if sha != source_commit:
        _fail(
            "stale_authority_source",
            "authority source commit is no longer the live main head",
        )


def _verify_main_branch(api: Any, registry: Mapping[str, Any]) -> None:
    policy = registry["branch_protection"]
    data = api.get(f"branches/{quote(policy['branch'], safe='')}/protection")
    if type(data) is not dict:
        _fail("branch_protection_missing", "main branch protection is unavailable")
    checks = data.get("required_status_checks")
    live_checks = checks.get("checks") if type(checks) is dict else None
    live_identities = set()
    if type(live_checks) is list:
        for item in live_checks:
            if (type(item) is not dict or not isinstance(item.get("context"), str)
                    or type(item.get("app_id")) is not int or item["app_id"] < 1):
                _fail(
                    "branch_protection_insufficient",
                    "main status-check identity is not bound to a GitHub App",
                )
            live_identities.add((item["context"], item["app_id"]))
    expected_identities = {
        (item["context"], item["app_id"])
        for item in policy["required_status_checks"]
    }
    if (type(checks) is not dict or checks.get("strict") is not True
            or type(live_checks) is not list
            or not expected_identities.issubset(live_identities)):
        _fail("branch_protection_insufficient", "main status-check protection is insufficient")
    reviews = data.get("required_pull_request_reviews")
    if (type(reviews) is not dict
            or reviews.get("dismiss_stale_reviews") is not True
            or reviews.get("require_code_owner_reviews") is not True
            or type(reviews.get("required_approving_review_count")) is not int
            or reviews["required_approving_review_count"] < policy["minimum_approvals"]):
        _fail("branch_protection_insufficient", "main review protection is insufficient")
    if (_bool_field(data, "enforce_admins") is not True
            or _bool_field(data, "required_linear_history") is not True
            or _bool_field(data, "allow_force_pushes") is not False
            or _bool_field(data, "allow_deletions") is not False):
        _fail("branch_protection_insufficient", "main mutation protection is insufficient")


def _verify_environment(api: Any, policy: Mapping[str, Any]) -> None:
    data = api.get(f"environments/{quote(policy['name'], safe='')}")
    if type(data) is not dict or data.get("name") != policy["name"]:
        _fail("environment_missing", "protected authority environment is unavailable")
    rules = data.get("protection_rules")
    if type(rules) is not list:
        _fail("environment_unprotected", "authority environment has no protection rules")
    reviewer_rules = [item for item in rules if type(item) is dict and item.get("type") == "required_reviewers"]
    if len(reviewer_rules) != 1:
        _fail("environment_unprotected", "authority environment lacks one reviewer rule")
    reviewer_rule = reviewer_rules[0]
    reviewers = reviewer_rule.get("reviewers")
    live_reviewer_ids = set()
    if type(reviewers) is list:
        for item in reviewers:
            reviewer = item.get("reviewer") if type(item) is dict else None
            reviewer_id = reviewer.get("id") if type(reviewer) is dict else None
            if (type(item) is not dict or item.get("type") != "User"
                    or type(reviewer_id) is not int or reviewer_id < 1):
                _fail(
                    "environment_unprotected",
                    "authority environment contains an unpinned reviewer principal",
                )
            live_reviewer_ids.add(reviewer_id)
    if (type(reviewers) is not list or len(reviewers) < policy["minimum_reviewers"]
            or reviewer_rule.get("prevent_self_review") is not True
            or live_reviewer_ids != set(policy["reviewer_ids"])):
        _fail("environment_unprotected", "authority environment reviewer policy is insufficient")
    branch_policy = data.get("deployment_branch_policy")
    if (type(branch_policy) is not dict
            or branch_policy.get("protected_branches") is not True
            or branch_policy.get("custom_branch_policies") is not False):
        _fail("environment_unprotected", "authority environment is not limited to protected branches")


def _environment_policy(registry: Mapping[str, Any], role: str) -> Mapping[str, Any]:
    matches = [item for item in registry["environments"] if item["role"] == role]
    if len(matches) != 1:
        _fail("invalid_registry", "authority environment registry is ambiguous")
    return matches[0]


def _workflow_run_actors(api: Any, registry: Mapping[str, Any], *, role: str,
                         run_id: str, run_attempt: str, source_commit: str,
                         require_success: bool) -> tuple[int, ...]:
    if role not in ROLES or not _RUN_ID_RE.fullmatch(run_id) or not _RUN_ID_RE.fullmatch(run_attempt):
        _fail("invalid_run_evidence", "authority workflow-run identity is invalid")
    data = api.get(f"actions/runs/{run_id}")
    repository = data.get("repository") if type(data) is dict else None
    actor = data.get("actor") if type(data) is dict else None
    triggering_actor = data.get("triggering_actor") if type(data) is dict else None
    actor_ids = (
        actor.get("id") if type(actor) is dict else None,
        triggering_actor.get("id") if type(triggering_actor) is dict else None,
    )
    workflow_id = data.get("workflow_id") if type(data) is dict else None
    workflow = api.get(f"actions/workflows/{workflow_id}") if type(workflow_id) is int else None
    if (type(data) is not dict
            or data.get("id") != int(run_id)
            or data.get("run_attempt") != int(run_attempt)
            or data.get("event") != "workflow_dispatch"
            or data.get("head_branch") != "main"
            or data.get("head_sha") != source_commit
            or type(repository) is not dict
            or repository.get("full_name") != registry["repository"]
            or type(workflow_id) is not int or workflow_id < 1
            or type(workflow) is not dict or workflow.get("id") != workflow_id
            or workflow.get("path") != registry[f"{role}_workflow"]
            or workflow.get("state") != "active"
            or any(type(value) is not int or value < 1 for value in actor_ids)):
        _fail("invalid_run_evidence", "authority workflow-run evidence is not source-bound")
    if require_success and (data.get("status") != "completed" or data.get("conclusion") != "success"):
        _fail("unsuccessful_authority_run", "upstream authority workflow did not complete successfully")
    return tuple(sorted(set(actor_ids)))


def _approval_actor_ids(api: Any, policy: Mapping[str, Any], *, run_id: str) -> tuple[int, ...]:
    rows = api.get(f"actions/runs/{run_id}/approvals")
    if type(rows) is not list:
        _fail("missing_approval_evidence", "authority environment approval history is unavailable")
    approved: set[int] = set()
    saw_environment = False
    for row in rows:
        environments = row.get("environments") if type(row) is dict else None
        if type(environments) is not list:
            _fail("invalid_approval_evidence", "authority approval history is malformed")
        names = {
            item.get("name") for item in environments
            if type(item) is dict and isinstance(item.get("name"), str)
        }
        if policy["name"] not in names:
            continue
        saw_environment = True
        user = row.get("user")
        user_id = user.get("id") if type(user) is dict else None
        if (row.get("state") != "approved" or type(user_id) is not int or user_id < 1
                or user_id not in policy["reviewer_ids"]):
            _fail("invalid_approval_evidence", "authority environment approval is not trusted")
        approved.add(user_id)
    if not saw_environment or len(approved) < policy["minimum_approvals"]:
        _fail("missing_approval_evidence", "authority environment lacks independent approval evidence")
    return tuple(sorted(approved))


def _require_disjoint(left: Iterable[int], right: Iterable[int], *, message: str) -> None:
    if set(left) & set(right):
        _fail("same_actor_authority", message)


def _collect_import_actor_evidence(candidate: Mapping[str, Any], *, api: Any,
                                   registry: Mapping[str, Any],
                                   runtime: Mapping[str, str]) -> Dict[str, Any]:
    candidate_run_id = candidate["verifier"]["run_id"]
    candidate_run_attempt = candidate["verifier"]["run_attempt"]
    candidate_actors = _workflow_run_actors(
        api, registry, role="candidate", run_id=candidate_run_id,
        run_attempt=candidate_run_attempt, source_commit=runtime["source_commit"],
        require_success=True,
    )
    importer_actors = _workflow_run_actors(
        api, registry, role="importer", run_id=runtime["run_id"],
        run_attempt=runtime["run_attempt"], source_commit=runtime["source_commit"],
        require_success=False,
    )
    reviewers = _approval_actor_ids(
        api, _environment_policy(registry, "importer"), run_id=runtime["run_id"],
    )
    _require_disjoint(
        candidate_actors, reviewers,
        message="candidate workflow actor cannot approve its own authority import",
    )
    _require_disjoint(
        importer_actors, reviewers,
        message="import workflow actor cannot approve its own protected environment",
    )
    return {
        "candidate_run_id": candidate_run_id,
        "candidate_run_attempt": candidate_run_attempt,
        "candidate_actor_ids": list(candidate_actors),
        "importer_run_id": runtime["run_id"],
        "importer_run_attempt": runtime["run_attempt"],
        "importer_actor_ids": list(importer_actors),
        "importer_reviewer_ids": list(reviewers),
    }


def _verify_workflow_files(root: Path, registry: Mapping[str, Any]) -> None:
    for record in registry["workflow_files"]:
        if record["active"] is not True:
            _fail("workflow_registry_inactive", "a required authority workflow is inactive")
        _, payload = _safe_authority_file(root, record["path"], label=f"{record['role']} workflow")
        if hashlib.sha256(payload).hexdigest() != record["sha256"]:
            _fail("workflow_digest_mismatch", "a main-pinned authority workflow digest changed")


def _match_authority_rows(candidate: Mapping[str, Any], root: Path,
                          registry: Mapping[str, Any]) -> str:
    signers = [row for row in registry["signers"] if row["active"] is True
               and row["signer_euid"] == candidate["signer_euid"]
               and row["key_id"] == candidate["receipt_key_id"]]
    suites = [row for row in registry["suites"] if row["active"] is True
              and row["suite_sha256"] == candidate["suite_sha256"]]
    keys = [row for row in registry["receipt_keys"] if row["active"] is True
            and row["key_id"] == candidate["receipt_key_id"]]
    if len(signers) != 1 or len(suites) != 1 or len(keys) != 1:
        _fail("authority_registry_miss", "candidate does not match one active signer, suite and key")
    if signers[0]["public_key_sha256"] != keys[0]["public_key_sha256"]:
        _fail("authority_registry_mismatch", "signer and key registries disagree")
    _, suite_payload = _safe_authority_file(root, suites[0]["manifest_path"], label="main-pinned suite")
    if hashlib.sha256(suite_payload).hexdigest() != candidate["suite_sha256"]:
        _fail("suite_digest_mismatch", "main-pinned suite bytes disagree with the candidate")
    key_path, _ = _safe_authority_file(root, keys[0]["registry_path"], label="main-pinned receipt keys")
    try:
        trusted = receipt_auth.load_trusted_keys(key_path)
    except (OSError, receipt_auth.ReceiptAuthorityError) as exc:
        raise AuthorityError("invalid_receipt_key_registry", "main-pinned receipt keys are invalid") from exc
    authority = trusted.get(candidate["receipt_key_id"])
    if (authority is None
            or authority.get("public_key_sha256") != keys[0]["public_key_sha256"]):
        _fail("receipt_key_mismatch", "main-pinned receipt key bytes disagree with the registry")
    return keys[0]["public_key_sha256"]


def _verify_ledger_exists(api: Any, registry: Mapping[str, Any], *,
                          source_commit: str) -> str:
    ledger = registry["publisher_ledger"]
    if ledger["active"] is not True:
        _fail("publisher_ledger_inactive", "publisher authority ledger is not active")
    _verify_live_main_head(api, registry, source_commit)
    # This branch-specific endpoint returns only actively enforced rules and does
    # not hide data behind ruleset-administration permission.  Classic branch
    # restrictions below independently prove the sole writer identity.
    rules = api.get(f"rules/branches/{quote(ledger['branch'], safe='')}?per_page=100")
    rule_types = {
        item.get("type") for item in rules
        if (type(item) is dict
            and item.get("ruleset_id") == ledger["ruleset_id"]
            and item.get("ruleset_source_type") == "Repository"
            and item.get("ruleset_source") == registry["repository"]
            and isinstance(item.get("type"), str))
    } if type(rules) is list else set()
    expected_rules = {"update", "deletion", "non_fast_forward", "required_linear_history"}
    if type(rules) is not list or not expected_rules.issubset(rule_types):
        _fail(
            "publisher_ledger_ruleset_invalid",
            "publisher ledger branch lacks its pinned active mutation ruleset",
        )
    protection = api.get(f"branches/{quote(ledger['branch'], safe='')}/protection")
    restrictions = protection.get("restrictions") if type(protection) is dict else None
    apps = restrictions.get("apps") if type(restrictions) is dict else None
    users = restrictions.get("users") if type(restrictions) is dict else None
    teams = restrictions.get("teams") if type(restrictions) is dict else None
    app_ids = {
        item.get("id") for item in apps
        if type(item) is dict and type(item.get("id")) is int
    } if type(apps) is list else set()
    if (type(protection) is not dict
            or _bool_field(protection, "enforce_admins") is not True
            or _bool_field(protection, "required_linear_history") is not True
            or _bool_field(protection, "allow_force_pushes") is not False
            or _bool_field(protection, "allow_deletions") is not False
            or type(restrictions) is not dict
            or type(apps) is not list or len(apps) != 1
            or any(type(item) is not dict or type(item.get("id")) is not int for item in apps)
            or app_ids != {ledger["trusted_writer_app_id"]}
            or type(users) is not list or users
            or type(teams) is not list or teams):
        _fail(
            "publisher_ledger_unprotected",
            "publisher ledger branch is not restricted to its pinned writer app",
        )
    ref = api.get(f"git/ref/heads/{quote(ledger['branch'], safe='')}")
    obj = ref.get("object") if type(ref) is dict else None
    sha = obj.get("sha") if type(obj) is dict and obj.get("type") == "commit" else None
    if not isinstance(sha, str) or not _COMMIT_RE.fullmatch(sha):
        _fail("publisher_ledger_missing", "publisher authority ledger branch is unavailable")
    genesis = ledger["genesis_commit"]
    if sha != genesis:
        comparison = api.get(f"compare/{genesis}...{sha}")
        merge_base = comparison.get("merge_base_commit") if type(comparison) is dict else None
        if (type(comparison) is not dict or comparison.get("status") != "ahead"
                or type(merge_base) is not dict or merge_base.get("sha") != genesis):
            _fail(
                "publisher_ledger_history_invalid",
                "publisher ledger no longer descends from its pinned genesis commit",
            )
    return sha


def _run_bounded_stdout(command: list[str], *, timeout: float,
                        env: Mapping[str, str], limit: int,
                        pass_fds: tuple[int, ...] = ()) -> tuple[int, bytes]:
    if limit < 1:
        _fail("invalid_runtime", "verifier output limit is invalid")
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=dict(env), pass_fds=pass_fds,
        )
    except OSError as exc:
        raise AuthorityError(
            "attestation_verifier_failed", "attestation verifier is unavailable",
        ) from exc
    if process.stdout is None:  # pragma: no cover - guaranteed by PIPE
        process.kill()
        process.wait()
        _fail("attestation_verifier_failed", "attestation verifier has no output pipe")
    selector = selectors.DefaultSelector()
    chunks: list[bytes] = []
    size = 0
    deadline = time.monotonic() + timeout
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        open_pipe = True
        while open_pipe:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _fail("attestation_verifier_timeout", "attestation verifier timed out")
            events = selector.select(remaining)
            if not events:
                _fail("attestation_verifier_timeout", "attestation verifier timed out")
            for key, _ in events:
                try:
                    chunk = os.read(key.fileobj.fileno(), min(65536, limit + 1 - size))
                except OSError as exc:
                    raise AuthorityError(
                        "attestation_verifier_failed", "attestation verifier output failed",
                    ) from exc
                if not chunk:
                    selector.unregister(key.fileobj)
                    open_pipe = False
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > limit:
                    _fail(
                        "attestation_verifier_output_too_large",
                        "attestation verifier output exceeded its hard limit",
                    )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _fail("attestation_verifier_timeout", "attestation verifier timed out")
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            raise AuthorityError(
                "attestation_verifier_timeout", "attestation verifier timed out",
            ) from exc
        return returncode, b"".join(chunks)
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
            process.wait()


def _verified_verifier_memfd(registry: Mapping[str, Any]) -> tuple[int, str, str]:
    pin = registry["attestation_verifier"]
    path = Path(pin["path"])
    payload = _stable_file(path, label="attestation verifier", limit=256 * 1024 * 1024)
    mode = path.stat(follow_symlinks=False).st_mode
    if not mode & stat.S_IXUSR or mode & 0o022:
        _fail("unsafe_attestation_verifier", "attestation verifier permissions are unsafe")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != pin["sha256"]:
        _fail("attestation_verifier_mismatch", "attestation verifier binary digest is not pinned")
    if not hasattr(os, "memfd_create") or not hasattr(os, "MFD_ALLOW_SEALING"):
        _fail("unsafe_attestation_verifier", "runtime cannot create a sealed verifier image")
    fd: Optional[int] = None
    try:
        flags = os.MFD_ALLOW_SEALING | getattr(os, "MFD_CLOEXEC", 0)
        fd = os.memfd_create("tdb-attestation-verifier", flags)
        offset = 0
        while offset < len(payload):
            written = os.write(fd, payload[offset:])
            if written < 1:
                _fail("unsafe_attestation_verifier", "sealed verifier copy was incomplete")
            offset += written
        os.fchmod(fd, 0o500)
        required_seals = (
            fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE
        )
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, required_seals)
        if fcntl.fcntl(fd, fcntl.F_GET_SEALS) & required_seals != required_seals:
            _fail("unsafe_attestation_verifier", "verifier image could not be sealed")
        if hashlib.sha256(os.pread(fd, len(payload), 0)).hexdigest() != digest:
            _fail("attestation_verifier_mismatch", "sealed verifier image changed")
    except AuthorityError:
        if fd is not None:
            os.close(fd)
        raise
    except (OSError, AttributeError) as exc:
        if fd is not None:
            os.close(fd)
        raise AuthorityError(
            "unsafe_attestation_verifier", "failed to create a sealed verifier image",
        ) from exc
    assert fd is not None
    binary = f"/proc/self/fd/{fd}"
    try:
        returncode, stdout = _run_bounded_stdout(
            [binary, "--version"], timeout=10,
            env={"HOME": os.environ.get("HOME", "/tmp")},
            limit=MAX_VERIFIER_VERSION_BYTES, pass_fds=(fd,),
        )
    except Exception:
        os.close(fd)
        raise
    try:
        first = stdout.decode("utf-8", "strict").splitlines()[:1]
    except UnicodeDecodeError:
        first = []
    if returncode != 0 or first != [pin["version"]]:
        os.close(fd)
        _fail("attestation_verifier_mismatch", "attestation verifier version is not pinned")
    return fd, binary, digest


def _attestation_environment() -> Dict[str, str]:
    env: Dict[str, str] = {"HOME": os.environ.get("HOME", "/tmp")}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        env["GH_TOKEN"] = token
    for name in ("SSL_CERT_FILE", "SSL_CERT_DIR"):
        if os.environ.get(name):
            env[name] = os.environ[name]
    return env


def _parse_attestation_result(payload: bytes, *, artifact_sha256: str,
                              repository: str, workflow_identity: str,
                              source_ref: str, source_commit: str,
                              run_id: str, run_attempt: str) -> str:
    value = _strict_json(payload, label="attestation verifier output")
    if type(value) is not list or len(value) != 1:
        _fail("ambiguous_attestation", "exactly one verified artifact attestation is required")
    row = _exact_fields(
        value[0], frozenset({"attestation", "verificationResult"}),
        code="invalid_attestation_result", label="attestation verification result",
    )
    if type(row["attestation"]) is not dict or type(row["verificationResult"]) is not dict:
        _fail("attestation_type_confusion", "attestation result objects have invalid types")
    result = _exact_fields(
        row["verificationResult"], frozenset({
            "mediaType", "signature", "statement", "verifiedIdentity",
            "verifiedTimestamps",
        }), code="invalid_attestation_result",
        label="attestation verification result body",
    )
    if result["mediaType"] != "application/vnd.dev.sigstore.verificationresult+json;version=0.1":
        _fail("invalid_attestation_result", "attestation verifier media type is unsupported")
    statement = result.get("statement")
    signature = result.get("signature")
    timestamps = result.get("verifiedTimestamps")
    if (type(statement) is not dict or type(signature) is not dict
            or set(signature) != {"certificate"}
            or type(signature.get("certificate")) is not dict
            or type(timestamps) is not list or not timestamps
            or any(type(item) is not dict for item in timestamps)):
        _fail("invalid_attestation_result", "verified attestation lacks cryptographic evidence")
    verified_identity = result["verifiedIdentity"]
    if (type(verified_identity) is not dict
            or set(verified_identity) != {"issuer", "subjectAlternativeName"}
            or any(type(value) is not dict for value in verified_identity.values())
            or any(type(item.get("type")) is not str for item in timestamps)):
        _fail("invalid_attestation_result", "verified attestation policy evidence is malformed")
    statement = _exact_fields(
        statement, frozenset({"_type", "predicateType", "subject", "predicate"}),
        code="invalid_attestation_result", label="verified in-toto statement",
    )
    if (statement.get("_type") != "https://in-toto.io/Statement/v1"
            or statement.get("predicateType") != SLSA_PREDICATE):
        _fail("wrong_attestation_type", "artifact attestation predicate type is not SLSA provenance")
    subjects = statement.get("subject")
    if (type(statement["predicate"]) is not dict or type(subjects) is not list
            or len(subjects) != 1 or type(subjects[0]) is not dict
            or set(subjects[0]) != {"name", "digest"}
            or type(subjects[0]["name"]) is not str or not subjects[0]["name"]):
        _fail("ambiguous_attestation_subject", "artifact attestation must have exactly one subject")
    digest = subjects[0].get("digest")
    if (type(digest) is not dict or set(digest) != {"sha256"}
            or type(digest["sha256"]) is not str
            or digest["sha256"] != artifact_sha256):
        _fail("attestation_subject_mismatch", "artifact attestation subject digest does not match")
    certificate = signature["certificate"]
    expected_certificate = {
        "subjectAlternativeName": workflow_identity,
        "issuer": "https://token.actions.githubusercontent.com",
        "sourceRepositoryURI": f"https://github.com/{repository}",
        "sourceRepositoryRef": source_ref,
        "sourceRepositoryDigest": source_commit,
        "buildConfigURI": workflow_identity,
        "buildConfigDigest": source_commit,
        "buildSignerURI": workflow_identity,
        "buildSignerDigest": source_commit,
        "githubWorkflowRepository": repository,
        "githubWorkflowRef": source_ref,
        "githubWorkflowSHA": source_commit,
        "githubWorkflowTrigger": "workflow_dispatch",
        "buildTrigger": "workflow_dispatch",
        "runnerEnvironment": "github-hosted",
        "runInvocationURI": (
            f"https://github.com/{repository}/actions/runs/{run_id}/attempts/{run_attempt}"
        ),
    }
    for name, expected in expected_certificate.items():
        if certificate.get(name) != expected:
            _fail(
                "attestation_certificate_mismatch",
                f"verified attestation certificate has the wrong {name}",
            )
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _verify_artifact_attestation(*, artifact_payload: bytes, artifact_sha256: str,
                                 registry: Mapping[str, Any], signer_role: str,
                                 source_commit: str, expected_run_id: str,
                                 expected_run_attempt: str) -> tuple[str, str]:
    if hashlib.sha256(artifact_payload).hexdigest() != artifact_sha256:
        _fail("artifact_changed", "artifact changed before attestation verification")
    workflow = registry[f"{signer_role}_workflow"]
    identity = f"https://github.com/{registry['repository']}/{workflow}@{registry['main_ref']}"
    # Verify a private immutable copy of the exact bytes inspected above.  The
    # untrusted download pathname can therefore not be swapped between hashing
    # and cryptographic verification.
    verifier_fd, binary, binary_sha = _verified_verifier_memfd(registry)
    try:
        with tempfile.TemporaryDirectory(prefix="tdb-attestation-") as temp:
            verified_artifact = Path(temp) / "artifact.json"
            _write_exclusive(verified_artifact, artifact_payload)
            command = [
                binary, "attestation", "verify", str(verified_artifact.resolve()),
                "--repo", registry["repository"],
                "--cert-identity", identity,
                "--cert-oidc-issuer", "https://token.actions.githubusercontent.com",
                "--deny-self-hosted-runners",
                "--predicate-type", SLSA_PREDICATE,
                "--source-ref", registry["main_ref"],
                "--source-digest", source_commit,
                "--signer-digest", source_commit,
                "--format", "json",
            ]
            returncode, stdout = _run_bounded_stdout(
                command, timeout=90, env=_attestation_environment(),
                limit=MAX_JSON_BYTES, pass_fds=(verifier_fd,),
            )
    finally:
        os.close(verifier_fd)
    if returncode != 0:
        _fail("attestation_verification_failed", "artifact attestation verification failed")
    evidence_sha = _parse_attestation_result(
        stdout, artifact_sha256=artifact_sha256,
        repository=registry["repository"], workflow_identity=identity,
        source_ref=registry["main_ref"], source_commit=source_commit,
        run_id=expected_run_id, run_attempt=expected_run_attempt,
    )
    return evidence_sha, binary_sha


def _evaluate_controls(candidate: Mapping[str, Any], *, candidate_path: Path,
                       candidate_sha256: str, authority_root: Path,
                       registry: Mapping[str, Any], runtime: Mapping[str, str],
                       api: Any) -> tuple[Dict[str, bool], str, str, Dict[str, Any]]:
    if registry["active"] is not True:
        _fail("deployment_inactive", "receipt authority deployment is explicitly inactive")
    if not all(registry["deployment_declarations"].values()):
        _fail("deployment_incomplete", "one or more deployment controls are undeclared")
    controls = {name: False for name in CONTROLS}

    _verify_live_main_head(api, registry, runtime["source_commit"])
    _verify_main_branch(api, registry)
    controls["main_branch_protection_verified"] = True
    _verify_environment(api, _environment_policy(registry, "importer"))
    controls["replay_promoter_environment_verified"] = True
    actor_evidence = _collect_import_actor_evidence(
        candidate, api=api, registry=registry, runtime=runtime,
    )
    public_key_sha = _match_authority_rows(candidate, authority_root, registry)
    controls["trusted_signer_registry_verified"] = True
    _verify_workflow_files(authority_root, registry)
    controls["trusted_workflow_registry_verified"] = True
    attestation_sha, _ = _verify_artifact_attestation(
        artifact_payload=_stable_file(candidate_path, label="promotion candidate"),
        artifact_sha256=candidate_sha256, registry=registry,
        signer_role="candidate", source_commit=runtime["source_commit"],
        expected_run_id=candidate["verifier"]["run_id"],
        expected_run_attempt=candidate["verifier"]["run_attempt"],
    )
    controls["artifact_attestation_importer_verified"] = True
    _verify_environment(api, _environment_policy(registry, "publisher"))
    _verify_ledger_exists(api, registry, source_commit=runtime["source_commit"])
    controls["publisher_import_boundary_verified"] = True
    _verify_live_main_head(api, registry, runtime["source_commit"])
    if not all(controls.values()):
        _fail("deployment_incomplete", "one or more independently checked controls failed")
    return controls, public_key_sha, attestation_sha, actor_evidence


def import_candidate(*, candidate_path: Path, registry_path: Path,
                     authority_root: Path, expected_run_id: str,
                     expected_run_attempt: str, expected_candidate_sha256: str,
                     out: Path,
                     api: Optional[Any] = None,
                     environ: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """Verify and import one still-unranked candidate into an attested record."""
    registry = load_registry(registry_path)
    runtime = _runtime_context(registry, "importer", environ)
    if not _RUN_ID_RE.fullmatch(expected_run_id) or not _RUN_ID_RE.fullmatch(expected_run_attempt):
        _fail("invalid_candidate_run", "expected candidate run identity is invalid")
    if not _SHA256_RE.fullmatch(expected_candidate_sha256):
        _fail("invalid_candidate_pin", "operator-pinned candidate digest is invalid")
    payload = _stable_file(candidate_path, label="promotion candidate")
    candidate_sha = hashlib.sha256(payload).hexdigest()
    if candidate_sha != expected_candidate_sha256:
        _fail("candidate_pin_mismatch", "candidate does not match the operator-pinned digest")
    candidate = _validate_candidate(
        payload, registry, runtime, expected_run_id=expected_run_id,
        expected_run_attempt=expected_run_attempt,
    )
    if api is None:
        source_env = os.environ if environ is None else environ
        token = source_env.get("GH_TOKEN", "") or source_env.get("GITHUB_TOKEN", "")
        api = GitHubAPI(token, repository=registry["repository"])
    controls, public_key_sha, attestation_sha, actor_evidence = _evaluate_controls(
        candidate, candidate_path=candidate_path, candidate_sha256=candidate_sha,
        authority_root=authority_root, registry=registry, runtime=runtime, api=api,
    )
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    body: Dict[str, Any] = {
        "schema": IMPORT_SCHEMA,
        "status": "authority_controls_verified_pending_publisher",
        "eligible_for_leaderboard": False,
        "candidate_sha256": candidate_sha,
        "bundle_sha256": candidate["bundle_sha256"],
        "submission_id": candidate["submission_id"],
        "attempt_id": candidate["attempt_id"],
        "suite_sha256": candidate["suite_sha256"],
        "receipt_sha256": candidate["receipt_sha256"],
        "receipt_key_id": candidate["receipt_key_id"],
        "receipt_public_key_sha256": public_key_sha,
        "reward": candidate["reward"],
        "signer_euid": candidate["signer_euid"],
        "candidate_attestation_sha256": attestation_sha,
        "source_commit": runtime["source_commit"],
        "registry_sha256": registry["_sha256"],
        "importer": {
            "repository": runtime["repository"], "ref": runtime["ref"],
            "workflow_ref": runtime["workflow_ref"], "run_id": runtime["run_id"],
            "run_attempt": runtime["run_attempt"], "environment": runtime["environment"],
            "runner_environment": runtime["runner_environment"],
        },
        "actor_separation": actor_evidence,
        "deployment_gate": {
            "status": "all_controls_verified_pending_publisher",
            "ready": True,
            "controls": controls,
        },
        "imported_at": now,
    }
    record = {**body, "import_id": hashlib.sha256(IMPORT_DOMAIN + _canonical_json(body)).hexdigest()}
    _write_exclusive(out, _canonical_json(record) + b"\n")
    return record


def _validate_import_record(payload: bytes, registry: Mapping[str, Any],
                            runtime: Mapping[str, str]) -> Dict[str, Any]:
    record = _exact_fields(
        _strict_json(payload, label="authority import record"), IMPORT_FIELDS,
        code="invalid_import_schema", label="authority import record",
    )
    if payload != _canonical_json(record) + b"\n":
        _fail("noncanonical_import", "authority import record bytes are not canonical")
    if (record["schema"] != IMPORT_SCHEMA
            or record["status"] != "authority_controls_verified_pending_publisher"
            or record["eligible_for_leaderboard"] is not False):
        _fail("invalid_import_state", "authority import record is not pending publication")
    for name in (
        "candidate_sha256", "bundle_sha256", "submission_id", "suite_sha256",
        "receipt_sha256", "receipt_public_key_sha256", "candidate_attestation_sha256",
        "registry_sha256", "import_id",
    ):
        if not isinstance(record[name], str) or not _SHA256_RE.fullmatch(record[name]):
            _fail("invalid_import_schema", f"authority import {name} is invalid")
    if (not isinstance(record["attempt_id"], str)
            or not _ATTEMPT_ID_RE.fullmatch(record["attempt_id"])
            or not isinstance(record["receipt_key_id"], str)
            or not _KEY_ID_RE.fullmatch(record["receipt_key_id"])):
        _fail("invalid_import_schema", "authority import identity is invalid")
    if (type(record["reward"]) is not float or not math.isfinite(record["reward"])
            or not 0.0 <= record["reward"] <= 1.0
            or type(record["signer_euid"]) is not int
            or isinstance(record["signer_euid"], bool) or record["signer_euid"] < 1):
        _fail("import_type_confusion", "authority import numeric fields are invalid")
    _utc_timestamp(record["imported_at"], code="invalid_import_schema", label="import time")
    importer = _exact_fields(
        record["importer"], IMPORTER_FIELDS,
        code="invalid_import_schema", label="importer identity",
    )
    expected_importer_ref = (
        f"{registry['repository']}/{registry['importer_workflow']}@{registry['main_ref']}"
    )
    if (importer["repository"] != registry["repository"]
            or importer["ref"] != registry["main_ref"]
            or importer["workflow_ref"] != expected_importer_ref
            or not isinstance(importer["run_id"], str)
            or not _RUN_ID_RE.fullmatch(importer["run_id"])
            or not isinstance(importer["run_attempt"], str)
            or not _RUN_ID_RE.fullmatch(importer["run_attempt"])
            or importer["environment"] != registry["importer_environment"]
            or importer["runner_environment"] != "github-hosted"):
        _fail("wrong_importer", "authority import record has the wrong importer identity")
    actor_evidence = _exact_fields(
        record["actor_separation"], IMPORT_ACTOR_FIELDS,
        code="invalid_import_schema", label="import actor-separation evidence",
    )
    for name in ("candidate_run_id", "candidate_run_attempt", "importer_run_id", "importer_run_attempt"):
        if not isinstance(actor_evidence[name], str) or not _RUN_ID_RE.fullmatch(actor_evidence[name]):
            _fail("invalid_import_schema", "import actor run identity is invalid")
    if (actor_evidence["importer_run_id"] != importer["run_id"]
            or actor_evidence["importer_run_attempt"] != importer["run_attempt"]):
        _fail("invalid_import_schema", "import actor evidence disagrees with importer identity")
    for name in ("candidate_actor_ids", "importer_actor_ids", "importer_reviewer_ids"):
        values = actor_evidence[name]
        if (type(values) is not list or not values
                or any(type(value) is not int or value < 1 for value in values)
                or values != sorted(set(values))):
            _fail("invalid_import_schema", "import actor identity list is not canonical")
    _require_disjoint(
        actor_evidence["candidate_actor_ids"], actor_evidence["importer_reviewer_ids"],
        message="candidate actor appears in import approval evidence",
    )
    _require_disjoint(
        actor_evidence["importer_actor_ids"], actor_evidence["importer_reviewer_ids"],
        message="import actor appears in its own approval evidence",
    )
    gate = _exact_fields(
        record["deployment_gate"], frozenset({"status", "ready", "controls"}),
        code="invalid_import_schema", label="import deployment gate",
    )
    controls = _exact_fields(
        gate["controls"], frozenset(CONTROLS),
        code="invalid_import_schema", label="import deployment controls",
    )
    if (gate["status"] != "all_controls_verified_pending_publisher"
            or gate["ready"] is not True or any(value is not True for value in controls.values())):
        _fail("incomplete_import_controls", "authority import record lacks all deployment controls")
    body = {key: value for key, value in record.items() if key != "import_id"}
    if record["import_id"] != hashlib.sha256(IMPORT_DOMAIN + _canonical_json(body)).hexdigest():
        _fail("import_digest_mismatch", "authority import record digest is invalid")
    if record["source_commit"] != runtime["source_commit"]:
        _fail("stale_import_source", "authority import does not match publisher source commit")
    if record["registry_sha256"] != registry["_sha256"]:
        _fail("stale_import_registry", "authority import does not match the current main registry")
    return record


def _record_as_candidate(record: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "suite_sha256": record["suite_sha256"],
        "receipt_key_id": record["receipt_key_id"],
        "signer_euid": record["signer_euid"],
    }


def _collect_publisher_actor_evidence(record: Mapping[str, Any], *, api: Any,
                                      registry: Mapping[str, Any],
                                      runtime: Mapping[str, str]) -> Dict[str, Any]:
    evidence = record["actor_separation"]
    candidate_actors = _workflow_run_actors(
        api, registry, role="candidate", run_id=evidence["candidate_run_id"],
        run_attempt=evidence["candidate_run_attempt"],
        source_commit=runtime["source_commit"], require_success=True,
    )
    importer_actors = _workflow_run_actors(
        api, registry, role="importer", run_id=evidence["importer_run_id"],
        run_attempt=evidence["importer_run_attempt"],
        source_commit=runtime["source_commit"], require_success=True,
    )
    importer_reviewers = _approval_actor_ids(
        api, _environment_policy(registry, "importer"),
        run_id=evidence["importer_run_id"],
    )
    if (list(candidate_actors) != evidence["candidate_actor_ids"]
            or list(importer_actors) != evidence["importer_actor_ids"]
            or list(importer_reviewers) != evidence["importer_reviewer_ids"]):
        _fail("stale_actor_evidence", "import actor evidence no longer matches GitHub review history")
    _require_disjoint(
        candidate_actors, importer_reviewers,
        message="candidate actor appears in re-checked import approval evidence",
    )
    _require_disjoint(
        importer_actors, importer_reviewers,
        message="import actor appears in re-checked self-approval evidence",
    )

    publisher_actors = _workflow_run_actors(
        api, registry, role="publisher", run_id=runtime["run_id"],
        run_attempt=runtime["run_attempt"], source_commit=runtime["source_commit"],
        require_success=False,
    )
    publisher_reviewers = _approval_actor_ids(
        api, _environment_policy(registry, "publisher"), run_id=runtime["run_id"],
    )
    _require_disjoint(
        candidate_actors, publisher_reviewers,
        message="candidate workflow actor cannot approve final publication",
    )
    _require_disjoint(
        importer_actors, publisher_reviewers,
        message="import workflow actor cannot approve final publication",
    )
    _require_disjoint(
        publisher_actors, publisher_reviewers,
        message="publisher workflow actor cannot approve its own protected environment",
    )
    return {
        **evidence,
        "publisher_run_id": runtime["run_id"],
        "publisher_run_attempt": runtime["run_attempt"],
        "publisher_actor_ids": list(publisher_actors),
        "publisher_reviewer_ids": list(publisher_reviewers),
    }


def _publisher_controls(record: Mapping[str, Any], *, import_path: Path,
                        import_sha256: str, authority_root: Path,
                        registry: Mapping[str, Any], runtime: Mapping[str, str],
                        api: Any) -> tuple[Dict[str, bool], str, Dict[str, Any]]:
    if registry["active"] is not True or not all(registry["deployment_declarations"].values()):
        _fail("deployment_inactive", "receipt authority deployment is inactive or incomplete")
    controls = {name: False for name in CONTROLS}
    _verify_live_main_head(api, registry, runtime["source_commit"])
    _verify_main_branch(api, registry)
    controls["main_branch_protection_verified"] = True
    _verify_environment(api, _environment_policy(registry, "importer"))
    controls["replay_promoter_environment_verified"] = True
    actor_evidence = _collect_publisher_actor_evidence(
        record, api=api, registry=registry, runtime=runtime,
    )
    public_key = _match_authority_rows(_record_as_candidate(record), authority_root, registry)
    if public_key != record["receipt_public_key_sha256"]:
        _fail("authority_registry_mismatch", "import record no longer matches receipt-key registry")
    controls["trusted_signer_registry_verified"] = True
    _verify_workflow_files(authority_root, registry)
    controls["trusted_workflow_registry_verified"] = True
    attestation_sha, _ = _verify_artifact_attestation(
        artifact_payload=_stable_file(import_path, label="authority import record"),
        artifact_sha256=import_sha256, registry=registry,
        signer_role="importer", source_commit=runtime["source_commit"],
        expected_run_id=record["importer"]["run_id"],
        expected_run_attempt=record["importer"]["run_attempt"],
    )
    controls["artifact_attestation_importer_verified"] = True
    _verify_environment(api, _environment_policy(registry, "publisher"))
    _verify_ledger_exists(api, registry, source_commit=runtime["source_commit"])
    controls["publisher_import_boundary_verified"] = True
    _verify_live_main_head(api, registry, runtime["source_commit"])
    return controls, attestation_sha, actor_evidence


def _ledger_paths(registry: Mapping[str, Any], record: Mapping[str, Any],
                  import_sha: str, import_attestation_sha: str) -> Dict[str, str]:
    prefix = registry["publisher_ledger"]["path_prefix"].rstrip("/")
    return {
        "entry": f"{prefix}/entries/{record['import_id']}.json",
        "candidate": f"{prefix}/index/candidate/{record['candidate_sha256']}.json",
        "receipt": f"{prefix}/index/receipt/{record['receipt_sha256']}.json",
        "import_record": f"{prefix}/index/import-record/{import_sha}.json",
        "import_attestation": f"{prefix}/index/import-attestation/{import_attestation_sha}.json",
    }


def _publish_to_ledger(api: Any, registry: Mapping[str, Any], publication: Mapping[str, Any],
                       *, import_sha: str, import_attestation_sha: str,
                       source_commit: str) -> str:
    ledger = registry["publisher_ledger"]
    # Re-establish the live main/ledger boundary immediately before deriving the
    # compare-and-swap parent.  Earlier control checks cannot authorize a write
    # after main is revoked or the protected ledger history changes.
    old_commit = _verify_ledger_exists(api, registry, source_commit=source_commit)
    commit = api.get(f"git/commits/{old_commit}")
    tree = commit.get("tree") if type(commit) is dict else None
    tree_sha = tree.get("sha") if type(tree) is dict else None
    if not isinstance(tree_sha, str) or not _GIT_OBJECT_RE.fullmatch(tree_sha):
        _fail("publisher_ledger_invalid", "publisher ledger commit has no valid tree")
    listing = api.get(f"git/trees/{tree_sha}?recursive=1")
    if type(listing) is not dict or listing.get("truncated") is not False or type(listing.get("tree")) is not list:
        _fail("publisher_ledger_invalid", "publisher ledger tree cannot be exhaustively checked")
    existing = {
        item.get("path") for item in listing["tree"]
        if type(item) is dict and isinstance(item.get("path"), str)
    }
    paths = _ledger_paths(registry, publication, import_sha, import_attestation_sha)
    duplicates = sorted(set(paths.values()) & existing)
    if duplicates:
        _fail("authority_replay", "candidate, receipt or import evidence has already been published")
    payload = _canonical_json(publication) + b"\n"
    marker = _canonical_json({
        "schema": "terminal-daily-receipt-authority-ledger-index/v1",
        "publication_id": publication["publication_id"],
    }) + b"\n"
    blobs: Dict[str, str] = {}
    for name, path in paths.items():
        content = payload if name == "entry" else marker
        blob = api.post("git/blobs", {
            "content": base64.b64encode(content).decode("ascii"), "encoding": "base64",
        })
        sha = blob.get("sha") if type(blob) is dict else None
        if not isinstance(sha, str) or not _GIT_OBJECT_RE.fullmatch(sha):
            _fail("publisher_ledger_write_failed", "GitHub rejected an authority ledger blob")
        blobs[path] = sha
    new_tree = api.post("git/trees", {
        "base_tree": tree_sha,
        "tree": [
            {"path": path, "mode": "100644", "type": "blob", "sha": blobs[path]}
            for path in sorted(blobs)
        ],
    })
    new_tree_sha = new_tree.get("sha") if type(new_tree) is dict else None
    if not isinstance(new_tree_sha, str) or not _GIT_OBJECT_RE.fullmatch(new_tree_sha):
        _fail("publisher_ledger_write_failed", "GitHub rejected the authority ledger tree")
    new_commit = api.post("git/commits", {
        "message": f"authority: publish {publication['publication_id']}",
        "tree": new_tree_sha,
        "parents": [old_commit],
    })
    new_commit_sha = new_commit.get("sha") if type(new_commit) is dict else None
    if not isinstance(new_commit_sha, str) or not _COMMIT_RE.fullmatch(new_commit_sha):
        _fail("publisher_ledger_write_failed", "GitHub rejected the authority ledger commit")
    current_commit = _verify_ledger_exists(
        api, registry, source_commit=source_commit,
    )
    if current_commit != old_commit:
        _fail("publisher_ledger_cas_failed", "authority ledger changed before compare-and-swap")
    updated = api.patch(
        f"git/refs/heads/{quote(ledger['branch'], safe='')}",
        {"sha": new_commit_sha, "force": False},
    )
    updated_obj = updated.get("object") if type(updated) is dict else None
    if type(updated_obj) is not dict or updated_obj.get("sha") != new_commit_sha:
        _fail("publisher_ledger_cas_failed", "authority ledger compare-and-swap failed")
    return new_commit_sha


def publish_import(*, import_path: Path, registry_path: Path, authority_root: Path,
                   expected_import_sha256: str, out: Path,
                   api: Optional[Any] = None,
                   environ: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """Verify an attested import and atomically append it to the authority ledger."""
    if not _SHA256_RE.fullmatch(expected_import_sha256):
        _fail("invalid_import_pin", "operator-pinned import digest is invalid")
    registry = load_registry(registry_path)
    runtime = _runtime_context(registry, "publisher", environ)
    payload = _stable_file(import_path, label="authority import record")
    import_sha = hashlib.sha256(payload).hexdigest()
    if import_sha != expected_import_sha256:
        _fail("import_pin_mismatch", "authority import does not match the operator-pinned digest")
    record = _validate_import_record(payload, registry, runtime)
    if api is None:
        source_env = os.environ if environ is None else environ
        token = source_env.get("GH_TOKEN", "") or source_env.get("GITHUB_TOKEN", "")
        api = GitHubAPI(token, repository=registry["repository"])
    controls, import_attestation_sha, actor_evidence = _publisher_controls(
        record, import_path=import_path, import_sha256=import_sha,
        authority_root=authority_root, registry=registry, runtime=runtime, api=api,
    )
    if not all(controls.values()):
        _fail("deployment_incomplete", "publisher did not independently re-establish all controls")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    body: Dict[str, Any] = {
        "schema": PUBLISH_SCHEMA,
        "status": "authorized_in_authority_ledger",
        "eligible_for_leaderboard": True,
        "import_id": record["import_id"],
        "import_record_sha256": import_sha,
        "candidate_sha256": record["candidate_sha256"],
        "bundle_sha256": record["bundle_sha256"],
        "submission_id": record["submission_id"],
        "attempt_id": record["attempt_id"],
        "suite_sha256": record["suite_sha256"],
        "receipt_sha256": record["receipt_sha256"],
        "receipt_key_id": record["receipt_key_id"],
        "reward": record["reward"],
        "candidate_attestation_sha256": record["candidate_attestation_sha256"],
        "import_attestation_sha256": import_attestation_sha,
        "source_commit": runtime["source_commit"],
        "registry_sha256": registry["_sha256"],
        "publisher": {
            "repository": runtime["repository"], "ref": runtime["ref"],
            "workflow_ref": runtime["workflow_ref"], "run_id": runtime["run_id"],
            "run_attempt": runtime["run_attempt"], "environment": runtime["environment"],
            "runner_environment": runtime["runner_environment"],
        },
        "actor_separation": actor_evidence,
        "deployment_gate": {
            "status": "all_controls_verified_and_published",
            "ready": True,
            "controls": controls,
        },
        "published_at": now,
    }
    publication = {
        **body,
        "publication_id": hashlib.sha256(PUBLISH_DOMAIN + _canonical_json(body)).hexdigest(),
    }
    commit_sha = _publish_to_ledger(
        api, registry, publication, import_sha=import_sha,
        import_attestation_sha=import_attestation_sha,
        source_commit=runtime["source_commit"],
    )
    result = {**publication, "ledger_commit": commit_sha}
    _write_exclusive(out, _canonical_json(result) + b"\n")
    return result


def _write_blocked(path: Path, *, stage: str, error: AuthorityError,
                   artifact_path: Optional[Path]) -> None:
    artifact_sha: Optional[str] = None
    if artifact_path is not None:
        try:
            artifact_sha = hashlib.sha256(_stable_file(artifact_path, label="blocked artifact")).hexdigest()
        except AuthorityError:
            artifact_sha = None
    blocked = {
        "schema": BLOCKED_SCHEMA,
        "status": "unranked_authority_blocked",
        "eligible_for_leaderboard": False,
        "stage": stage,
        "error_code": error.code,
        "artifact_sha256": artifact_sha,
        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    _write_exclusive(path, _canonical_json(blocked) + b"\n")


def _main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser("import", help="verify an unranked candidate attestation")
    importer.add_argument("--candidate", type=Path, required=True)
    importer.add_argument("--registry", type=Path, required=True)
    importer.add_argument("--authority-root", type=Path, required=True)
    importer.add_argument("--expected-run-id", required=True)
    importer.add_argument("--expected-run-attempt", required=True)
    importer.add_argument("--expected-candidate-sha256", required=True)
    importer.add_argument("--out", type=Path, required=True)
    importer.add_argument("--blocked-out", type=Path, required=True)
    publisher = commands.add_parser("publish", help="verify an import and append authority ledger")
    publisher.add_argument("--import-record", type=Path, required=True)
    publisher.add_argument("--registry", type=Path, required=True)
    publisher.add_argument("--authority-root", type=Path, required=True)
    publisher.add_argument("--expected-import-sha256", required=True)
    publisher.add_argument("--out", type=Path, required=True)
    publisher.add_argument("--blocked-out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "import":
            record = import_candidate(
                candidate_path=args.candidate, registry_path=args.registry,
                authority_root=args.authority_root, expected_run_id=args.expected_run_id,
                expected_run_attempt=args.expected_run_attempt,
                expected_candidate_sha256=args.expected_candidate_sha256, out=args.out,
            )
            print(json.dumps({
                "status": record["status"], "eligible_for_leaderboard": False,
                "import_id": record["import_id"],
            }, sort_keys=True))
            return 0
        publication = publish_import(
            import_path=args.import_record, registry_path=args.registry,
            authority_root=args.authority_root,
            expected_import_sha256=args.expected_import_sha256, out=args.out,
        )
        print(json.dumps({
            "status": publication["status"], "eligible_for_leaderboard": True,
            "publication_id": publication["publication_id"],
            "ledger_commit": publication["ledger_commit"],
        }, sort_keys=True))
        return 0
    except AuthorityError as exc:
        artifact = args.candidate if args.command == "import" else args.import_record
        _write_blocked(args.blocked_out, stage=args.command, error=exc, artifact_path=artifact)
        print(json.dumps({
            "status": "unranked_authority_blocked",
            "eligible_for_leaderboard": False,
            "error_code": exc.code,
        }, sort_keys=True))
        return 3


if __name__ == "__main__":
    raise SystemExit(_main())
