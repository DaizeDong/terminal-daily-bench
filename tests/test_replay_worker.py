import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tomllib
from unittest import mock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import replay_worker as rw
import receipt_auth
import receipt_bundle
import submit_result as sr


TASK = "td-0123456789abcdef"
AUTH_ID = "github:alice"
HARBOR_SHA = hashlib.sha256(b"pinned harbor binary").hexdigest()
HARBOR_PACKAGE_SHA = hashlib.sha256(b"pinned Harbor package tree").hexdigest()
IMAGE_SHA = hashlib.sha256(b"pinned runtime image").hexdigest()
HARBOR_VERSION = "harbor 0.test"
HARBOR_PATH = "/controlled/bin/harbor"
HARBOR_PACKAGE_ROOT = "/controlled/harbor/src/harbor"
RUNTIME_KIND = "apptainer"
RUNTIME_PATH = "/usr/bin/apptainer"
RUNTIME_SHA = hashlib.sha256(b"pinned apptainer binary").hexdigest()
RUNTIME_VERSION = "apptainer 1.test"


def _task(root: pathlib.Path, task: str = TASK) -> pathlib.Path:
    package = root / "live" / task
    (package / "solution").mkdir(parents=True)
    (package / "tests").mkdir()
    (package / "task.toml").write_text(
        "[environment]\nallow_internet = false\n", encoding="utf-8"
    )
    (package / "solution" / "solve.sh").write_text("#!/bin/sh\nexit 0\n")
    (package / "solution" / "oracle.patch").write_text(
        "diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n"
    )
    (package / "tests" / "test.sh").write_text("#!/bin/sh\nexit 0\n")
    (package / "tests" / "test_outputs.py").write_text("def test_x(): assert True\n")
    return package


def _submission(task: str = TASK, patch: str | None = None) -> dict:
    return {
        "date": "2026-08-05",
        "submitter": "alice",
        "model": "model-a",
        "model_build": "model-a@2026-08-05",
        "scaffold": "codex",
        "harness_version": "codex@1.2.3",
        "task": task,
        "patch": patch or (
            "diff --git a/src/a.py b/src/a.py\n"
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-a\n+b\n"
        ),
        "reward_claimed": 1.0,
    }


def _authority(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path, str]:
    private = tmp_path / "receipt-ed25519.pem"
    if not private.exists():
        key = Ed25519PrivateKey.generate()
        private.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        os.chmod(private, 0o600)
    public_pem = receipt_auth.public_key_pem_from_private(private)
    key_id = "test-authority-2026"
    keys = tmp_path / "trusted-keys.json"
    if not keys.exists():
        keys.write_text(json.dumps({
            "schema": receipt_auth.KEYS_SCHEMA,
            "keys": [{
                "key_id": key_id,
                "algorithm": "ed25519",
                "public_key_pem": public_pem,
                "public_key_sha256": receipt_auth.public_key_sha256(public_pem),
            }],
        }))
        os.chmod(keys, 0o444)
    return private, keys, key_id


def _policy(tmp_path: pathlib.Path, tasks: tuple[str, ...] = (TASK,)) -> pathlib.Path:
    _, keys_path, key_id = _authority(tmp_path)
    authority = receipt_auth.load_trusted_keys(keys_path)[key_id]
    path = tmp_path / "execution-policy.json"
    path.write_text(json.dumps({
        "schema": rw.POLICY_SCHEMA,
        "runner_sha256": rw._runner_code_sha256(),
        "harbor_binary_path": HARBOR_PATH,
        "harbor_binary_sha256": HARBOR_SHA,
        "harbor_version": HARBOR_VERSION,
        "harbor_package_root": HARBOR_PACKAGE_ROOT,
        "harbor_package_sha256": HARBOR_PACKAGE_SHA,
        "backend": "singularity",
        "container_runtime_kind": RUNTIME_KIND,
        "container_runtime_path": RUNTIME_PATH,
        "container_runtime_binary_sha256": RUNTIME_SHA,
        "container_runtime_version": RUNTIME_VERSION,
        "network_policy": "no-network",
        "canary_required": True,
        "receipt_key_id": key_id,
        "receipt_public_key_sha256": authority["public_key_sha256"],
        "task_images": {task: IMAGE_SHA for task in tasks},
    }))
    return path


