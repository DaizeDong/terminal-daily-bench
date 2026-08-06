import hashlib
import json
import pathlib
import sys

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import receipt_auth
import receipt_authority as authority
import receipt_bundle


REPOSITORY = "DaizeDong/terminal-daily-bench"
SOURCE = "a" * 40
KEY_ID = "test-authority-2026"
SIGNER_EUID = 3225
CHECK_APP_ID = 4242
CHECK_APP_SLUG = "external-source-authorizer"
WRITER_APP_ID = 7654321
WRITER_APP_SLUG = "terminal-daily-ledger-writer"
RULESET_ID = 314
REVIEWER_ID = 7
CANDIDATE_ACTOR_ID = 101
IMPORTER_ACTOR_ID = 102
PUBLISHER_ACTOR_ID = 103
LEDGER_GENESIS = "0" * 40


class FakeGitHub:
    def __init__(self, *, main_sha=SOURCE, candidate_actor=CANDIDATE_ACTOR_ID,
                 importer_actor=IMPORTER_ACTOR_ID,
                 publisher_actor=PUBLISHER_ACTOR_ID,
                 importer_reviewer=REVIEWER_ID,
                 publisher_reviewer=REVIEWER_ID,
                 check_app_id=CHECK_APP_ID, writer_app_id=WRITER_APP_ID,
                 check_app_slug=CHECK_APP_SLUG,
                 writer_app_slug=WRITER_APP_SLUG,
                 environment_admin_bypass=False,
                 include_environment_admin_bypass=True,
                 source_check_status="completed",
                 source_check_conclusion="success",
                 include_source_check=True,
                 ledger_genesis=LEDGER_GENESIS, ledger_merge_base=None,
                 main_heads=None, ruleset_id=RULESET_ID):
        self.existing = set()
        self.pending_paths = set()
        self.ref = "1" * 40
        self.tree = "2" * 40
        self.blob_count = 0
        self.main_sha = main_sha
        self.candidate_actor = candidate_actor
        self.importer_actor = importer_actor
        self.publisher_actor = publisher_actor
        self.importer_reviewer = importer_reviewer
        self.publisher_reviewer = publisher_reviewer
        self.check_app_id = check_app_id
        self.writer_app_id = writer_app_id
        self.check_app_slug = check_app_slug
        self.writer_app_slug = writer_app_slug
        self.environment_admin_bypass = environment_admin_bypass
        self.include_environment_admin_bypass = include_environment_admin_bypass
        self.source_check_status = source_check_status
        self.source_check_conclusion = source_check_conclusion
        self.include_source_check = include_source_check
        self.ruleset_id = ruleset_id
        self.ledger_genesis = ledger_genesis
        self.ledger_merge_base = ledger_genesis if ledger_merge_base is None else ledger_merge_base
        self.main_heads = list(main_heads or [main_sha])
        self.main_ref_reads = 0

    def get(self, suffix, *, allow_not_found=False):
        if suffix == "branches/main/protection":
            return {
                "required_status_checks": {
                    "strict": True,
                    "contexts": ["authority-check"],
                    "checks": [{"context": "authority-check", "app_id": self.check_app_id}],
                },
                "required_pull_request_reviews": {
                    "dismiss_stale_reviews": True,
                    "require_code_owner_reviews": True,
                    "required_approving_review_count": 1,
                },
                "enforce_admins": {"enabled": True},
                "required_linear_history": {"enabled": True},
                "allow_force_pushes": {"enabled": False},
                "allow_deletions": {"enabled": False},
            }
        if suffix in {"environments/receipt-importer", "environments/receipt-publisher"}:
            name = suffix.split("/", 1)[1]
            environment = {
                "name": name,
                "protection_rules": [{
                    "type": "required_reviewers",
                    "prevent_self_review": True,
                    "reviewers": [{"type": "User", "reviewer": {"id": REVIEWER_ID}}],
                }],
                "deployment_branch_policy": {
                    "protected_branches": True,
                    "custom_branch_policies": False,
                },
            }
            if self.include_environment_admin_bypass:
                environment["can_admins_bypass"] = self.environment_admin_bypass
            return environment
        if suffix == f"commits/{SOURCE}/check-runs?filter=latest&per_page=100":
            runs = []
            if self.include_source_check:
                runs.append({
                    "name": "authority-check",
                    "head_sha": SOURCE,
                    "status": self.source_check_status,
                    "conclusion": self.source_check_conclusion,
                    "app": {"id": self.check_app_id, "slug": self.check_app_slug},
                })
            return {"total_count": len(runs), "check_runs": runs}
        if suffix == "git/ref/heads/main":
            index = min(self.main_ref_reads, len(self.main_heads) - 1)
            self.main_ref_reads += 1
            return {"object": {"type": "commit", "sha": self.main_heads[index]}}
        if suffix == "branches/receipt-authority-ledger/protection":
            return {
                "enforce_admins": {"enabled": True},
                "required_linear_history": {"enabled": True},
                "allow_force_pushes": {"enabled": False},
                "allow_deletions": {"enabled": False},
                "restrictions": {
                    "apps": [{
                        "id": self.writer_app_id, "slug": self.writer_app_slug,
                    }],
                    "users": [], "teams": [],
                },
            }
        if suffix == "rules/branches/receipt-authority-ledger?per_page=100":
            return [{
                "type": rule_type, "ruleset_id": self.ruleset_id,
                "ruleset_source_type": "Repository", "ruleset_source": REPOSITORY,
            } for rule_type in (
                "update", "deletion", "non_fast_forward", "required_linear_history",
            )]
        if suffix == "git/ref/heads/receipt-authority-ledger":
            return {"object": {"type": "commit", "sha": self.ref}}
        if suffix.startswith("compare/") and suffix.endswith(f"...{self.ref}"):
            return {
                "status": "ahead",
                "merge_base_commit": {"sha": self.ledger_merge_base},
            }
        if suffix.startswith("actions/runs/") and suffix.endswith("/approvals"):
            run_id = suffix.split("/")[2]
            if run_id == "9001":
                environment, reviewer = "receipt-importer", self.importer_reviewer
            elif run_id == "9002":
                environment, reviewer = "receipt-publisher", self.publisher_reviewer
            else:
                raise AssertionError(f"unexpected approval run {run_id}")
            return [{
                "environments": [{"name": environment}],
                "state": "approved",
                "user": {"id": reviewer, "type": "User"},
                "comment": "approved by independent test principal",
            }]
        if suffix.startswith("actions/workflows/"):
            workflow_id = int(suffix.rsplit("/", 1)[1])
            workflows = {
                17001: ".github/workflows/promote-receipt.yml",
                19001: ".github/workflows/import-receipt.yml",
                19002: ".github/workflows/publish-receipt.yml",
            }
            if workflow_id not in workflows:
                raise AssertionError(f"unexpected workflow id {workflow_id}")
            return {"id": workflow_id, "path": workflows[workflow_id], "state": "active"}
        if suffix.startswith("actions/runs/"):
            run_id = suffix.split("/")[2]
            values = {
                "7001": ("promote-receipt.yml", 17001, self.candidate_actor),
                "9001": ("import-receipt.yml", 19001, self.importer_actor),
                "9002": ("publish-receipt.yml", 19002, self.publisher_actor),
            }
            if run_id not in values:
                raise AssertionError(f"unexpected workflow run {run_id}")
            workflow, workflow_id, actor_id = values[run_id]
            return {
                "id": int(run_id), "run_attempt": 1,
                "event": "workflow_dispatch", "head_branch": "main",
                "head_sha": SOURCE, "path": f".github/workflows/{workflow}",
                "workflow_id": workflow_id,
                "status": "completed", "conclusion": "success",
                "repository": {"full_name": REPOSITORY},
                "actor": {"id": actor_id},
                "triggering_actor": {"id": actor_id},
            }
        if suffix == f"git/commits/{self.ref}":
            return {"tree": {"sha": self.tree}}
        if suffix == f"git/trees/{self.tree}?recursive=1":
            return {
                "truncated": False,
                "tree": [{"path": path, "type": "blob"} for path in sorted(self.existing)],
            }
        raise AssertionError(f"unexpected GET {suffix}")

    def post(self, suffix, payload):
        if suffix == "git/blobs":
            self.blob_count += 1
            return {"sha": f"{self.blob_count:040x}"}
        if suffix == "git/trees":
            self.pending_paths = {row["path"] for row in payload["tree"]}
            self.tree = "3" * 40
            return {"sha": self.tree}
        if suffix == "git/commits":
            assert payload["parents"] == [self.ref]
            return {"sha": "4" * 40}
        raise AssertionError(f"unexpected POST {suffix}")

    def patch(self, suffix, payload):
        assert suffix == "git/refs/heads/receipt-authority-ledger"
        assert payload == {"sha": "4" * 40, "force": False}
        self.ref = payload["sha"]
        self.existing.update(self.pending_paths)
        return {"object": {"sha": self.ref}}


