#!/usr/bin/env python3
"""Publish the frozen W1 task environments to one OCI registry repository.

The W1 ``.sif`` files are deterministic gzip-compressed OCI image-layout
archives (despite their historical suffix).  This program verifies the
certified archive identity before unpacking it, publishes each unique OCI
object exactly once, and gives every task a stable alias.

No credential is accepted on the command line.  ``crane`` must already be
authenticated by the caller (for example via an owner-only DOCKER_CONFIG).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


DEFAULT_ROSTER = Path(
    "/shared_nfs/daidong/terminal-daily-benchmark-baselines/"
    "w1-scratch-replay-2026-08-17-v1/runtime/new-run/"
    "generate-repro-raw-r007-primus/W1_FIXED50_FROZEN_TASK_ROSTER.json"
)
DEFAULT_ROSTER_SHA256 = (
    "44b722079e4b47901b21f4086f77001fe8578b7279be62773ca347222bfaf6f1"
)
# Pre-existing full-stream audit provenance for this exact roster's 49 objects.
# Its historical canonicalization is not redefined by this publisher; the script
# emits a separate, self-described publication-plan digest below.
CERTIFIED_OBJECT_SET_AUDIT_SHA256 = (
    "fc24fd6ade825990723f431a69cd389665ffb77da35f02e3bbb4e7f3306b6f91"
)
DEFAULT_REPOSITORY = "ghcr.io/daizedong/terminal-daily-task-envs"
EXPECTED_TASKS = 50
EXPECTED_IMAGES = 49
OCI_INDEX = "application/vnd.oci.image.index.v1+json"
OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TASK_RE = re.compile(r"^td-[0-9a-f]{16}$")
TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")


class PublishError(RuntimeError):
    """A fail-closed publication or validation error."""


@dataclasses.dataclass(frozen=True)
class ImagePlan:
    archive_sha256: str
    archive_size: int
    archive_path: Path
    task_ids: tuple[str, ...]

    @property
    def primary_tag(self) -> str:
        return f"img-{self.archive_sha256[:16]}"

    @property
    def task_tags(self) -> tuple[str, ...]:
        return tuple(f"task-{task_id}" for task_id in self.task_ids)

    @property
    def tags(self) -> tuple[str, ...]:
        return (self.primary_tag, *self.task_tags)


@dataclasses.dataclass(frozen=True)
class OciIdentity:
    top_digest: str
    linux_amd64_digest: str


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary_path.unlink(missing_ok=True)


def _require_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise PublishError(f"{field} is not a lowercase SHA-256: {value!r}")
    return value


def _resolve_inside(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    root = root.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PublishError(f"archive path escapes authority root: {relative!r}") from exc
    return candidate


def load_plan(
    roster_path: Path,
    expected_roster_sha256: str | None = DEFAULT_ROSTER_SHA256,
    *,
    enforce_fixed50: bool = True,
) -> tuple[list[ImagePlan], dict[str, Any]]:
    """Load and strictly validate the frozen roster, then deduplicate by bytes."""
    roster_path = roster_path.resolve()
    if not roster_path.is_file():
        raise PublishError(f"roster is not a regular file: {roster_path}")
    roster_sha256 = _sha256_file(roster_path)
    if expected_roster_sha256 and roster_sha256 != expected_roster_sha256:
        raise PublishError(
            "roster SHA-256 mismatch: "
            f"expected {expected_roster_sha256}, got {roster_sha256}"
        )
    try:
        roster = json.loads(roster_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishError(f"cannot parse roster {roster_path}: {exc}") from exc
    if not isinstance(roster, dict) or roster.get("schema") != "td-frozen-task-roster-v1":
        raise PublishError("unexpected frozen roster schema")
    tasks = roster.get("tasks")
    if not isinstance(tasks, list) or roster.get("count") != len(tasks):
        raise PublishError("roster count does not match tasks")
    if enforce_fixed50 and len(tasks) != EXPECTED_TASKS:
        raise PublishError(f"expected {EXPECTED_TASKS} tasks, got {len(tasks)}")

    authority_root_value = roster.get("authority_root", ".")
    if not isinstance(authority_root_value, str):
        raise PublishError("authority_root must be a string")
    authority_root = _resolve_inside(roster_path.parent, authority_root_value)
    grouped: dict[str, dict[str, Any]] = {}
    seen_tasks: set[str] = set()
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise PublishError(f"tasks[{index}] is not an object")
        task_id = task.get("task_id")
        if not isinstance(task_id, str) or not TASK_RE.fullmatch(task_id):
            raise PublishError(f"tasks[{index}].task_id is invalid: {task_id!r}")
        if task_id in seen_tasks:
            raise PublishError(f"duplicate task_id: {task_id}")
        seen_tasks.add(task_id)
        archive_sha256 = _require_sha256(
            task.get("task_sif_sha256"), f"tasks[{index}].task_sif_sha256"
        )
        archive_size = task.get("task_sif_size")
        if not isinstance(archive_size, int) or isinstance(archive_size, bool) or archive_size <= 0:
            raise PublishError(f"tasks[{index}].task_sif_size is invalid")
        relative_path = task.get("task_sif_path")
        if not isinstance(relative_path, str) or not relative_path:
            raise PublishError(f"tasks[{index}].task_sif_path is invalid")
        archive_path = _resolve_inside(authority_root, relative_path)
        current = grouped.setdefault(
            archive_sha256,
            {"size": archive_size, "path": archive_path, "task_ids": []},
        )
        if current["size"] != archive_size:
            raise PublishError(f"same archive SHA has conflicting sizes: {archive_sha256}")
        if current["path"] != archive_path:
            raise PublishError(f"same archive SHA has conflicting paths: {archive_sha256}")
        current["task_ids"].append(task_id)

    plans = [
        ImagePlan(sha, value["size"], value["path"], tuple(sorted(value["task_ids"])))
        for sha, value in sorted(grouped.items())
    ]
    if enforce_fixed50 and len(plans) != EXPECTED_IMAGES:
        raise PublishError(f"expected {EXPECTED_IMAGES} unique images, got {len(plans)}")
    metadata = {
        "roster_path": str(roster_path),
        "roster_sha256": roster_sha256,
        "roster_payload_sha256": roster.get("payload_sha256"),
        "task_count": len(tasks),
        "image_count": len(plans),
    }
    if roster_sha256 == DEFAULT_ROSTER_SHA256:
        metadata["certified_object_set_audit_sha256"] = (
            CERTIFIED_OBJECT_SET_AUDIT_SHA256
        )
    return plans, metadata


def verify_archive(plan: ImagePlan) -> None:
    try:
        stat = plan.archive_path.stat()
    except OSError as exc:
        raise PublishError(f"cannot stat archive {plan.archive_path}: {exc}") from exc
    if not plan.archive_path.is_file():
        raise PublishError(f"archive is not a regular file: {plan.archive_path}")
    if stat.st_size != plan.archive_size:
        raise PublishError(
            f"archive size mismatch for {plan.archive_path}: "
            f"expected {plan.archive_size}, got {stat.st_size}"
        )
    actual = _sha256_file(plan.archive_path)
    if actual != plan.archive_sha256:
        raise PublishError(
            f"archive SHA-256 mismatch for {plan.archive_path}: "
            f"expected {plan.archive_sha256}, got {actual}"
        )


def _safe_member_path(destination: Path, name: str) -> Path:
    pure = PurePosixPath(name)
    if not name or pure.is_absolute() or ".." in pure.parts:
        raise PublishError(f"unsafe archive member path: {name!r}")
    if any(part in ("", ".") for part in pure.parts):
        raise PublishError(f"non-canonical archive member path: {name!r}")
    target = destination.joinpath(*pure.parts)
    try:
        target.resolve().relative_to(destination.resolve())
    except ValueError as exc:
        raise PublishError(f"archive member escapes destination: {name!r}") from exc
    return target


def extract_oci_archive(archive_path: Path, destination: Path) -> None:
    """Extract a gzip OCI layout without trusting tar paths or link entries."""
    destination.mkdir(parents=True, exist_ok=False)
    seen: set[str] = set()
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            for member in archive:
                normalized = member.name.rstrip("/")
                if normalized in seen:
                    raise PublishError(f"duplicate archive member: {member.name!r}")
                seen.add(normalized)
                target = _safe_member_path(destination, normalized)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    raise PublishError(
                        f"unsupported archive member type for {member.name!r}; "
                        "links and devices are forbidden"
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise PublishError(f"cannot read archive member: {member.name!r}")
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                if target.stat().st_size != member.size:
                    raise PublishError(f"short extraction for archive member: {member.name!r}")
                target.chmod(0o644)
    except (tarfile.TarError, OSError) as exc:
        if isinstance(exc, PublishError):
            raise
        raise PublishError(f"cannot safely extract {archive_path}: {exc}") from exc


def _read_json(path: Path, what: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishError(f"cannot parse {what} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PublishError(f"{what} is not a JSON object: {path}")
    return value


def _validate_blob(layout: Path, descriptor: Mapping[str, Any], what: str) -> Path:
    digest = descriptor.get("digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise PublishError(f"{what} has a non-SHA-256 digest")
    hex_digest = _require_sha256(digest.removeprefix("sha256:"), f"{what}.digest")
    size = descriptor.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise PublishError(f"{what}.size is invalid")
    blob = layout / "blobs" / "sha256" / hex_digest
    if not blob.is_file():
        raise PublishError(f"{what} blob is missing: {blob}")
    if blob.stat().st_size != size:
        raise PublishError(f"{what} blob size does not match its descriptor")
    if _sha256_file(blob) != hex_digest:
        raise PublishError(f"{what} blob digest does not match its descriptor")
    return blob


def parse_oci_identity(layout: Path) -> OciIdentity:
    oci_layout = _read_json(layout / "oci-layout", "OCI layout marker")
    if oci_layout != {"imageLayoutVersion": "1.0.0"}:
        raise PublishError("unsupported oci-layout marker")
    root_index = _read_json(layout / "index.json", "OCI root index")
    manifests = root_index.get("manifests")
    if root_index.get("schemaVersion") != 2 or not isinstance(manifests, list) or len(manifests) != 1:
        raise PublishError("OCI root index must contain exactly one descriptor")
    top_descriptor = manifests[0]
    if not isinstance(top_descriptor, dict) or top_descriptor.get("mediaType") != OCI_INDEX:
        raise PublishError("OCI root descriptor is not an OCI image index")
    top_blob = _validate_blob(layout, top_descriptor, "top OCI index")
    top_index = _read_json(top_blob, "top OCI index")
    if top_index.get("schemaVersion") != 2:
        raise PublishError("top OCI index has an unsupported schemaVersion")
    child_manifests = top_index.get("manifests")
    if not isinstance(child_manifests, list):
        raise PublishError("top OCI index manifests is not a list")
    linux_descriptors = []
    for descriptor in child_manifests:
        if not isinstance(descriptor, dict):
            raise PublishError("top OCI index contains a non-object descriptor")
        platform = descriptor.get("platform")
        if (
            descriptor.get("mediaType") == OCI_MANIFEST
            and isinstance(platform, dict)
            and platform.get("os") == "linux"
            and platform.get("architecture") == "amd64"
        ):
            linux_descriptors.append(descriptor)
    if len(linux_descriptors) != 1:
        raise PublishError(
            "top OCI index must contain exactly one linux/amd64 image manifest"
        )
    linux_descriptor = linux_descriptors[0]
    linux_blob = _validate_blob(layout, linux_descriptor, "linux/amd64 manifest")
    linux_manifest = _read_json(linux_blob, "linux/amd64 manifest")
    if linux_manifest.get("schemaVersion") != 2:
        raise PublishError("linux/amd64 manifest has an unsupported schemaVersion")
    return OciIdentity(top_descriptor["digest"], linux_descriptor["digest"])


def _run_crane(
    crane: str,
    arguments: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    try:
        result = subprocess.run(
            [crane, *arguments],
            check=False,
            capture_output=True,
            text=True,
            env=dict(env) if env is not None else None,
        )
    except OSError as exc:
        raise PublishError(f"cannot execute crane: {exc}") from exc
    if result.returncode:
        # crane is never passed a credential, so command arguments are safe to report.
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise PublishError(
            f"crane {' '.join(arguments[:2])} failed with exit "
            f"{result.returncode}: {detail}"
        )
    return result.stdout.strip()


def _digest(crane: str, ref: str, *, platform: str | None = None, env=None) -> str:
    arguments = ["digest"]
    if platform:
        arguments.append(f"--platform={platform}")
    arguments.append(ref)
    lines = _run_crane(crane, arguments, env=env).splitlines()
    if not lines:
        raise PublishError(f"crane returned no digest for {ref}")
    value = lines[-1].strip()
    if not value.startswith("sha256:"):
        raise PublishError(f"crane returned an invalid digest for {ref}: {value!r}")
    _require_sha256(value.removeprefix("sha256:"), "crane digest")
    return value


def verify_remote(
    crane: str,
    repository: str,
    identity: OciIdentity,
    tags: Iterable[str],
    *,
    env: Mapping[str, str] | None = None,
) -> None:
    canonical_ref = f"{repository}@{identity.top_digest}"
    if _digest(crane, canonical_ref, env=env) != identity.top_digest:
        raise PublishError(f"canonical registry digest mismatch: {canonical_ref}")
    if _digest(crane, canonical_ref, platform="linux/amd64", env=env) != identity.linux_amd64_digest:
        raise PublishError(f"linux/amd64 registry digest mismatch: {canonical_ref}")
    # The top index also contains a BuildKit attestation manifest whose platform
    # is unknown/unknown.  Validate the runnable platform explicitly so crane
    # does not treat that attestation as an image-platform failure.
    _run_crane(
        crane,
        [
            "validate",
            "--platform=linux/amd64",
            "--fast",
            "--remote",
            canonical_ref,
        ],
        env=env,
    )
    for tag in tags:
        if not TAG_RE.fullmatch(tag):
            raise PublishError(f"invalid registry tag: {tag!r}")
        ref = f"{repository}:{tag}"
        if _digest(crane, ref, env=env) != identity.top_digest:
            raise PublishError(f"registry tag points at the wrong digest: {ref}")


def _checkpoint_path(state_dir: Path, archive_sha256: str) -> Path:
    return state_dir / "objects" / f"{archive_sha256}.json"


def _load_checkpoint(
    path: Path, plan: ImagePlan, repository: str, roster_sha256: str
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishError(f"invalid checkpoint {path}: {exc}") from exc
    expected = {
        "schema": "terminal-daily-image-checkpoint-v1",
        "status": "published",
        "repository": repository,
        "roster_sha256": roster_sha256,
        "archive_sha256": plan.archive_sha256,
        "archive_size": plan.archive_size,
        "task_ids": list(plan.task_ids),
        "tags": list(plan.tags),
    }
    if not isinstance(checkpoint, dict) or any(
        checkpoint.get(key) != value for key, value in expected.items()
    ):
        raise PublishError(f"checkpoint does not match this publication plan: {path}")
    top_digest = str(checkpoint.get("top_oci_digest", ""))
    _require_sha256(top_digest.removeprefix("sha256:"), "checkpoint top_oci_digest")
    _require_sha256(
        str(checkpoint.get("linux_amd64_manifest_digest", "")).removeprefix("sha256:"),
        "checkpoint linux_amd64_manifest_digest",
    )
    if checkpoint.get("canonical_ref") != f"{repository}@{top_digest}":
        raise PublishError(f"checkpoint canonical_ref is inconsistent: {path}")
    return checkpoint


def _publish_one(
    plan: ImagePlan,
    *,
    repository: str,
    roster_sha256: str,
    state_dir: Path,
    temporary_root: Path,
    crane: str,
    resume: bool,
    verify_checkpoints: bool,
) -> dict[str, Any]:
    checkpoint_path = _checkpoint_path(state_dir, plan.archive_sha256)
    checkpoint = _load_checkpoint(checkpoint_path, plan, repository, roster_sha256) if resume else None
    if checkpoint is not None:
        identity = OciIdentity(
            checkpoint["top_oci_digest"], checkpoint["linux_amd64_manifest_digest"]
        )
        if verify_checkpoints:
            verify_remote(crane, repository, identity, plan.tags)
        return checkpoint

    verify_archive(plan)
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f"w1-{plan.archive_sha256[:12]}-", dir=temporary_root
    ) as temporary:
        layout = Path(temporary) / "oci"
        extract_oci_archive(plan.archive_path, layout)
        identity = parse_oci_identity(layout)
        primary_ref = f"{repository}:{plan.primary_tag}"
        _run_crane(crane, ["push", str(layout), primary_ref])
        if _digest(crane, primary_ref) != identity.top_digest:
            raise PublishError(f"pushed digest does not match source OCI index: {primary_ref}")
        canonical_ref = f"{repository}@{identity.top_digest}"
        for tag in plan.task_tags:
            _run_crane(crane, ["tag", canonical_ref, tag])
        verify_remote(crane, repository, identity, plan.tags)

    checkpoint = {
        "schema": "terminal-daily-image-checkpoint-v1",
        "status": "published",
        "published_at": _utc_now(),
        "repository": repository,
        "roster_sha256": roster_sha256,
        "archive_sha256": plan.archive_sha256,
        "archive_size": plan.archive_size,
        "source_archive": str(plan.archive_path),
        "top_oci_digest": identity.top_digest,
        "linux_amd64_manifest_digest": identity.linux_amd64_digest,
        "canonical_ref": f"{repository}@{identity.top_digest}",
        "task_ids": list(plan.task_ids),
        "tags": list(plan.tags),
    }
    _atomic_json(checkpoint_path, checkpoint)
    return checkpoint


def _publication_plan_digest(plans: Sequence[ImagePlan]) -> str:
    objects = [
        {
            "archive_sha256": plan.archive_sha256,
            "archive_size": plan.archive_size,
            "task_ids": list(plan.task_ids),
        }
        for plan in sorted(plans, key=lambda item: item.archive_sha256)
    ]
    return hashlib.sha256(_canonical_json(objects)).hexdigest()


def build_manifest(
    plans: Sequence[ImagePlan],
    checkpoints: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any],
    repository: str,
) -> dict[str, Any]:
    by_sha = {item["archive_sha256"]: item for item in checkpoints}
    if set(by_sha) != {plan.archive_sha256 for plan in plans}:
        raise PublishError("checkpoint set is incomplete or contains unexpected objects")
    images = []
    tasks = []
    for plan in plans:
        item = by_sha[plan.archive_sha256]
        image = {
            "archive_sha256": plan.archive_sha256,
            "archive_size": plan.archive_size,
            "source_archive": str(plan.archive_path),
            "top_oci_digest": item["top_oci_digest"],
            "linux_amd64_manifest_digest": item["linux_amd64_manifest_digest"],
            "canonical_ref": item["canonical_ref"],
            "tags": list(plan.tags),
            "task_ids": list(plan.task_ids),
        }
        images.append(image)
        for task_id in plan.task_ids:
            tasks.append(
                {
                    "task_id": task_id,
                    "archive_sha256": plan.archive_sha256,
                    "archive_size": plan.archive_size,
                    "top_oci_digest": item["top_oci_digest"],
                    "linux_amd64_manifest_digest": item["linux_amd64_manifest_digest"],
                    "registry_ref": f"{repository}:task-{task_id}",
                }
            )
    return {
        "schema": "terminal-daily-w1-fixed50-image-manifest-v1",
        "generated_at": _utc_now(),
        "repository": repository,
        **metadata,
        "publication_plan_sha256": _publication_plan_digest(plans),
        "publication_plan_digest_definition": (
            "sha256(canonical-json(sorted archive_sha256 objects containing "
            "archive_sha256, archive_size, sorted task_ids))"
        ),
        "images": images,
        "tasks": sorted(tasks, key=lambda item: item["task_id"]),
    }


def _dry_run_document(
    plans: Sequence[ImagePlan], metadata: Mapping[str, Any], repository: str
) -> dict[str, Any]:
    return {
        "schema": "terminal-daily-w1-fixed50-image-publication-plan-v1",
        "dry_run": True,
        "repository": repository,
        **metadata,
        "publication_plan_sha256": _publication_plan_digest(plans),
        "publication_plan_digest_definition": (
            "sha256(canonical-json(sorted archive_sha256 objects containing "
            "archive_sha256, archive_size, sorted task_ids))"
        ),
        "objects": [
            {
                "archive_sha256": plan.archive_sha256,
                "archive_size": plan.archive_size,
                "source_archive": str(plan.archive_path),
                "task_ids": list(plan.task_ids),
                "tags": list(plan.tags),
            }
            for plan in plans
        ],
    }


def _verify_public(
    crane: str, repository: str, checkpoints: Sequence[Mapping[str, Any]]
) -> None:
    # An empty Docker config proves the package can be pulled without credentials.
    with tempfile.TemporaryDirectory(prefix="w1-anonymous-docker-config-") as config:
        env = os.environ.copy()
        env["DOCKER_CONFIG"] = config
        for checkpoint in checkpoints:
            verify_remote(
                crane,
                repository,
                OciIdentity(
                    checkpoint["top_oci_digest"],
                    checkpoint["linux_amd64_manifest_digest"],
                ),
                checkpoint["tags"],
                env=env,
            )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    parser.add_argument(
        "--expected-roster-sha256",
        default=DEFAULT_ROSTER_SHA256,
        help="set to an empty string only for development fixtures",
    )
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--crane", default="crane")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--state-dir", type=Path, default=Path(".publish-state/w1-fixed50"))
    parser.add_argument("--temporary-root", type=Path, default=None)
    parser.add_argument(
        "--manifest-out", type=Path, default=Path("docs/registry/w1-fixed50-images.json")
    )
    parser.add_argument(
        "--receipt-out", type=Path, default=Path("docs/registry/w1-fixed50-publish-receipt.json")
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.add_argument(
        "--trust-checkpoints",
        dest="verify_checkpoints",
        action="store_false",
        help="skip remote re-verification of already completed checkpoints",
    )
    parser.add_argument(
        "--verify-public",
        action="store_true",
        help="prove all refs are anonymously pullable using an empty Docker config",
    )
    parser.set_defaults(resume=True, verify_checkpoints=True)
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    if not re.fullmatch(r"[a-z0-9.-]+(?::[0-9]+)?/[A-Za-z0-9._/-]+", args.repository):
        parser.error("--repository must be a registry/repository reference without a tag")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    plans, metadata = load_plan(
        args.roster,
        args.expected_roster_sha256 or None,
        enforce_fixed50=bool(args.expected_roster_sha256),
    )
    if args.dry_run:
        print(json.dumps(_dry_run_document(plans, metadata, args.repository), indent=2))
        return 0
    crane_path = shutil.which(args.crane)
    if crane_path is None:
        raise PublishError(f"crane executable not found: {args.crane}")
    temporary_root = args.temporary_root or (args.state_dir / "tmp")
    results: list[dict[str, Any]] = []
    lock = threading.Lock()

    def publish(plan: ImagePlan) -> dict[str, Any]:
        result = _publish_one(
            plan,
            repository=args.repository,
            roster_sha256=metadata["roster_sha256"],
            state_dir=args.state_dir,
            temporary_root=temporary_root,
            crane=crane_path,
            resume=args.resume,
            verify_checkpoints=args.verify_checkpoints,
        )
        with lock:
            print(
                f"published {plan.archive_sha256[:16]} "
                f"({len(plan.task_ids)} task alias(es))",
                file=sys.stderr,
                flush=True,
            )
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_plan = {executor.submit(publish, plan): plan for plan in plans}
        for future in concurrent.futures.as_completed(future_to_plan):
            plan = future_to_plan[future]
            try:
                results.append(future.result())
            except Exception as exc:
                for pending in future_to_plan:
                    pending.cancel()
                raise PublishError(
                    f"publication failed for archive {plan.archive_sha256}: {exc}"
                ) from exc

    results.sort(key=lambda item: item["archive_sha256"])
    if args.verify_public:
        _verify_public(crane_path, args.repository, results)
    manifest = build_manifest(plans, results, metadata, args.repository)
    _atomic_json(args.manifest_out, manifest)
    manifest_bytes = args.manifest_out.read_bytes()
    receipt = {
        "schema": "terminal-daily-w1-fixed50-publication-receipt-v1",
        "completed_at": _utc_now(),
        "repository": args.repository,
        "public_pull_verified": bool(args.verify_public),
        "roster_sha256": metadata["roster_sha256"],
        "certified_object_set_audit_sha256": metadata.get(
            "certified_object_set_audit_sha256"
        ),
        "publication_plan_sha256": manifest["publication_plan_sha256"],
        "task_count": metadata["task_count"],
        "image_count": metadata["image_count"],
        "manifest_path": str(args.manifest_out),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }
    _atomic_json(args.receipt_out, receipt)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublishError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