def _manifest(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    trusted = tmp_path / "trusted"
    _task(trusted)
    membership = tmp_path / "suite.json"
    membership.write_text(json.dumps([{"task": TASK, "mode": "live"}]))
    manifest = tmp_path / "frozen.json"
    rw.freeze_manifest(
        date="2026-08-05", membership=membership,
        trusted_root=trusted, execution_policy=_policy(tmp_path),
        trusted_keys=tmp_path / "trusted-keys.json", out=manifest,
    )
    return trusted, manifest


def _fake_runner(*, entry, patch, trusted_task, work_root, timeout_sec,
                 execution_policy, expected_task_sha256,
                 expected_image_sha256):
    assert entry["task"] == TASK
    assert "src/a.py" in patch
    assert trusted_task.is_dir()
    assert timeout_sec > 0
    assert expected_task_sha256 == rw.hash_tree(trusted_task)
    assert expected_image_sha256 == IMAGE_SHA
    runtime_control = {
        "worker_euid": os.geteuid(),
        "binary_uid": os.geteuid() + 1,
        "binary_mode": 0o755,
        "parent_uid": os.geteuid() + 2,
        "parent_mode": 0o755,
        "worker_writable": False,
        "path_resolution": "absolute-no-path-no-symlink",
    }
    runtime = {
        "container_runtime_kind": execution_policy["container_runtime_kind"],
        "container_runtime_path": execution_policy["container_runtime_path"],
        "container_runtime_binary_sha256": execution_policy[
            "container_runtime_binary_sha256"
        ],
        "container_runtime_version": execution_policy["container_runtime_version"],
        "container_runtime_control": runtime_control,
    }
    harbor_control = {
        "worker_euid": os.geteuid(),
        "worker_writable": False,
        "worker_owned_entries": 0,
        "symlinks": 0,
        "regular_files_checked": 12,
        "directories_checked": 6,
        "path_resolution": "absolute-no-path-no-symlink",
        "python_resolution": "pathfinder-without-import",
    }
    return {
        "reward": 0.0,
        "result_sha256": hashlib.sha256(b"result").hexdigest(),
        "runner_sha256": rw._runner_code_sha256(),
        "harbor_binary_path": HARBOR_PATH,
        "harbor_binary_sha256": HARBOR_SHA,
        "harbor_version": HARBOR_VERSION,
        "harbor_package_root": HARBOR_PACKAGE_ROOT,
        "harbor_package_sha256": HARBOR_PACKAGE_SHA,
        "harbor_runtime_control": harbor_control,
        "image_sha256": IMAGE_SHA,
        "backend": "singularity",
        **runtime,
        "started_at": "2026-08-05T00:00:00+00:00",
        "finished_at": "2026-08-05T00:00:01+00:00",
        "network_isolation": {
            "requested": True,
            "enforced": True,
            "task_policy": "network_mode=no-network",
            "credentials_forwarded": False,
            "egress_canary": {
                "control_reachable": True,
                "isolated_blocked": True,
                "target_sha256": hashlib.sha256(b"canary-target").hexdigest(),
                "image_sha256": IMAGE_SHA,
                "evidence_sha256": hashlib.sha256(b"canary-evidence").hexdigest(),
                **runtime,
            },
        },
    }


def _run_queue(tmp_path: pathlib.Path, *, store: pathlib.Path,
               manifest: pathlib.Path, trusted: pathlib.Path,
               runner=_fake_runner):
    private, keys, key_id = _authority(tmp_path)
    return rw.run_queue(
        store=store, manifest=manifest, trusted_root=trusted,
        work_root=tmp_path / "work", runner=runner,
        signing_key=private, key_id=key_id, trusted_keys=keys,
    )


def _promote_ready(*, store: pathlib.Path, manifest: pathlib.Path,
                   sub_id: str, trusted_keys: pathlib.Path):
    """Exercise the promoter phase under a fixture UID distinct from the signer."""
    staged = sr.get_entry(str(store), sub_id)
    assert staged is not None
    receipt_path = (
        store / "receipts" / sub_id / f"{staged['receipt_sha256']}.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    signer_uid = receipt["authority_runtime"]["worker_euid"]
    with mock.patch.object(sr.os, "geteuid", return_value=signer_uid + 10_000):
        return sr.promote_ready_receipt(
            str(store), sub_id, manifest_path=manifest,
            trusted_keys=trusted_keys,
        )


def _portable_ready_bundle(tmp_path: pathlib.Path):
    trusted, manifest = _manifest(tmp_path)
    store = tmp_path / "store"
    entry = sr.record(_submission(), str(store), authenticated_submitter=AUTH_ID)
    results = _run_queue(
        tmp_path, store=store, manifest=manifest, trusted=trusted,
    )
    assert results[0]["status"] == "receipt_ready"
    out = tmp_path / "portable-receipt"
    exported = receipt_bundle.export_bundle(
        store=store, submission_id=entry["id"], manifest_path=manifest,
        trusted_keys=tmp_path / "trusted-keys.json", out=out,
    )
    return store, entry, manifest, tmp_path / "trusted-keys.json", out, exported


def _rewrite_portable_snapshot(
    bundle_root: pathlib.Path, *, entry_update: dict,
    bundle_update: dict | None = None,
) -> str:
    """Rewrite attacker-controlled bundle bytes while keeping public digests valid."""
    bundle_root.chmod(0o755)
    snapshot_path = bundle_root / "submission.json"
    snapshot_path.chmod(0o644)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["entry"].update(entry_update)
    snapshot_payload = receipt_bundle._canonical_json(snapshot) + b"\n"
    snapshot_path.write_bytes(snapshot_payload)
    snapshot_path.chmod(0o444)

    manifest_path = bundle_root / "bundle.json"
    manifest_path.chmod(0o644)
    bundle = json.loads(manifest_path.read_text(encoding="utf-8"))
    bundle["files"]["submission.json"] = receipt_bundle._file_record(
        snapshot_payload
    )
    if bundle_update:
        bundle.update(bundle_update)
    body = {key: value for key, value in bundle.items() if key != "bundle_sha256"}
    bundle["bundle_sha256"] = receipt_bundle._bundle_digest(body)
    manifest_path.write_bytes(receipt_bundle._canonical_json(bundle) + b"\n")
    manifest_path.chmod(0o444)
    bundle_root.chmod(0o555)
    return bundle["bundle_sha256"]


def _write_fake_runtime(path: pathlib.Path, *, version: str,
                        marker: pathlib.Path) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/usr/bin/python3\n"
        "import pathlib, sys\n"
        f"pathlib.Path({str(marker)!r}).write_text('called')\n"
        f"VERSION = {version!r}\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    print(VERSION); raise SystemExit(0)\n"
        "args = sys.argv[1:]\n"
        "if '--network' in args and args[args.index('--network') + 1] == 'none':\n"
        "    print('TDB_CANARY_BLOCKED:OSError'); raise SystemExit(23)\n"
        "print('TDB_CANARY_CONNECTED'); raise SystemExit(0)\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _runtime_policy(path: pathlib.Path, *, digest: str | None = None,
                    version: str = RUNTIME_VERSION) -> dict:
    return {
        "container_runtime_kind": path.name,
        "container_runtime_path": str(path),
        "container_runtime_binary_sha256": digest or hashlib.sha256(
            path.read_bytes()
        ).hexdigest(),
        "container_runtime_version": version,
    }


def _pretend_runtime_is_not_worker_owned(monkeypatch) -> None:
    actual_uid = os.geteuid()
    fake_worker_uid = actual_uid + 10_000 if actual_uid != 0 else 10_000
    monkeypatch.setattr(rw.os, "geteuid", lambda: fake_worker_uid)
    monkeypatch.setattr(rw.os, "access", lambda _path, _mode: False)


def _sif_task(root: pathlib.Path, image: pathlib.Path) -> pathlib.Path:
    task = root / "task"
    task.mkdir(parents=True)
    (task / "task.toml").write_text(
        "[environment]\n"
        f"docker_image = {json.dumps(str(image))}\n"
        "allow_internet = false\n",
        encoding="utf-8",
    )
    return task


def _fake_harbor_install(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    marker = tmp_path / "harbor-launcher-called"
    binary = tmp_path / "controlled-bin" / "harbor"
    binary.parent.mkdir()
    binary.write_text(
        f"#!{sys.executable}\n"
        "import pathlib\n"
        f"pathlib.Path({str(marker)!r}).write_text('called')\n"
        f"print({HARBOR_VERSION!r})\n",
        encoding="utf-8",
    )
    binary.chmod(0o755)
    package = tmp_path / "controlled-source" / "harbor"
    backend = package / "environments" / "singularity"
    backend.mkdir(parents=True)
    (package / "__init__.py").write_text("__version__ = 'test'\n", encoding="utf-8")
    (backend / "singularity.py").write_text(
        "NO_NETWORK_FLAGS = ('--net', '--network', 'none')\n", encoding="utf-8"
    )
    (backend / "server.py").write_text("TRANSPORT = 'uds'\n", encoding="utf-8")
    return binary, package, marker


def _harbor_policy(binary: pathlib.Path, package: pathlib.Path, *,
                   package_digest: str | None = None) -> dict:
    return {
        "harbor_binary_path": str(binary),
        "harbor_binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "harbor_version": HARBOR_VERSION,
        "harbor_package_root": str(package),
        "harbor_package_sha256": package_digest or rw.hash_harbor_package_tree(package),
    }


def test_record_is_idempotent_and_patch_is_out_of_line(tmp_path):
    store = tmp_path / "store"
    first = sr.record(_submission(), str(store), authenticated_submitter=AUTH_ID)
    second = sr.record(_submission(), str(store), authenticated_submitter=AUTH_ID)
    assert first["id"] == second["id"]
    lines = (store / "2026-08-05.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert "diff --git" not in lines[0]
    assert sr.load_patch(str(store), first).startswith("diff --git")


@pytest.mark.parametrize("patch", [
    "diff --git a/tests/test_x.py b/tests/test_x.py\n",
    "diff --git a/../../escape b/../../escape\n",
    "diff --git a/.git/config b/.git/config\n",
])
def test_record_rejects_test_and_path_tampering(tmp_path, patch):
    with pytest.raises(ValueError):
        sr.record(
            _submission(patch=patch), str(tmp_path / "store"),
            authenticated_submitter=AUTH_ID,
        )


def test_forged_claim_becomes_verified_zero_only_after_receipt(tmp_path):
    trusted, manifest = _manifest(tmp_path)
    store = tmp_path / "store"
    entry = sr.record(_submission(), str(store), authenticated_submitter=AUTH_ID)
    assert entry["verify_status"] == "pending"
    results = _run_queue(
        tmp_path, store=store, manifest=manifest, trusted=trusted,
    )
    assert results[0]["status"] == "receipt_ready"
    staged = sr.get_entry(str(store), entry["id"])
    assert staged["verified_reward"] is None
    assert staged["receipt_sha256"]

    waiting = sr.rebuild_leaderboard(
        str(store), str(tmp_path / "waiting.json"), manifest_path=manifest,
        trusted_keys=tmp_path / "trusted-keys.json",
    )
    assert waiting["community_verified"] == []
    assert waiting["community_pending"][0]["receipt_ready"] == 1
    assert waiting["community_pending"][0]["reason"] == (
        "signed_receipt_awaiting_separate_promoter"
    )

    # The signer process cannot silently publish its own receipt.
    with pytest.raises(ValueError, match="distinct UIDs"):
        sr.promote_ready_receipt(
            str(store), entry["id"], manifest_path=manifest,
            trusted_keys=tmp_path / "trusted-keys.json",
        )

    promoted = _promote_ready(
        store=store, manifest=manifest, sub_id=entry["id"],
        trusted_keys=tmp_path / "trusted-keys.json",
    )
    assert promoted["verified_reward"] == 0.0
    assert promoted["claim_mismatch"] is True
    assert promoted["receipt_sha256"]
    assert promoted["promoter_euid"] != promoted["signer_euid"]

    board_path = tmp_path / "leaderboard.json"
    board = sr.rebuild_leaderboard(
        str(store), str(board_path), manifest_path=manifest,
        trusted_keys=tmp_path / "trusted-keys.json",
    )
    assert board["community_verified"][0]["solved"] == 0
    assert board["community_verified"][0]["claim_mismatches"] == 1
    assert board["community_pending"] == []


def test_portable_bundle_verifies_but_never_promotes_locally(tmp_path):
    store, entry, manifest, keys, bundle_root, exported = _portable_ready_bundle(
        tmp_path
    )
    candidate = receipt_bundle.verify_bundle(
        bundle_root=bundle_root,
        expected_manifest=manifest,
        trusted_keys=keys,
        expected_bundle_sha256=exported["bundle_sha256"],
    )
    assert candidate["status"] == "receipt_validated_pending_external_attestation"
    assert candidate["eligible_for_leaderboard"] is False
    assert candidate["reward"] == 0.0
    assert candidate["verifier"] == {
        "kind": "local_diagnostic",
        "independent_authority": False,
    }
    assert candidate["deployment_gate"] == {
        "status": "blocked_external_authority_not_deployed",
        "ready": False,
        "controls": {
            name: False for name in receipt_bundle.DEPLOYMENT_CONTROLS
        },
    }
    staged = sr.get_entry(str(store), entry["id"])
    assert staged["verify_status"] == "receipt_ready"
    assert staged["verified_reward"] is None
    assert staged["promoter_euid"] is None


def test_portable_snapshot_is_minimal_and_diagnostic_text_fails_closed(tmp_path):
    store, entry, manifest, keys, bundle_root, _ = _portable_ready_bundle(tmp_path)
    snapshot = json.loads(
        (bundle_root / "submission.json").read_text(encoding="utf-8")
    )
    assert set(snapshot) == {"schema", "entry"}
    assert set(snapshot["entry"]) == receipt_bundle.SNAPSHOT_ENTRY_FIELDS
    assert set(snapshot["entry"]).isdisjoint({
        "last_error", "reward_claimed", "received_at", "lease_expires_at",
        "replay_started_at", "replay_finished_at",
    })
    assert b"provider-runtime-secret" not in (bundle_root / "submission.json").read_bytes()

    queue = next(store.glob("*.jsonl"))
    row = json.loads(queue.read_text(encoding="utf-8"))
    row["last_error"] = "provider-runtime-secret"
    queue.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(
        receipt_bundle.ReceiptBundleError,
        match="non-canonical diagnostic/promotion state",
    ):
        receipt_bundle.export_bundle(
            store=store, submission_id=entry["id"], manifest_path=manifest,
            trusted_keys=keys, out=tmp_path / "must-not-export",
        )
    assert not (tmp_path / "must-not-export").exists()


def test_portable_export_rejects_staged_signer_metadata_drift(tmp_path):
    store, entry, manifest, keys, _, _ = _portable_ready_bundle(tmp_path)
    queue = next(store.glob("*.jsonl"))
    row = json.loads(queue.read_text(encoding="utf-8"))
    row["signer_euid"] += 1
    queue.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(receipt_bundle.ReceiptBundleError, match="signed receipt authority"):
        receipt_bundle.export_bundle(
            store=store, submission_id=entry["id"], manifest_path=manifest,
            trusted_keys=keys, out=tmp_path / "must-not-export-drift",
        )
    assert not (tmp_path / "must-not-export-drift").exists()


@pytest.mark.parametrize(
    ("field", "bundle_field", "suffix"),
    [
        ("id", "submission_id", "escaped-id"),
        ("date", None, "escaped-date"),
        ("patch_sha256", None, "escaped-patch"),
        ("receipt_sha256", "receipt_sha256", "escaped-receipt"),
    ],
)
def test_portable_snapshot_rejects_path_fields_before_materialization(
    tmp_path, field, bundle_field, suffix,
):
    _, _, manifest, keys, bundle_root, _ = _portable_ready_bundle(tmp_path)
    escaped = tmp_path / suffix
    value = str(escaped)
    bundle_update = {bundle_field: value} if bundle_field else None
    digest = _rewrite_portable_snapshot(
        bundle_root, entry_update={field: value}, bundle_update=bundle_update,
    )

    with pytest.raises(
        receipt_bundle.ReceiptBundleError,
        match="(?:snapshot|receipt bundle).*invalid",
    ):
        receipt_bundle.verify_bundle(
            bundle_root=bundle_root,
            expected_manifest=manifest,
            trusted_keys=keys,
            expected_bundle_sha256=digest,
        )
    assert not escaped.exists()
    assert not escaped.with_suffix(".diff").exists()
    assert not escaped.with_suffix(".json").exists()
    assert not pathlib.Path(f"{escaped}.jsonl").exists()


@pytest.mark.parametrize(
    ("bundle_update", "message"),
    [
        ({"reward": True}, "reward"),
        ({"reward": 1}, "reward"),
        ({"created_at": "2026-08-06T00:00:00Z"}, "creation time"),
        ({"attempt_id": 1}, "attempt id"),
        ({"receipt_key_id": True}, "receipt key id"),
    ],
)
def test_portable_bundle_rejects_summary_type_confusion_even_with_valid_digest(
    tmp_path, bundle_update, message,
):
    _, _, manifest, keys, bundle_root, _ = _portable_ready_bundle(tmp_path)
    digest = _rewrite_portable_snapshot(
        bundle_root, entry_update={}, bundle_update=bundle_update,
    )
    with pytest.raises(receipt_bundle.ReceiptBundleError, match=message):
        receipt_bundle.verify_bundle(
            bundle_root=bundle_root,
            expected_manifest=manifest,
            trusted_keys=keys,
            expected_bundle_sha256=digest,
        )


def test_portable_bundle_rejects_float_payload_size_type_confusion(tmp_path):
    _, _, manifest, keys, bundle_root, _ = _portable_ready_bundle(tmp_path)
    bundle = json.loads((bundle_root / "bundle.json").read_text(encoding="utf-8"))
    records = bundle["files"]
    records["patch.diff"]["size"] = float(records["patch.diff"]["size"])
    digest = _rewrite_portable_snapshot(
        bundle_root, entry_update={}, bundle_update={"files": records},
    )
    with pytest.raises(receipt_bundle.ReceiptBundleError, match="payload digest"):
        receipt_bundle.verify_bundle(
            bundle_root=bundle_root,
            expected_manifest=manifest,
            trusted_keys=keys,
            expected_bundle_sha256=digest,
        )


@pytest.mark.parametrize("target", ["patch.diff", "receipt.json", "submission.json"])
def test_portable_bundle_payload_tamper_fails_closed(tmp_path, target):
    _, _, manifest, keys, bundle_root, exported = _portable_ready_bundle(tmp_path)
    path = bundle_root / target
    path.chmod(0o644)
    path.write_bytes(path.read_bytes() + b"\n")
    path.chmod(0o444)
    with pytest.raises(receipt_bundle.ReceiptBundleError, match="payload digest mismatch"):
        receipt_bundle.verify_bundle(
            bundle_root=bundle_root,
            expected_manifest=manifest,
            trusted_keys=keys,
            expected_bundle_sha256=exported["bundle_sha256"],
        )


def test_portable_bundle_rejects_extra_file_and_symlink(tmp_path):
    _, _, manifest, keys, bundle_root, exported = _portable_ready_bundle(tmp_path)
    bundle_root.chmod(0o755)
    (bundle_root / "unreviewed.txt").write_text("not allowed", encoding="utf-8")
    with pytest.raises(receipt_bundle.ReceiptBundleError, match="file set mismatch"):
        receipt_bundle.verify_bundle(
            bundle_root=bundle_root,
            expected_manifest=manifest,
            trusted_keys=keys,
            expected_bundle_sha256=exported["bundle_sha256"],
        )
    (bundle_root / "unreviewed.txt").unlink()
    receipt = bundle_root / "receipt.json"
    receipt.chmod(0o644)
    receipt.unlink()
    receipt.symlink_to(bundle_root / "submission.json")
    with pytest.raises(receipt_bundle.ReceiptBundleError, match="bundle file"):
        receipt_bundle.verify_bundle(
            bundle_root=bundle_root,
            expected_manifest=manifest,
            trusted_keys=keys,
            expected_bundle_sha256=exported["bundle_sha256"],
        )


def test_portable_bundle_rejects_intermediate_directory_symlink(tmp_path):
    _, _, manifest, keys, bundle_root, exported = _portable_ready_bundle(tmp_path)
    linked_parent = tmp_path / "linked-transport"
    linked_parent.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(receipt_bundle.ReceiptBundleError, match="contains a symlink"):
        receipt_bundle.verify_bundle(
            bundle_root=linked_parent / bundle_root.name,
            expected_manifest=manifest,
            trusted_keys=keys,
            expected_bundle_sha256=exported["bundle_sha256"],
        )


def test_portable_bundle_rejects_self_supplied_suite_or_key(tmp_path):
    _, _, manifest, keys, bundle_root, exported = _portable_ready_bundle(tmp_path)
    alternate_suite = tmp_path / "alternate-suite.json"
    alternate_suite.write_bytes(manifest.read_bytes() + b" ")
    alternate_suite.chmod(0o444)
    with pytest.raises(receipt_bundle.ReceiptBundleError, match="promoter-pinned suite"):
        receipt_bundle.verify_bundle(
            bundle_root=bundle_root,
            expected_manifest=alternate_suite,
            trusted_keys=keys,
            expected_bundle_sha256=exported["bundle_sha256"],
        )

    alternate_root = tmp_path / "alternate-authority"
    alternate_root.mkdir()
    _, alternate_keys, _ = _authority(alternate_root)
    with pytest.raises(receipt_bundle.ReceiptBundleError, match="authority validation"):
        receipt_bundle.verify_bundle(
            bundle_root=bundle_root,
            expected_manifest=manifest,
            trusted_keys=alternate_keys,
            expected_bundle_sha256=exported["bundle_sha256"],
        )


def test_github_candidate_requires_exact_main_workflow_and_hosted_runner(
    tmp_path, monkeypatch,
):
    _, _, manifest, keys, bundle_root, exported = _portable_ready_bundle(tmp_path)
    repository = "DaizeDong/terminal-daily-bench"
    context = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": repository,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": "a" * 40,
        "TDB_AUTHORITY_WORKFLOW_SHA": "a" * 40,
        "GITHUB_WORKFLOW_REF": (
            f"{repository}/.github/workflows/promote-receipt.yml@refs/heads/main"
        ),
        "GITHUB_RUN_ID": "123456",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "TDB_RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_ENVIRONMENT": "github-hosted",
    }
    for name, value in context.items():
        monkeypatch.setenv(name, value)
    candidate = receipt_bundle.verify_bundle(
        bundle_root=bundle_root,
        expected_manifest=manifest,
        trusted_keys=keys,
        expected_bundle_sha256=exported["bundle_sha256"],
        expected_repository=repository,
    )
    assert candidate["eligible_for_leaderboard"] is False
    assert candidate["verifier"]["independent_authority"] is True
    assert candidate["verifier"]["source_commit"] == "a" * 40

    monkeypatch.delenv("TDB_RUNNER_ENVIRONMENT")
    with pytest.raises(receipt_bundle.ReceiptBundleError, match="GitHub-hosted"):
        receipt_bundle.verify_bundle(
            bundle_root=bundle_root,
            expected_manifest=manifest,
            trusted_keys=keys,
            expected_repository=repository,
        )

    monkeypatch.setenv("TDB_RUNNER_ENVIRONMENT", "self-hosted")
    with pytest.raises(receipt_bundle.ReceiptBundleError, match="GitHub-hosted"):
        receipt_bundle.verify_bundle(
            bundle_root=bundle_root,
            expected_manifest=manifest,
            trusted_keys=keys,
            expected_repository=repository,
        )

    monkeypatch.setenv("TDB_RUNNER_ENVIRONMENT", "github-hosted")
    monkeypatch.setenv("TDB_AUTHORITY_WORKFLOW_SHA", "b" * 40)
    with pytest.raises(receipt_bundle.ReceiptBundleError, match="workflow commit"):
        receipt_bundle.verify_bundle(
            bundle_root=bundle_root,
            expected_manifest=manifest,
            trusted_keys=keys,
            expected_repository=repository,
        )


def test_unknown_task_is_rejected_not_ranked(tmp_path):
    trusted, manifest = _manifest(tmp_path)
    store = tmp_path / "store"
    unknown = "td-fedcba9876543210"
    sr.record(
        _submission(task=unknown), str(store), authenticated_submitter=AUTH_ID,
    )
    results = _run_queue(
        tmp_path, store=store, manifest=manifest, trusted=trusted,
    )
    assert results[0]["status"] == "rejected"
    board = sr.rebuild_leaderboard(
        str(store), str(tmp_path / "board.json"), manifest_path=manifest,
        trusted_keys=tmp_path / "trusted-keys.json",
    )
    assert board["community_verified"] == []
    assert board["community_pending"][0]["rejected"] == 1


def test_task_version_drift_fails_closed(tmp_path):
    trusted, manifest = _manifest(tmp_path)
    store = tmp_path / "store"
    sr.record(_submission(), str(store), authenticated_submitter=AUTH_ID)
    (trusted / "live" / TASK / "tests" / "test_outputs.py").write_text(
        "def test_x(): assert False\n"
    )
    results = _run_queue(
        tmp_path, store=store, manifest=manifest, trusted=trusted,
    )
    assert results[0]["status"] == "error"
    assert results[0]["error"] == "trusted_task_drift"


def test_copy_toctou_is_checked_against_frozen_manifest_digest(
    tmp_path, monkeypatch,
):
    trusted_task = _task(tmp_path / "trusted")
    frozen_sha256 = rw.hash_tree(trusted_task)
    original_copytree = rw.shutil.copytree

    def mutate_between_check_and_copy(source, destination, *args, **kwargs):
        # Avoid recursively intercepting shutil.copytree's own directory copies.
        monkeypatch.setattr(rw.shutil, "copytree", original_copytree)
        (pathlib.Path(source) / "tests" / "test_outputs.py").write_text(
            "def test_x(): assert False\n", encoding="utf-8"
        )
        return original_copytree(source, destination, *args, **kwargs)

    monkeypatch.setattr(rw.shutil, "copytree", mutate_between_check_and_copy)
    with pytest.raises(
        rw.TransientReplayError, match="trusted_copy_manifest_digest_mismatch"
    ):
        rw.harbor_runner(
            entry={"id": "a" * 64},
            patch=_submission()["patch"],
            trusted_task=trusted_task,
            work_root=tmp_path / "work",
            timeout_sec=60,
            execution_policy={},
            expected_task_sha256=frozen_sha256,
            expected_image_sha256=IMAGE_SHA,
        )


def test_runtime_sif_is_copied_and_pinned_before_execution(tmp_path):
    original = b"immutable pre-execution sif bytes"
    source = tmp_path / "source.sif"
    source.write_bytes(original)
    run_task = _sif_task(tmp_path / "run", source)
    attempt = tmp_path / "attempt"
    attempt.mkdir()

    pinned, digest = rw._pin_runtime_sif(
        run_task=run_task,
        attempt=attempt,
        expected_sha256=hashlib.sha256(original).hexdigest(),
    )

    assert digest == hashlib.sha256(original).hexdigest()
    assert pinned.read_bytes() == original
    assert pinned.stat().st_mode & 0o777 == 0o400
    effective = tomllib.loads((run_task / "task.toml").read_text())
    assert effective["environment"]["docker_image"] == str(pinned)

    # Replacing the source after pinning cannot change the execution artifact.
    source.write_bytes(b"attacker replacement after the private copy")
    assert pinned.read_bytes() == original


def test_runtime_sif_rejects_symlink_source_replacement(tmp_path):
    target = tmp_path / "real.sif"
    target.write_bytes(b"real image")
    source = tmp_path / "source.sif"
    source.symlink_to(target)
    run_task = _sif_task(tmp_path / "run", source)
    attempt = tmp_path / "attempt"
    attempt.mkdir()

    with pytest.raises(
        rw.TransientReplayError, match="runtime_sif_source_unavailable"
    ):
        rw._pin_runtime_sif(
            run_task=run_task,
            attempt=attempt,
            expected_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        )


def test_runtime_sif_rejects_non_sif_and_wrong_digest(tmp_path):
    non_sif = tmp_path / "image.tar"
    non_sif.write_bytes(b"not a sif")
    non_sif_task = _sif_task(tmp_path / "non-sif-run", non_sif)
    non_sif_attempt = tmp_path / "non-sif-attempt"
    non_sif_attempt.mkdir()
    with pytest.raises(
        rw.PermanentReplayError, match="prebuilt SIF artifact"
    ):
        rw._pin_runtime_sif(
            run_task=non_sif_task,
            attempt=non_sif_attempt,
            expected_sha256=hashlib.sha256(non_sif.read_bytes()).hexdigest(),
        )

    sif = tmp_path / "image.sif"
    sif.write_bytes(b"actual sif bytes")
    wrong_digest_task = _sif_task(tmp_path / "wrong-digest-run", sif)
    wrong_digest_attempt = tmp_path / "wrong-digest-attempt"
    wrong_digest_attempt.mkdir()
    with pytest.raises(
        rw.TransientReplayError, match="runtime_sif_digest_mismatch_before_execution"
    ):
        rw._pin_runtime_sif(
            run_task=wrong_digest_task,
            attempt=wrong_digest_attempt,
            expected_sha256=hashlib.sha256(b"different bytes").hexdigest(),
        )


def test_patch_blob_tampering_fails_closed(tmp_path):
    trusted, manifest = _manifest(tmp_path)
    store = tmp_path / "store"
    entry = sr.record(_submission(), str(store), authenticated_submitter=AUTH_ID)
    blob = store / "patches" / f"{entry['patch_sha256']}.diff"
    blob.write_text("diff --git a/src/x.py b/src/x.py\n")
    results = _run_queue(
        tmp_path, store=store, manifest=manifest, trusted=trusted,
    )
    assert results[0]["status"] == "rejected"
    assert sr.get_entry(str(store), entry["id"])["verified_reward"] is None


def test_legacy_self_hashed_receipt_and_signed_body_tamper_both_fail(tmp_path):
    trusted, manifest = _manifest(tmp_path)
    store = tmp_path / "store"
    entry = sr.record(_submission(), str(store), authenticated_submitter=AUTH_ID)
    results = _run_queue(tmp_path, store=store, manifest=manifest, trusted=trusted)
    assert results[0]["status"] == "receipt_ready"
    staged = sr.get_entry(str(store), entry["id"])
    signed_path = (
        store / "receipts" / entry["id"] / f"{staged['receipt_sha256']}.json"
    )
    signed = json.loads(signed_path.read_text(encoding="utf-8"))

    # Recomputing the public self-hash cannot repair a changed signed field.
    tampered = dict(signed)
    tampered["reward"] = 1.0
    tampered.pop("receipt_sha256")
    tampered["receipt_sha256"] = receipt_auth.receipt_sha256(tampered)
    receipt_dir = store / "receipts" / entry["id"]
    (receipt_dir / f"{tampered['receipt_sha256']}.json").write_text(json.dumps(tampered))
    signer_uid = signed["authority_runtime"]["worker_euid"]
    with mock.patch.object(sr.os, "geteuid", return_value=signer_uid + 10_000):
        with pytest.raises(receipt_auth.ReceiptAuthorityError):
            sr.apply_verification(
                str(store), entry["id"], tampered,
                attempt_id=staged["attempt_id"],
                trusted_keys=tmp_path / "trusted-keys.json",
                manifest_path=manifest,
            )
    assert sr.get_entry(str(store), entry["id"])["verified_reward"] is None


def test_receipt_crypto_never_executes_path_openssl(tmp_path, monkeypatch):
    marker = tmp_path / "ambient-openssl-was-called"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_openssl = fake_bin / "openssl"
    fake_openssl.write_text(
        "#!/bin/sh\n"
        f"printf called > {str(marker)!r}\n"
        "exit 99\n",
        encoding="utf-8",
    )
    fake_openssl.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ.get("PATH", ""))

    private, keys, key_id = _authority(tmp_path)
    body = {"submission_id": "probe", "reward": 1.0}
    signature = receipt_auth.sign_body(
        body, private_key=private, key_id=key_id, trusted_keys=keys,
    )
    receipt_auth.verify_body(body, signature, trusted_keys=keys)

    assert not marker.exists()


def test_offline_rewrite_is_structured_and_overrides_only_environment(tmp_path):
    config = tmp_path / "task.toml"
    config.write_text(
        '[agent]\nnetwork_mode = "public"\n'
        '[environment]\nnetwork_mode = "public" # hostile baseline\n'
        '[verifier]\nallow_internet = true\n'
    )
    rw._force_offline(config)
    text = config.read_text()
    assert '[agent]\nnetwork_mode = "public"' in text
    assert '[environment]\nnetwork_mode = "no-network" # hostile baseline' in text
    assert '[verifier]\nallow_internet = true' in text
    # Added inside [environment], before [verifier], never as a stray top-level key.
    assert text.index("allow_internet = false") < text.index("[verifier]")


def test_runner_env_is_allowlist_not_credential_denylist(tmp_path, monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ambient")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/secret.json")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/agent.sock")
    monkeypatch.setenv("SLURM_JOB_TOKEN", "scheduler-secret")
    monkeypatch.setenv("PATH", os.environ.get("PATH", "/usr/bin:/bin"))
    env = rw._runner_env(tmp_path / "work")
    for name in (
        "AWS_ACCESS_KEY_ID", "GOOGLE_APPLICATION_CREDENTIALS",
        "SSH_AUTH_SOCK", "SLURM_JOB_TOKEN",
    ):
        assert name not in env
    assert pathlib.Path(env["HOME"]).is_dir()
    assert pathlib.Path(env["HOME"]).stat().st_mode & 0o077 == 0


def test_egress_canary_ignores_path_fake_and_uses_pinned_runtime(
    tmp_path, monkeypatch,
):
    pinned_marker = tmp_path / "pinned-runtime-called"
    path_fake_marker = tmp_path / "path-fake-called"
    pinned = _write_fake_runtime(
        tmp_path / "pinned" / RUNTIME_KIND,
        version=RUNTIME_VERSION,
        marker=pinned_marker,
    )
    _write_fake_runtime(
        tmp_path / "path-fake" / RUNTIME_KIND,
        version="attacker runtime",
        marker=path_fake_marker,
    )
    policy = _runtime_policy(pinned)
    image = tmp_path / "fixture.sif"
    image.write_bytes(b"the fake runtime never parses this fixture")
    _pretend_runtime_is_not_worker_owned(monkeypatch)
    monkeypatch.setenv("TDB_EGRESS_CANARY_HOST", "canary.invalid")
    monkeypatch.setenv("TDB_EGRESS_CANARY_PORT", "443")

    evidence = rw._run_egress_canary(
        image=image,
        image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
        env={"PATH": str(tmp_path / "path-fake")},
        execution_policy=policy,
        timeout_sec=5,
    )

    assert evidence["control_reachable"] is True
    assert evidence["isolated_blocked"] is True
    assert evidence["container_runtime_path"] == str(pinned)
    assert pinned_marker.exists()
    assert not path_fake_marker.exists()


def test_harbor_runtime_name_shims_override_ambient_path(tmp_path):
    pinned_marker = tmp_path / "pinned-runtime-called"
    ambient_marker = tmp_path / "ambient-runtime-called"
    pinned = _write_fake_runtime(
        tmp_path / "controlled" / RUNTIME_KIND,
        version=RUNTIME_VERSION,
        marker=pinned_marker,
    )
    ambient = tmp_path / "ambient"
    for name in ("singularity", "apptainer"):
        _write_fake_runtime(
            ambient / name, version="attacker runtime", marker=ambient_marker,
        )
    attempt = tmp_path / "attempt"
    attempt.mkdir()

    shim_dir = rw._install_container_runtime_shims(
        runtime_path=pinned, attempt=attempt,
    )
    effective_path = str(shim_dir) + os.pathsep + str(ambient)
    for name in ("singularity", "apptainer"):
        selected = shutil.which(name, path=effective_path)
        assert selected == str(shim_dir / name)
        assert pathlib.Path(selected).resolve(strict=True) == pinned
        completed = subprocess.run(
            [selected, "--version"], check=True, text=True,
            stdout=subprocess.PIPE,
        )
        assert completed.stdout.strip() == RUNTIME_VERSION

    assert pinned_marker.exists()
    assert not ambient_marker.exists()


def test_harbor_package_digest_drift_fails_before_launcher_executes(tmp_path):
    binary, package, marker = _fake_harbor_install(tmp_path)
    frozen_digest = rw.hash_harbor_package_tree(package)
    (package / "environments" / "singularity" / "singularity.py").write_text(
        "NO_NETWORK_FLAGS = ()  # attacker removed the egress cut\n",
        encoding="utf-8",
    )

    with pytest.raises(rw.TransientReplayError, match="harbor_package_digest_mismatch"):
        rw._harbor_runtime_facts(
            _harbor_policy(binary, package, package_digest=frozen_digest),
            env={"PATH": "/usr/bin:/bin"},
        )

    assert not marker.exists()


def test_harbor_runtime_binds_launcher_package_and_nonimporting_resolution(
    tmp_path, monkeypatch,
):
    binary, package, marker = _fake_harbor_install(tmp_path)
    control = {
        "worker_euid": os.geteuid(),
        "worker_writable": False,
        "worker_owned_entries": 0,
        "symlinks": 0,
        "regular_files_checked": 4,
        "directories_checked": 4,
        "path_resolution": "absolute-no-path-no-symlink",
        "python_resolution": "pathfinder-without-import",
    }
    monkeypatch.setattr(
        rw, "_harbor_immutable_control_facts", lambda **_kwargs: control,
    )
    monkeypatch.setattr(
        rw, "_resolved_harbor_package_root", lambda _env: package,
    )

    facts = rw._harbor_runtime_facts(
        _harbor_policy(binary, package), env={"PATH": "/usr/bin:/bin"},
    )

    assert facts["harbor_binary_path"] == str(binary)
    assert facts["harbor_package_root"] == str(package)
    assert facts["harbor_package_sha256"] == rw.hash_harbor_package_tree(package)
    assert facts["harbor_runtime_control"] == control
    assert marker.exists()


def test_worker_owned_fake_container_runtime_is_rejected(tmp_path):
    runtime = _write_fake_runtime(
        tmp_path / "worker-owned" / RUNTIME_KIND,
        version=RUNTIME_VERSION,
        marker=tmp_path / "worker-owned-called",
    )
    with pytest.raises(
        rw.TransientReplayError, match="container_runtime_owned_by_worker"
    ):
        rw._pinned_container_runtime_facts(
            _runtime_policy(runtime), env={"PATH": "/usr/bin:/bin"}
        )


def test_container_runtime_digest_drift_is_rejected(
    tmp_path, monkeypatch,
):
    runtime = _write_fake_runtime(
        tmp_path / "digest-drift" / RUNTIME_KIND,
        version=RUNTIME_VERSION,
        marker=tmp_path / "digest-drift-called",
    )
    _pretend_runtime_is_not_worker_owned(monkeypatch)
    with pytest.raises(
        rw.TransientReplayError, match="container_runtime_binary_digest_mismatch"
    ):
        rw._pinned_container_runtime_facts(
            _runtime_policy(
                runtime, digest=hashlib.sha256(b"different runtime").hexdigest()
            ),
            env={"PATH": "/usr/bin:/bin"},
        )


def test_container_runtime_version_drift_is_rejected(
    tmp_path, monkeypatch,
):
    runtime = _write_fake_runtime(
        tmp_path / "version-drift" / RUNTIME_KIND,
        version="apptainer actual-version",
        marker=tmp_path / "version-drift-called",
    )
    _pretend_runtime_is_not_worker_owned(monkeypatch)
    with pytest.raises(
        rw.TransientReplayError, match="container_runtime_version_mismatch"
    ):
        rw._pinned_container_runtime_facts(
            _runtime_policy(runtime, version="apptainer pinned-version"),
            env={"PATH": "/usr/bin:/bin"},
        )


def test_worker_rejects_private_key_inside_submission_store(tmp_path):
    trusted, manifest = _manifest(tmp_path)
    private, keys, _ = _authority(tmp_path)
    store = tmp_path / "store"
    store.mkdir()
    co_located = store / "receipt-key.pem"
    shutil.copyfile(private, co_located)
    os.chmod(co_located, 0o600)
    with pytest.raises(rw.PermanentReplayError, match="signing_key_inside_submission_store"):
        rw._authority_runtime_facts(
            signing_key=co_located, store=store, work_root=tmp_path / "work",
            trusted_root=trusted, manifest=manifest, trusted_keys=keys,
        )


def test_missing_enforcement_or_canary_never_promotes(tmp_path):
    trusted, manifest = _manifest(tmp_path)
    store = tmp_path / "store"
    entry = sr.record(_submission(), str(store), authenticated_submitter=AUTH_ID)

    def unsafe_runner(**kwargs):
        result = _fake_runner(**kwargs)
        result["network_isolation"] = {
            "requested": True,
            "credentials_forwarded": False,
        }
        return result

    result = _run_queue(
        tmp_path, store=store, manifest=manifest, trusted=trusted,
        runner=unsafe_runner,
    )[0]
    assert result["status"] == "error"
    assert sr.get_entry(str(store), entry["id"])["verified_reward"] is None


def test_caller_supplied_alternate_public_key_is_not_authority(tmp_path):
    trusted, manifest = _manifest(tmp_path)
    store = tmp_path / "store"
    entry = sr.record(_submission(), str(store), authenticated_submitter=AUTH_ID)
    alternate = tmp_path / "alternate-authority"
    alternate.mkdir()
    private, keys, key_id = _authority(alternate)
    result = rw.run_queue(
        store=store, manifest=manifest, trusted_root=trusted,
        work_root=tmp_path / "work", runner=_fake_runner,
        signing_key=private, key_id=key_id, trusted_keys=keys,
    )[0]
    assert result["status"] == "rejected"
    assert result["error"] == "worker_public_key_not_pinned_by_manifest"
    assert sr.get_entry(str(store), entry["id"])["verified_reward"] is None


def test_claim_is_cas_and_expired_lease_is_recovered(tmp_path):
    store = tmp_path / "store"
    entry = sr.record(_submission(), str(store), authenticated_submitter=AUTH_ID)
    claimed = sr.claim_for_replay(str(store), entry["id"], lease_seconds=60)
    with pytest.raises(ValueError):
        sr.claim_for_replay(str(store), entry["id"], lease_seconds=60)
    future = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    future += __import__("datetime").timedelta(minutes=2)
    assert sr.recover_expired_leases(str(store), now=future) == 1
    recovered = sr.get_entry(str(store), entry["id"])
    assert recovered["verify_status"] == "pending"
    assert recovered["attempt_id"] is None
    with pytest.raises(ValueError):
        sr.mark_replay_failure(
            str(store), entry["id"], rejected=False, code="stale_worker",
            attempt_id=claimed["attempt_id"],
        )


def test_one_attempt_per_authenticated_cell_and_complete_roster_required(tmp_path):
    store = tmp_path / "store"
    first = sr.record(_submission(), str(store), authenticated_submitter=AUTH_ID)
    second_patch = _submission(patch=(
        "diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n"
        "@@ -1 +1 @@\n-a\n+c\n"
    ))
    with pytest.raises(ValueError, match="already exists"):
        sr.record(second_patch, str(store), authenticated_submitter=AUTH_ID)
    board = sr.rebuild_leaderboard(str(store), str(tmp_path / "board.json"))
    assert board["community_verified"] == []
    assert board["community_pending"][0]["reason"] == "missing_pinned_roster"
    assert board["community_suite"]["official_results_included"] is False
    assert first["verified_reward"] is None


def test_verified_queue_metadata_tamper_is_not_ranked(tmp_path):
    trusted, manifest = _manifest(tmp_path)
    store = tmp_path / "store"
    sr.record(_submission(), str(store), authenticated_submitter=AUTH_ID)
    assert _run_queue(
        tmp_path, store=store, manifest=manifest, trusted=trusted,
    )[0]["status"] == "receipt_ready"
    staged = next(sr.iter_entries(str(store)))
    _promote_ready(
        store=store, manifest=manifest, sub_id=staged["id"],
        trusted_keys=tmp_path / "trusted-keys.json",
    )
    queue = store / "2026-08-05.jsonl"
    entry = json.loads(queue.read_text())
    entry["model"] = "attacker-renamed-model"
    queue.write_text(json.dumps(entry) + "\n")
    board = sr.rebuild_leaderboard(
        str(store), str(tmp_path / "tampered-board.json"),
        manifest_path=manifest, trusted_keys=tmp_path / "trusted-keys.json",
    )
    assert board["community_verified"] == []
    assert board["community_pending"][0]["reason"] == (
        "replay_incomplete_or_authority_mismatch"
    )


def test_partial_frozen_roster_cannot_get_perfect_one_of_one_score(tmp_path):
    second_task = "td-fedcba9876543210"
    trusted = tmp_path / "trusted"
    _task(trusted, TASK)
    _task(trusted, second_task)
    membership = tmp_path / "suite-two.json"
    membership.write_text(json.dumps([
        {"task": TASK, "mode": "live"},
        {"task": second_task, "mode": "live"},
    ]))
    manifest = tmp_path / "frozen-two.json"
    _, keys, _ = _authority(tmp_path)
    rw.freeze_manifest(
        date="2026-08-05", membership=membership, trusted_root=trusted,
        execution_policy=_policy(tmp_path, (TASK, second_task)),
        trusted_keys=keys, out=manifest,
    )
    store = tmp_path / "store"
    sr.record(_submission(), str(store), authenticated_submitter=AUTH_ID)
    assert _run_queue(
        tmp_path, store=store, manifest=manifest, trusted=trusted,
    )[0]["status"] == "receipt_ready"
    staged = next(sr.iter_entries(str(store)))
    _promote_ready(
        store=store, manifest=manifest, sub_id=staged["id"],
        trusted_keys=keys,
    )
    board = sr.rebuild_leaderboard(
        str(store), str(tmp_path / "partial-board.json"),
        manifest_path=manifest, trusted_keys=keys,
    )
    assert board["community_verified"] == []
    pending = board["community_pending"][0]
    assert pending["reason"] == "incomplete_roster"
    assert pending["coverage"] == 0.5
    assert pending["missing_tasks"] == [second_task]