def _runtime(role: str):
    workflow = "import-receipt.yml" if role == "importer" else "publish-receipt.yml"
    environment = "receipt-importer" if role == "importer" else "receipt-publisher"
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": SOURCE,
        "TDB_AUTHORITY_WORKFLOW_SHA": SOURCE,
        "GITHUB_WORKFLOW_REF": f"{REPOSITORY}/.github/workflows/{workflow}@refs/heads/main",
        "GITHUB_RUN_ID": "9001" if role == "importer" else "9002",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "TDB_RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "TDB_AUTHORITY_ENVIRONMENT": environment,
    }


def _write(path: pathlib.Path, payload: bytes, mode=0o444):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.chmod(mode)


def _fake_verifier(path: pathlib.Path, *, wrong_subject=False):
    script = f'''#!/usr/bin/env python3
import hashlib, json, pathlib, sys
if sys.argv[1:] == ["--version"]:
    print("gh version 9.9.9")
    raise SystemExit(0)
artifact = pathlib.Path(sys.argv[3])
required = {{
  "--repo": "DaizeDong/terminal-daily-bench",
  "--cert-oidc-issuer": "https://token.actions.githubusercontent.com",
  "--predicate-type": "https://slsa.dev/provenance/v1",
  "--source-ref": "refs/heads/main",
  "--source-digest": "a" * 40,
  "--signer-digest": "a" * 40,
  "--format": "json",
}}
if "--deny-self-hosted-runners" not in sys.argv:
    raise SystemExit(8)
for flag, value in required.items():
    if flag not in sys.argv or sys.argv[sys.argv.index(flag) + 1] != value:
        raise SystemExit(9)
identity = sys.argv[sys.argv.index("--cert-identity") + 1]
if identity not in {{
  "https://github.com/DaizeDong/terminal-daily-bench/.github/workflows/promote-receipt.yml@refs/heads/main",
  "https://github.com/DaizeDong/terminal-daily-bench/.github/workflows/import-receipt.yml@refs/heads/main",
}}:
    raise SystemExit(10)
if identity.endswith("promote-receipt.yml@refs/heads/main"):
    run_id = "7001"
else:
    run_id = "9001"
digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
if {wrong_subject!r}:
    digest = "f" * 64
print(json.dumps([{{
  "attestation": {{"bundle": "cryptographically-checked-by-test-double"}},
  "verificationResult": {{
    "mediaType": "application/vnd.dev.sigstore.verificationresult+json;version=0.1",
    "signature": {{"certificate": {{
      "subjectAlternativeName": identity,
      "issuer": "https://token.actions.githubusercontent.com",
      "sourceRepositoryURI": "https://github.com/DaizeDong/terminal-daily-bench",
      "sourceRepositoryRef": "refs/heads/main",
      "sourceRepositoryDigest": "a" * 40,
      "buildConfigURI": identity,
      "buildConfigDigest": "a" * 40,
      "buildSignerURI": identity,
      "buildSignerDigest": "a" * 40,
      "githubWorkflowRepository": "DaizeDong/terminal-daily-bench",
      "githubWorkflowRef": "refs/heads/main",
      "githubWorkflowSHA": "a" * 40,
      "githubWorkflowTrigger": "workflow_dispatch",
      "buildTrigger": "workflow_dispatch",
      "runnerEnvironment": "github-hosted",
      "runInvocationURI": f"https://github.com/DaizeDong/terminal-daily-bench/actions/runs/{{run_id}}/attempts/1",
    }}}},
    "verifiedIdentity": {{
      "issuer": {{"issuer": "https://token.actions.githubusercontent.com", "regexp": ""}},
      "subjectAlternativeName": {{"subjectAlternativeName": identity, "regexp": ""}},
    }},
    "verifiedTimestamps": [{{"type": "transparency-log"}}],
    "statement": {{
      "_type": "https://in-toto.io/Statement/v1",
      "predicateType": "https://slsa.dev/provenance/v1",
      "subject": [{{"name": artifact.name, "digest": {{"sha256": digest}}}}],
      "predicate": {{}}
    }}
  }}
}}], sort_keys=True))
'''.encode()
    _write(path, script, 0o555)


