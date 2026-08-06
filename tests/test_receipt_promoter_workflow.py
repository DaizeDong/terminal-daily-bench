import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "promote-receipt.yml"
LOCK = ROOT / ".github" / "receipt-promoter-requirements.txt"


def test_promoter_workflow_is_main_hosted_and_sha_pinned():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "github.repository == 'DaizeDong/terminal-daily-bench'" in text
    assert "github.ref == 'refs/heads/main'" in text
    assert 'test "${TDB_RUNNER_ENVIRONMENT}" = "github-hosted"' in text
    assert "TDB_RUNNER_ENVIRONMENT: ${{ runner.environment }}" in text
    assert "TDB_AUTHORITY_WORKFLOW_SHA: ${{ github.workflow_sha }}" in text
    assert text.index("Require a GitHub-hosted runner") < text.index(
        "Checkout main-pinned authority code"
    )
    assert "runs-on: ubuntu-24.04" in text
    assert "id-token: write" in text
    assert "attestations: write" in text
    assert "pull_request" not in text
    assert "pull_request_target" not in text
    assert "actions/checkout@11d5960a326750d5838078e36cf38b85af677262" in text
    assert "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065" in text
    assert "actions/attest-build-provenance@977bb373ede98d70efdf65b84cb5f73e068dcc2a" in text
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in text
    assert "uses: actions/checkout@v" not in text
    assert "uses: actions/setup-python@v" not in text


def test_promoter_never_executes_incoming_code_and_emits_unranked_candidate():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "python authority/web/receipt_bundle.py verify" in text
    assert '--bundle "incoming/${BUNDLE_PATH}"' in text
    assert '--expected-manifest "authority/${SUITE_MANIFEST_PATH}"' in text
    assert '--trusted-keys "authority/${TRUSTED_KEYS_PATH}"' in text
    assert "working-directory: incoming" not in text
    assert "subject-path: promotion-candidate.json" in text
    assert "Confirm the candidate has no promotion authority" in text
    assert 'candidate.get("eligible_for_leaderboard") is False' in text
    assert 'candidate.get("bundle_sha256") == os.environ["EXPECTED_BUNDLE_SHA256"]' in text
    assert 'gate.get("ready") is False' in text
    assert "set(candidate) == candidate_fields" in text
    assert "set(verifier) == verifier_fields" in text
    assert "set(controls) == control_fields" in text
    assert "all(value is False for value in controls.values())" in text
    assert "object_pairs_hook=reject_duplicates" in text
    assert "parse_constant=reject_constant" in text
    assert text.index("Confirm the candidate has no promotion authority") < text.index(
        "Attest the still-unranked candidate"
    )
    assert "apply_verification" not in text
    assert "promote_ready_receipt" not in text


def test_promoter_python_dependencies_are_hash_locked():
    text = LOCK.read_text(encoding="utf-8")
    assert "cryptography==" in text
    assert "cffi==" in text
    assert "pycparser==" in text
    assert text.count("--hash=sha256:") == 3
    assert "--require-hashes" in WORKFLOW.read_text(encoding="utf-8")


def test_receipt_bundle_cli_constructs_exactly_one_subparser_tree():
    script = ROOT / "web" / "receipt_bundle.py"
    for args, expected in (
        (["--help"], "{export,verify}"),
        (["export", "--help"], "--store"),
        (["verify", "--help"], "--expected-manifest"),
    ):
        completed = subprocess.run(
            [sys.executable, str(script), *args],
            cwd=ROOT, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert expected in completed.stdout
