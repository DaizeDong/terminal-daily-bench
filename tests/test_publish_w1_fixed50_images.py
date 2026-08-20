"""Focused tests for the resumable W1 OCI publisher (no registry access)."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "publish_w1_fixed50_images.py"
SPEC = importlib.util.spec_from_file_location("publish_w1_fixed50_images", SCRIPT)
assert SPEC and SPEC.loader
publisher = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = publisher
SPEC.loader.exec_module(publisher)


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _descriptor(data: bytes, media_type: str, **extra):
    return {
        "mediaType": media_type,
        "digest": f"sha256:{hashlib.sha256(data).hexdigest()}",
        "size": len(data),
        **extra,
    }


def _make_oci_archive(path: Path) -> publisher.OciIdentity:
    config = _json_bytes({"architecture": "amd64", "os": "linux"})
    config_descriptor = _descriptor(config, "application/vnd.oci.image.config.v1+json")
    image_manifest = _json_bytes(
        {
            "schemaVersion": 2,
            "mediaType": publisher.OCI_MANIFEST,
            "config": config_descriptor,
            "layers": [],
        }
    )
    image_descriptor = _descriptor(
        image_manifest,
        publisher.OCI_MANIFEST,
        platform={"os": "linux", "architecture": "amd64"},
    )
    attestation = _json_bytes({"schemaVersion": 2, "mediaType": publisher.OCI_MANIFEST})
    attestation_descriptor = _descriptor(
        attestation,
        publisher.OCI_MANIFEST,
        platform={"os": "unknown", "architecture": "unknown"},
    )
    top_index = _json_bytes(
        {
            "schemaVersion": 2,
            "mediaType": publisher.OCI_INDEX,
            "manifests": [image_descriptor, attestation_descriptor],
        }
    )
    top_descriptor = _descriptor(top_index, publisher.OCI_INDEX)
    root_index = _json_bytes(
        {
            "schemaVersion": 2,
            "mediaType": publisher.OCI_INDEX,
            "manifests": [top_descriptor],
        }
    )
    files = {
        "oci-layout": _json_bytes({"imageLayoutVersion": "1.0.0"}),
        "index.json": root_index,
        f"blobs/sha256/{config_descriptor['digest'].split(':')[1]}": config,
        f"blobs/sha256/{image_descriptor['digest'].split(':')[1]}": image_manifest,
        f"blobs/sha256/{attestation_descriptor['digest'].split(':')[1]}": attestation,
        f"blobs/sha256/{top_descriptor['digest'].split(':')[1]}": top_index,
    }
    with tarfile.open(path, "w:gz") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(data))
    return publisher.OciIdentity(top_descriptor["digest"], image_descriptor["digest"])


def _make_roster(path: Path, archive: Path, task_ids: list[str]) -> str:
    archive_bytes = archive.read_bytes()
    tasks = [
        {
            "task_id": task_id,
            "task_sif_path": archive.name,
            "task_sif_sha256": hashlib.sha256(archive_bytes).hexdigest(),
            "task_sif_size": len(archive_bytes),
        }
        for task_id in task_ids
    ]
    path.write_text(
        json.dumps(
            {
                "schema": "td-frozen-task-roster-v1",
                "count": len(tasks),
                "authority_root": ".",
                "payload_sha256": "fixture",
                "tasks": tasks,
            }
        )
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_authoritative_roster_deduplicates_to_49_objects():
    plans, metadata = publisher.load_plan(publisher.DEFAULT_ROSTER)
    assert metadata["task_count"] == 50
    assert metadata["image_count"] == 49
    assert sum(len(plan.task_ids) for plan in plans) == 50
    assert len([plan for plan in plans if len(plan.task_ids) == 2]) == 1


def test_load_verify_extract_and_parse_fixture(tmp_path):
    archive = tmp_path / "image.sif"
    expected_identity = _make_oci_archive(archive)
    roster = tmp_path / "roster.json"
    roster_sha = _make_roster(
        roster, archive, ["td-0000000000000001", "td-0000000000000002"]
    )

    plans, metadata = publisher.load_plan(
        roster, roster_sha, enforce_fixed50=False
    )
    assert metadata["image_count"] == 1
    assert plans[0].tags == (
        f"img-{plans[0].archive_sha256[:16]}",
        "task-td-0000000000000001",
        "task-td-0000000000000002",
    )
    publisher.verify_archive(plans[0])
    layout = tmp_path / "layout"
    publisher.extract_oci_archive(archive, layout)
    assert publisher.parse_oci_identity(layout) == expected_identity


def test_roster_and_archive_identity_are_fail_closed(tmp_path):
    archive = tmp_path / "image.sif"
    _make_oci_archive(archive)
    roster = tmp_path / "roster.json"
    roster_sha = _make_roster(roster, archive, ["td-0000000000000001"])
    with pytest.raises(publisher.PublishError, match="roster SHA-256 mismatch"):
        publisher.load_plan(roster, "0" * 64, enforce_fixed50=False)

    plans, _ = publisher.load_plan(roster, roster_sha, enforce_fixed50=False)
    archive.write_bytes(archive.read_bytes() + b"corrupt")
    with pytest.raises(publisher.PublishError, match="size mismatch"):
        publisher.verify_archive(plans[0])


def test_safe_extractor_rejects_traversal_and_links(tmp_path):
    for name, configure in [
        ("../escape", lambda member: None),
        ("link", lambda member: setattr(member, "type", tarfile.SYMTYPE)),
    ]:
        archive_path = tmp_path / f"bad-{name.replace('/', '_')}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            member = tarfile.TarInfo(name)
            configure(member)
            if member.isreg():
                member.size = 1
                archive.addfile(member, io.BytesIO(b"x"))
            else:
                member.linkname = "elsewhere"
                archive.addfile(member)
        with pytest.raises(publisher.PublishError):
            publisher.extract_oci_archive(archive_path, tmp_path / f"out-{archive_path.stem}")
    assert not (tmp_path.parent / "escape").exists()


def test_publish_runs_push_tags_verify_then_writes_atomic_checkpoint(tmp_path, monkeypatch):
    archive = tmp_path / "image.sif"
    identity = _make_oci_archive(archive)
    roster = tmp_path / "roster.json"
    roster_sha = _make_roster(
        roster, archive, ["td-0000000000000001", "td-0000000000000002"]
    )
    plans, _ = publisher.load_plan(roster, roster_sha, enforce_fixed50=False)
    plan = plans[0]
    calls = []

    def fake_run_crane(crane, arguments, *, env=None):
        calls.append(tuple(arguments))
        return "ok"

    def fake_digest(crane, ref, *, platform=None, env=None):
        calls.append(("digest-fixture", platform, ref))
        return identity.linux_amd64_digest if platform else identity.top_digest

    monkeypatch.setattr(publisher, "_run_crane", fake_run_crane)
    monkeypatch.setattr(publisher, "_digest", fake_digest)
    repository = "ghcr.io/example/task-envs"
    state = tmp_path / "state"
    result = publisher._publish_one(
        plan,
        repository=repository,
        roster_sha256=roster_sha,
        state_dir=state,
        temporary_root=tmp_path / "temporary",
        crane="crane",
        resume=True,
        verify_checkpoints=True,
    )

    assert result["top_oci_digest"] == identity.top_digest
    assert result["linux_amd64_manifest_digest"] == identity.linux_amd64_digest
    push_calls = [call for call in calls if call and call[0] == "push"]
    assert len(push_calls) == 1
    assert push_calls[0][2] == f"{repository}:{plan.primary_tag}"
    assert [call[-1] for call in calls if call and call[0] == "tag"] == list(plan.task_tags)
    assert any(
        call[:4] == ("validate", "--platform=linux/amd64", "--fast", "--remote")
        for call in calls
    )
    checkpoint = publisher._checkpoint_path(state, plan.archive_sha256)
    assert json.loads(checkpoint.read_text()) == result
    assert not list(checkpoint.parent.glob(f".{checkpoint.name}.*"))

    calls.clear()
    resumed = publisher._publish_one(
        plan,
        repository=repository,
        roster_sha256=roster_sha,
        state_dir=state,
        temporary_root=tmp_path / "temporary",
        crane="crane",
        resume=True,
        verify_checkpoints=False,
    )
    assert resumed == result
    assert calls == []


def test_manifest_maps_every_task_to_certified_and_registry_identity(tmp_path):
    archive = tmp_path / "image.sif"
    identity = _make_oci_archive(archive)
    roster = tmp_path / "roster.json"
    roster_sha = _make_roster(
        roster, archive, ["td-0000000000000001", "td-0000000000000002"]
    )
    plans, metadata = publisher.load_plan(roster, roster_sha, enforce_fixed50=False)
    plan = plans[0]
    repository = "ghcr.io/example/task-envs"
    checkpoint = {
        "archive_sha256": plan.archive_sha256,
        "top_oci_digest": identity.top_digest,
        "linux_amd64_manifest_digest": identity.linux_amd64_digest,
        "canonical_ref": f"{repository}@{identity.top_digest}",
    }
    manifest = publisher.build_manifest(plans, [checkpoint], metadata, repository)
    assert len(manifest["images"]) == 1
    assert len(manifest["tasks"]) == 2
    assert {task["archive_sha256"] for task in manifest["tasks"]} == {
        plan.archive_sha256
    }
    assert all(task["registry_ref"].startswith(repository + ":task-td-") for task in manifest["tasks"])