def _authority_tree(tmp_path: pathlib.Path, *, wrong_subject=False):
    root = tmp_path / "authority"
    workflows = {
        "candidate": ".github/workflows/promote-receipt.yml",
        "importer": ".github/workflows/import-receipt.yml",
        "publisher": ".github/workflows/publish-receipt.yml",
    }
    workflow_rows = []
    for role, relative in workflows.items():
        payload = f"name: {role}\n".encode()
        _write(root / relative, payload)
        workflow_rows.append({
            "role": role, "path": relative,
            "sha256": hashlib.sha256(payload).hexdigest(), "active": True,
        })

    suite = b'{"schema":"test-frozen-suite"}\n'
    suite_sha = hashlib.sha256(suite).hexdigest()
    suite_path = ".github/replay-suites/test.json"
    _write(root / suite_path, suite)

    private = Ed25519PrivateKey.generate()
    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    public_sha = receipt_auth.public_key_sha256(public_pem)
    keys_path = ".github/receipt-authorities/test.json"
    _write(root / keys_path, json.dumps({
        "schema": receipt_auth.KEYS_SCHEMA,
        "keys": [{
            "key_id": KEY_ID,
            "algorithm": "ed25519",
            "public_key_pem": public_pem,
            "public_key_sha256": public_sha,
        }],
    }, sort_keys=True).encode() + b"\n")

    verifier = tmp_path / "pinned-gh"
    _fake_verifier(verifier, wrong_subject=wrong_subject)
    verifier_sha = hashlib.sha256(verifier.read_bytes()).hexdigest()
    registry = {
        "schema": authority.REGISTRY_SCHEMA,
        "active": True,
        "deployment_status": {
            "state": "active", "observed_at": "2026-08-06T00:00:00+00:00",
            "blockers": [],
        },
        "repository": REPOSITORY,
        "main_ref": "refs/heads/main",
        "candidate_workflow": workflows["candidate"],
        "importer_workflow": workflows["importer"],
        "publisher_workflow": workflows["publisher"],
        "importer_environment": "receipt-importer",
        "publisher_environment": "receipt-publisher",
        "attestation_verifier": {
            "path": str(verifier), "sha256": verifier_sha, "version": "gh version 9.9.9",
        },
        "workflow_files": workflow_rows,
        "branch_protection": {
            "branch": "main",
            "strict_status_checks": True,
            "required_status_checks": [{
                "context": "authority-check", "app_id": CHECK_APP_ID,
            }],
            "enforce_admins": True,
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": True,
            "minimum_approvals": 1,
            "require_linear_history": True,
            "block_force_pushes": True,
            "block_deletions": True,
        },
        "environments": [
            {
                "role": "importer", "name": "receipt-importer",
                "minimum_reviewers": 1, "minimum_approvals": 1,
                "reviewer_ids": [REVIEWER_ID], "prevent_self_review": True,
                "protected_branches_only": True,
            },
            {
                "role": "publisher", "name": "receipt-publisher",
                "minimum_reviewers": 1, "minimum_approvals": 1,
                "reviewer_ids": [REVIEWER_ID], "prevent_self_review": True,
                "protected_branches_only": True,
            },
        ],
        "signers": [{
            "signer_euid": SIGNER_EUID, "key_id": KEY_ID,
            "public_key_sha256": public_sha, "active": True,
        }],
        "suites": [{
            "suite_sha256": suite_sha, "manifest_path": suite_path, "active": True,
        }],
        "receipt_keys": [{
            "key_id": KEY_ID, "public_key_sha256": public_sha,
            "registry_path": keys_path, "active": True,
        }],
        "publisher_ledger": {
            "active": True, "branch": "receipt-authority-ledger",
            "path_prefix": ".github/receipt-authority/ledger",
            "genesis_commit": LEDGER_GENESIS,
            "trusted_writer_app_id": WRITER_APP_ID,
            "trusted_writer_app_slug": WRITER_APP_SLUG,
            "ruleset_id": RULESET_ID,
            "enforce_admins": True, "require_linear_history": True,
            "block_force_pushes": True, "block_deletions": True,
        },
        "deployment_declarations": {name: True for name in authority.CONTROLS},
    }
    registry_path = root / ".github/receipt-authority/deployment.json"
    _write(registry_path, authority._canonical_json(registry) + b"\n")
    return root, registry_path, suite_sha


