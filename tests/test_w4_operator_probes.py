"""Regression tests for the W4 operator-only canary evidence boundary."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import paired_egress_canary as probe  # noqa: E402


def _work_root(tmp_path: Path, name: str = "work") -> Path:
    work = tmp_path / name
    work.mkdir(mode=0o700)
    return work


def test_stage_sif_binds_private_read_only_snapshot(tmp_path):
    source = tmp_path / "source.sif"
    original = b"fixture-runtime-image\n" * 64
    source.write_bytes(original)
    work = _work_root(tmp_path)

    staged, digest, facts = probe._stage_sif(source, work)

    assert staged == work / "runtime-image" / "canary.sif"
    assert staged.read_bytes() == original
    assert digest == hashlib.sha256(original).hexdigest()
    assert staged.stat().st_mode & 0o777 == 0o400
    assert facts["source_stat_stable"] is True
    assert facts["source_size"] == facts["staged_size"] == len(original)

    source.write_bytes(b"mutated after the stable copy")
    assert staged.read_bytes() == original
    assert hashlib.sha256(staged.read_bytes()).hexdigest() == digest


def test_stage_sif_rejects_source_symlink(tmp_path):
    source = tmp_path / "source.sif"
    source.write_bytes(b"runtime image")
    link = tmp_path / "linked.sif"
    link.symlink_to(source)

    with pytest.raises(RuntimeError, match="source_symlink_or_unavailable"):
        probe._stage_sif(link, _work_root(tmp_path))


def test_stage_sif_rejects_source_mutation_during_copy(tmp_path):
    source = tmp_path / "source.sif"
    source.write_bytes(b"a" * (2 * 1024 * 1024))
    mutated = False

    def mutate_source() -> None:
        nonlocal mutated
        if mutated:
            return
        mutated = True
        fd = os.open(source, os.O_WRONLY)
        try:
            os.pwrite(fd, b"z", 0)
            os.fchmod(fd, 0o600)
            os.fsync(fd)
        finally:
            os.close(fd)

    with pytest.raises(RuntimeError, match="source_changed_during_staging"):
        probe._stage_sif(
            source, _work_root(tmp_path), _after_chunk=mutate_source,
        )
    assert mutated is True


def test_main_invokes_worker_canary_only_on_staged_sif(tmp_path, monkeypatch):
    source = tmp_path / "source.sif"
    source.write_bytes(b"staged bytes used by fake worker canary")
    runtime = tmp_path / "singularity"
    runtime.write_text("#!/bin/sh\necho 'singularity version test'\n", encoding="utf-8")
    runtime.chmod(0o755)
    work = tmp_path / "work"
    out = tmp_path / "report.json"
    observed = {}

    def fake_canary(*, image, image_sha256, env, execution_policy):
        observed["image"] = image
        observed["digest"] = image_sha256
        observed["kind"] = execution_policy["container_runtime_kind"]
        assert "AWS_SECRET_ACCESS_KEY" not in env
        return {
            "control_reachable": True,
            "isolated_blocked": True,
            "image_sha256": image_sha256,
        }

    monkeypatch.setattr(probe.replay_worker, "_run_egress_canary", fake_canary)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-reach-canary")
    monkeypatch.setenv("TDB_EGRESS_CANARY_HOST", "127.0.0.1")
    monkeypatch.setenv("TDB_EGRESS_CANARY_PORT", "9")
    monkeypatch.setattr(sys, "argv", [
        "paired_egress_canary.py",
        "--image", str(source),
        "--runtime", str(runtime),
        "--host", "127.0.0.1",
        "--port", "9",
        "--work-root", str(work),
        "--out", str(out),
    ])
    old_umask = os.umask(0o077)
    try:
        assert probe.main() == 0
    finally:
        os.umask(old_umask)

    report = json.loads(out.read_text(encoding="utf-8"))
    staged = Path(observed["image"])
    assert staged != source
    assert staged == work / "runtime-image" / "canary.sif"
    assert observed["kind"] == "singularity"
    assert observed["digest"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert report["status"] == "SUCCESS"
    assert report["image_source_path"] == str(source)
    assert report["image_path"] == str(staged)
    assert report["image_staging"]["source_stat_stable"] is True
    assert report["scope"].startswith("paired canary only")