def _candidate(path: pathlib.Path, suite_sha: str, *, reward=0.0,
               workflow_ref=None, run_id="7001", run_attempt="1"):
    candidate = {
        "schema": receipt_bundle.PROMOTION_SCHEMA,
        "status": "receipt_validated_pending_external_attestation",
        "eligible_for_leaderboard": False,
        "attestation_required": "github_actions_artifact_attestation",
        "bundle_sha256": "b" * 64,
        "submission_id": "c" * 64,
        "attempt_id": "d" * 32,
        "suite_sha256": suite_sha,
        "receipt_sha256": "e" * 64,
        "receipt_key_id": KEY_ID,
        "reward": reward,
        "signer_euid": SIGNER_EUID,
        "verified_at": "2026-08-06T00:00:00+00:00",
        "verifier": {
            "kind": "github_actions_keyless_candidate",
            "repository": REPOSITORY,
            "ref": "refs/heads/main",
            "source_commit": SOURCE,
            "workflow_commit": SOURCE,
            "workflow_ref": workflow_ref or (
                f"{REPOSITORY}/.github/workflows/promote-receipt.yml@refs/heads/main"
            ),
            "run_id": run_id,
            "run_attempt": run_attempt,
            "event_name": "workflow_dispatch",
            "runner_environment": "github-hosted",
            "independent_authority": True,
        },
        "deployment_gate": {
            "status": "blocked_external_authority_not_deployed",
            "ready": False,
            "controls": {name: False for name in authority.CONTROLS},
        },
    }
    _write(path, authority._canonical_json(candidate) + b"\n")
    return candidate, hashlib.sha256(path.read_bytes()).hexdigest()


def _import(tmp_path, *, wrong_subject=False, reward=0.0, workflow_ref=None,
            api=None):
    root, registry, suite_sha = _authority_tree(tmp_path, wrong_subject=wrong_subject)
    candidate_path = tmp_path / "promotion-candidate.json"
    _, candidate_sha = _candidate(
        candidate_path, suite_sha, reward=reward, workflow_ref=workflow_ref,
    )
    out = tmp_path / "receipt-import-record.json"
    record = authority.import_candidate(
        candidate_path=candidate_path,
        registry_path=registry,
        authority_root=root,
        expected_run_id="7001",
        expected_run_attempt="1",
        expected_candidate_sha256=candidate_sha,
        out=out,
        api=api or FakeGitHub(),
        environ=_runtime("importer"),
    )
    return root, registry, out, record


def test_committed_registry_is_honestly_inactive_and_workflows_fail_closed():
    registry = authority.load_registry(
        ROOT / ".github/receipt-authority/deployment.json"
    )
    assert registry["active"] is False
    assert registry["deployment_status"]["state"] == "blocked"
    assert "independent_environment_reviewer_missing" in registry["deployment_status"]["blockers"]
    assert "independent_workflow_dispatcher_missing" in registry["deployment_status"]["blockers"]
    assert all(value is False for value in registry["deployment_declarations"].values())
    assert registry["signers"] == []
    assert registry["suites"] == []
    assert registry["receipt_keys"] == []
    assert registry["attestation_verifier"] == {
        "path": None, "sha256": None, "version": None,
    }
    assert all(item["active"] is False and item["sha256"] is None
               for item in registry["workflow_files"])
    assert registry["publisher_ledger"]["active"] is False
    assert registry["publisher_ledger"]["genesis_commit"] is None
    assert registry["publisher_ledger"]["trusted_writer_app_id"] is None
    assert registry["publisher_ledger"]["trusted_writer_app_slug"] is None
    assert registry["publisher_ledger"]["ruleset_id"] is None
    assert all(not item["reviewer_ids"] for item in registry["environments"])
    assert all(item["app_id"] is None
               for item in registry["branch_protection"]["required_status_checks"])
    blockers = set(registry["deployment_status"]["blockers"])
    assert {
        "publisher_ledger_protection_missing",
        "publisher_ledger_ruleset_missing",
        "publisher_ledger_genesis_pin_missing",
        "publisher_ledger_trusted_writer_missing",
        "publisher_ledger_external_app_custody_missing",
        "required_status_check_app_pin_missing",
        "external_source_authorization_missing",
        "external_control_reader_missing",
        "environment_admin_bypass_policy_unverified",
        "environment_reviewer_registry_empty",
        "trusted_workflow_registry_inactive",
    }.issubset(blockers)


def test_inactive_registry_blocks_before_api_or_attestation(tmp_path):
    registry = authority.load_registry(
        ROOT / ".github/receipt-authority/deployment.json"
    )
    with pytest.raises(authority.AuthorityError) as raised:
        authority._evaluate_controls(
            {}, candidate_path=tmp_path / "absent.json",
            candidate_sha256="0" * 64, authority_root=ROOT,
            registry=registry, runtime={"source_commit": SOURCE},
            api=object(),
        )
    assert raised.value.code == "deployment_inactive"


def test_import_accepts_only_exact_candidate_and_cryptographic_subject(tmp_path):
    _, _, out, record = _import(tmp_path)
    assert record["eligible_for_leaderboard"] is False
    assert record["status"] == "authority_controls_verified_pending_publisher"
    assert record["deployment_gate"]["ready"] is True
    assert all(record["deployment_gate"]["controls"].values())
    assert record["actor_separation"] == {
        "candidate_run_id": "7001", "candidate_run_attempt": "1",
        "candidate_actor_ids": [CANDIDATE_ACTOR_ID],
        "importer_run_id": "9001", "importer_run_attempt": "1",
        "importer_actor_ids": [IMPORTER_ACTOR_ID],
        "importer_reviewer_ids": [REVIEWER_ID],
    }
    assert out.read_bytes() == authority._canonical_json(record) + b"\n"


def test_import_rejects_source_commit_that_is_no_longer_live_main(tmp_path):
    api = FakeGitHub(main_sha="f" * 40)
    with pytest.raises(authority.AuthorityError) as raised:
        _import(tmp_path, api=api)
    assert raised.value.code == "stale_authority_source"
    assert api.main_ref_reads == 1


@pytest.mark.parametrize(
    "api_kwargs",
    [
        {"include_environment_admin_bypass": False},
        {"environment_admin_bypass": True},
        {"environment_admin_bypass": None},
        {"environment_admin_bypass": 0},
        {"environment_admin_bypass": "false"},
    ],
)
def test_import_rejects_missing_enabled_or_type_confused_admin_bypass_policy(
    tmp_path, api_kwargs,
):
    with pytest.raises(authority.AuthorityError) as raised:
        _import(tmp_path, api=FakeGitHub(**api_kwargs))
    assert raised.value.code == "environment_admin_bypass_enabled"


@pytest.mark.parametrize(
    "api_kwargs",
    [
        {"include_source_check": False},
        {"source_check_status": "queued", "source_check_conclusion": None},
        {"source_check_conclusion": "failure"},
        {"check_app_slug": authority.GITHUB_ACTIONS_APP_SLUG},
    ],
)
def test_current_protection_snapshot_does_not_replace_external_source_authorization(
    tmp_path, api_kwargs,
):
    with pytest.raises(authority.AuthorityError) as raised:
        _import(tmp_path, api=FakeGitHub(**api_kwargs))
    assert raised.value.code in {
        "source_authorization_missing", "source_authorization_failed",
    }


def test_import_rejects_same_named_status_check_from_wrong_app(tmp_path):
    with pytest.raises(authority.AuthorityError) as raised:
        _import(tmp_path, api=FakeGitHub(check_app_id=CHECK_APP_ID + 1))
    assert raised.value.code == "branch_protection_insufficient"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("trusted_writer_app_id", authority.GITHUB_ACTIONS_APP_ID),
        ("trusted_writer_app_slug", authority.GITHUB_ACTIONS_APP_SLUG),
    ],
)
def test_same_repository_actions_oidc_is_not_a_dedicated_ledger_writer(
    tmp_path, field, value,
):
    _, registry_path, _ = _authority_tree(tmp_path)
    payload = registry_path.read_bytes()
    registry = authority._strict_json(payload, label="test registry")
    registry["publisher_ledger"][field] = value
    hostile = authority._canonical_json(registry) + b"\n"
    with pytest.raises(authority.AuthorityError) as raised:
        authority._validate_registry(registry, hostile)
    assert raised.value.code == "invalid_registry"


def test_source_authorizer_and_ledger_writer_apps_must_be_distinct(tmp_path):
    _, registry_path, _ = _authority_tree(tmp_path)
    payload = registry_path.read_bytes()
    registry = authority._strict_json(payload, label="test registry")
    registry["publisher_ledger"]["trusted_writer_app_id"] = CHECK_APP_ID
    hostile = authority._canonical_json(registry) + b"\n"
    with pytest.raises(authority.AuthorityError) as raised:
        authority._validate_registry(registry, hostile)
    assert raised.value.code == "invalid_registry"


def test_repository_github_token_is_never_an_authority_credential(tmp_path):
    root, registry, suite_sha = _authority_tree(tmp_path)
    candidate_path = tmp_path / "candidate.json"
    _, candidate_sha = _candidate(candidate_path, suite_sha)
    runtime = _runtime("importer")
    runtime["GITHUB_TOKEN"] = "repository-wide-built-in-token"
    with pytest.raises(authority.AuthorityError) as raised:
        authority.import_candidate(
            candidate_path=candidate_path, registry_path=registry,
            authority_root=root, expected_run_id="7001", expected_run_attempt="1",
            expected_candidate_sha256=candidate_sha, out=tmp_path / "out.json",
            environ=runtime,
        )
    assert raised.value.code == "missing_github_token"


@pytest.mark.parametrize("actor_field", ["candidate_actor", "importer_actor"])
def test_import_rejects_candidate_actor_or_dispatcher_self_approval(tmp_path, actor_field):
    with pytest.raises(authority.AuthorityError) as raised:
        _import(tmp_path, api=FakeGitHub(**{actor_field: REVIEWER_ID}))
    assert raised.value.code == "same_actor_authority"


@pytest.mark.parametrize(
    ("api_kwargs", "expected_code"),
    [
        ({"ruleset_id": RULESET_ID + 1}, "publisher_ledger_ruleset_invalid"),
        ({"writer_app_id": WRITER_APP_ID + 1}, "publisher_ledger_unprotected"),
        ({"writer_app_slug": "wrong-ledger-writer"}, "publisher_ledger_unprotected"),
        ({"ledger_merge_base": "f" * 40}, "publisher_ledger_history_invalid"),
    ],
)
def test_import_rejects_untrusted_ledger_writer_or_unanchored_history(
    tmp_path, api_kwargs, expected_code,
):
    with pytest.raises(authority.AuthorityError) as raised:
        _import(tmp_path, api=FakeGitHub(**api_kwargs))
    assert raised.value.code == expected_code


def test_attestation_executes_sealed_verified_bytes_after_source_path_swap(
    tmp_path, monkeypatch,
):
    original_stable_file = authority._stable_file
    swaps = 0

    def swap_after_read(path, *, label, limit=authority.MAX_JSON_BYTES):
        nonlocal swaps
        payload = original_stable_file(path, label=label, limit=limit)
        if label == "attestation verifier":
            swaps += 1
            path.chmod(0o755)
            path.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
            path.chmod(0o555)
        return payload

    monkeypatch.setattr(authority, "_stable_file", swap_after_read)
    _, _, _, record = _import(tmp_path)
    assert swaps == 1
    assert record["status"] == "authority_controls_verified_pending_publisher"


def test_verifier_stdout_is_streamed_through_a_hard_limit():
    with pytest.raises(authority.AuthorityError) as raised:
        authority._run_bounded_stdout(
            [sys.executable, "-c", "import os; os.write(1, b'x' * 65)"],
            timeout=5, env={}, limit=64,
        )
    assert raised.value.code == "attestation_verifier_output_too_large"


@pytest.mark.parametrize("reward", [True, 0, 1, "0.0", None])
def test_import_rejects_candidate_reward_type_confusion(tmp_path, reward):
    root, registry, suite_sha = _authority_tree(tmp_path)
    candidate_path = tmp_path / "candidate.json"
    _, candidate_sha = _candidate(candidate_path, suite_sha, reward=reward)
    with pytest.raises(authority.AuthorityError, match="finite float") as raised:
        authority.import_candidate(
            candidate_path=candidate_path, registry_path=registry,
            authority_root=root, expected_run_id="7001", expected_run_attempt="1",
            expected_candidate_sha256=candidate_sha, out=tmp_path / "out.json",
            api=FakeGitHub(), environ=_runtime("importer"),
        )
    assert raised.value.code == "candidate_type_confusion"


def test_import_rejects_wrong_candidate_workflow_even_when_operator_repins(tmp_path):
    root, registry, suite_sha = _authority_tree(tmp_path)
    candidate_path = tmp_path / "candidate.json"
    _, candidate_sha = _candidate(
        candidate_path, suite_sha,
        workflow_ref=f"{REPOSITORY}/.github/workflows/evil.yml@refs/heads/main",
    )
    with pytest.raises(authority.AuthorityError) as raised:
        authority.import_candidate(
            candidate_path=candidate_path, registry_path=registry,
            authority_root=root, expected_run_id="7001", expected_run_attempt="1",
            expected_candidate_sha256=candidate_sha, out=tmp_path / "out.json",
            api=FakeGitHub(), environ=_runtime("importer"),
        )
    assert raised.value.code == "wrong_candidate_workflow"


def test_import_rejects_attestation_subject_mismatch(tmp_path):
    root, registry, suite_sha = _authority_tree(tmp_path, wrong_subject=True)
    candidate_path = tmp_path / "candidate.json"
    _, candidate_sha = _candidate(candidate_path, suite_sha)
    with pytest.raises(authority.AuthorityError) as raised:
        authority.import_candidate(
            candidate_path=candidate_path, registry_path=registry,
            authority_root=root, expected_run_id="7001", expected_run_attempt="1",
            expected_candidate_sha256=candidate_sha, out=tmp_path / "out.json",
            api=FakeGitHub(), environ=_runtime("importer"),
        )
    assert raised.value.code == "attestation_subject_mismatch"


def test_import_rejects_duplicate_json_keys_before_attestation(tmp_path):
    root, registry, suite_sha = _authority_tree(tmp_path)
    candidate_path = tmp_path / "candidate.json"
    candidate, _ = _candidate(candidate_path, suite_sha)
    payload = authority._canonical_json(candidate)
    malicious = payload[:-1] + b',"reward":0.0}\n'
    candidate_path.chmod(0o644)
    candidate_path.write_bytes(malicious)
    candidate_path.chmod(0o444)
    with pytest.raises(authority.AuthorityError) as raised:
        authority.import_candidate(
            candidate_path=candidate_path, registry_path=registry,
            authority_root=root, expected_run_id="7001", expected_run_attempt="1",
            expected_candidate_sha256=hashlib.sha256(malicious).hexdigest(),
            out=tmp_path / "out.json", api=FakeGitHub(), environ=_runtime("importer"),
        )
    assert raised.value.code == "duplicate_json_key"


def test_import_requires_operator_pinned_candidate_digest(tmp_path):
    root, registry, suite_sha = _authority_tree(tmp_path)
    candidate_path = tmp_path / "candidate.json"
    _candidate(candidate_path, suite_sha)
    with pytest.raises(authority.AuthorityError) as raised:
        authority.import_candidate(
            candidate_path=candidate_path, registry_path=registry,
            authority_root=root, expected_run_id="7001", expected_run_attempt="1",
            expected_candidate_sha256="0" * 64, out=tmp_path / "out.json",
            api=FakeGitHub(), environ=_runtime("importer"),
        )
    assert raised.value.code == "candidate_pin_mismatch"


def test_publisher_rejects_candidate_receipt_and_import_replay(tmp_path):
    root, registry, import_path, record = _import(tmp_path)
    import_sha = hashlib.sha256(import_path.read_bytes()).hexdigest()
    api = FakeGitHub()
    result = authority.publish_import(
        import_path=import_path, registry_path=registry, authority_root=root,
        expected_import_sha256=import_sha, out=tmp_path / "publication.json",
        api=api, environ=_runtime("publisher"),
    )
    assert result["eligible_for_leaderboard"] is True
    assert result["status"] == "authorized_in_authority_ledger"
    assert result["actor_separation"]["publisher_actor_ids"] == [PUBLISHER_ACTOR_ID]
    assert result["actor_separation"]["publisher_reviewer_ids"] == [REVIEWER_ID]
    assert len(api.existing) == 5
    assert any(f"/candidate/{record['candidate_sha256']}.json" in path for path in api.existing)
    assert any(f"/receipt/{record['receipt_sha256']}.json" in path for path in api.existing)
    assert any(f"/import-record/{import_sha}.json" in path for path in api.existing)

    with pytest.raises(authority.AuthorityError) as raised:
        authority.publish_import(
            import_path=import_path, registry_path=registry, authority_root=root,
            expected_import_sha256=import_sha, out=tmp_path / "publication-2.json",
            api=api, environ=_runtime("publisher"),
        )
    assert raised.value.code == "authority_replay"
    assert not (tmp_path / "publication-2.json").exists()


def test_publisher_rechecks_live_main_immediately_before_ledger_cas(tmp_path):
    root, registry, import_path, _ = _import(tmp_path)
    import_sha = hashlib.sha256(import_path.read_bytes()).hexdigest()
    api = FakeGitHub(main_heads=[SOURCE, SOURCE, SOURCE, SOURCE, "f" * 40])
    with pytest.raises(authority.AuthorityError) as raised:
        authority.publish_import(
            import_path=import_path, registry_path=registry, authority_root=root,
            expected_import_sha256=import_sha, out=tmp_path / "publication.json",
            api=api, environ=_runtime("publisher"),
        )
    assert raised.value.code == "stale_authority_source"
    assert api.main_ref_reads == 5
    assert api.ref == "1" * 40
    assert not (tmp_path / "publication.json").exists()


def test_publisher_rejects_wrong_workflow_and_never_writes(tmp_path):
    root, registry, import_path, _ = _import(tmp_path)
    import_sha = hashlib.sha256(import_path.read_bytes()).hexdigest()
    runtime = _runtime("publisher")
    runtime["GITHUB_WORKFLOW_REF"] = (
        f"{REPOSITORY}/.github/workflows/import-receipt.yml@refs/heads/main"
    )
    api = FakeGitHub()
    with pytest.raises(authority.AuthorityError) as raised:
        authority.publish_import(
            import_path=import_path, registry_path=registry, authority_root=root,
            expected_import_sha256=import_sha, out=tmp_path / "publication.json",
            api=api, environ=runtime,
        )
    assert raised.value.code == "wrong_workflow"
    assert api.existing == set()


def test_workflows_separate_read_only_import_from_protected_writer():
    importer = (ROOT / ".github/workflows/import-receipt.yml").read_text()
    publisher = (ROOT / ".github/workflows/publish-receipt.yml").read_text()
    for text in (importer, publisher):
        assert "runs-on: ubuntu-24.04" in text
        assert "${{ github.workflow_sha }}" in text
        assert "actions/checkout@11d5960a326750d5838078e36cf38b85af677262" in text
        assert "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093" in text
        assert "uses: actions/checkout@v" not in text
        assert "pull_request_target" not in text
    assert "environment: receipt-importer" in importer
    assert "actions: read" in importer
    assert "checks: read" in importer
    assert "contents: read" in importer
    assert "contents: write" not in importer
    assert "GH_TOKEN: ${{ secrets.RECEIPT_AUTHORITY_READER_TOKEN }}" in importer
    assert "GH_TOKEN: ${{ github.token }}" not in importer
    assert "permissions: {}" in importer
    assert "needs: preflight" in importer
    assert "Refuse to enter an authority environment for an inactive deployment" in importer
    assert "environment: receipt-publisher" in publisher
    assert "actions: read" in publisher
    assert "checks: read" in publisher
    assert "contents: read" in publisher
    assert "contents: write" not in publisher
    assert "GH_TOKEN: ${{ secrets.RECEIPT_LEDGER_WRITER_TOKEN }}" in publisher
    assert "GH_TOKEN: ${{ github.token }}" not in publisher
    assert "permissions: {}" in publisher
    assert "needs: preflight" in publisher
    assert publisher.index("Refuse to start a writer for an inactive deployment") < publisher.index(
        "environment: receipt-publisher"
    )
    assert 'registry.get("active") is not True' in publisher
    assert "python authority/web/receipt_authority.py publish" in publisher
    assert "--expected-import-sha256" in publisher


def test_attestation_parser_accepts_official_camel_case_and_rejects_subject_confusion():
    identity = (
        "https://github.com/DaizeDong/terminal-daily-bench/"
        ".github/workflows/promote-receipt.yml@refs/heads/main"
    )
    base = {
        "attestation": {},
        "verificationResult": {
            "mediaType": "application/vnd.dev.sigstore.verificationresult+json;version=0.1",
            "signature": {"certificate": {
                "subjectAlternativeName": identity,
                "issuer": "https://token.actions.githubusercontent.com",
                "sourceRepositoryURI": f"https://github.com/{REPOSITORY}",
                "sourceRepositoryRef": "refs/heads/main",
                "sourceRepositoryDigest": SOURCE,
                "buildConfigURI": identity,
                "buildConfigDigest": SOURCE,
                "buildSignerURI": identity,
                "buildSignerDigest": SOURCE,
                "githubWorkflowRepository": REPOSITORY,
                "githubWorkflowRef": "refs/heads/main",
                "githubWorkflowSHA": SOURCE,
                "githubWorkflowTrigger": "workflow_dispatch",
                "buildTrigger": "workflow_dispatch",
                "runnerEnvironment": "github-hosted",
                "runInvocationURI": (
                    f"https://github.com/{REPOSITORY}/actions/runs/7001/attempts/1"
                ),
            }},
            "verifiedIdentity": {
                "issuer": {"issuer": "https://token.actions.githubusercontent.com"},
                "subjectAlternativeName": {"subjectAlternativeName": identity},
            },
            "verifiedTimestamps": [{"type": "Tlog"}],
            "statement": {
                "_type": "https://in-toto.io/Statement/v1",
                "predicateType": authority.SLSA_PREDICATE,
                "subject": [{"name": "artifact.json", "digest": {"sha256": "a" * 64}}],
                "predicate": {},
            },
        },
    }
    authority._parse_attestation_result(
        authority._canonical_json([base]), artifact_sha256="a" * 64,
        repository=REPOSITORY, workflow_identity=identity,
        source_ref="refs/heads/main", source_commit=SOURCE,
        run_id="7001", run_attempt="1",
    )
    legacy = json.loads(json.dumps(base))
    legacy_statement = legacy["verificationResult"]["statement"]
    legacy_statement["type"] = legacy_statement.pop("_type")
    legacy_statement["predicate_type"] = legacy_statement.pop("predicateType")
    with pytest.raises(authority.AuthorityError) as raised:
        authority._parse_attestation_result(
            authority._canonical_json([legacy]), artifact_sha256="a" * 64,
            repository=REPOSITORY, workflow_identity=identity,
            source_ref="refs/heads/main", source_commit=SOURCE,
            run_id="7001", run_attempt="1",
        )
    assert raised.value.code == "invalid_attestation_result"
    base["verificationResult"]["statement"]["subject"].append(
        {"name": "artifact.json", "digest": {"sha256": "a" * 64}}
    )
    with pytest.raises(authority.AuthorityError) as raised:
        authority._parse_attestation_result(
            authority._canonical_json([base]), artifact_sha256="a" * 64,
            repository=REPOSITORY, workflow_identity=identity,
            source_ref="refs/heads/main", source_commit=SOURCE,
            run_id="7001", run_attempt="1",
        )
    assert raised.value.code == "ambiguous_attestation_subject"
    base["verificationResult"]["statement"]["subject"] = [
        {"name": "artifact.json", "digest": {"sha256": True}}
    ]
    with pytest.raises(authority.AuthorityError) as raised:
        authority._parse_attestation_result(
            authority._canonical_json([base]), artifact_sha256="a" * 64,
            repository=REPOSITORY, workflow_identity=identity,
            source_ref="refs/heads/main", source_commit=SOURCE,
            run_id="7001", run_attempt="1",
        )
    assert raised.value.code == "attestation_subject_mismatch"
