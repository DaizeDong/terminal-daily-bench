"""Release smoke tests: the public package is self-contained and FA=0 holds."""
import json, pathlib, shutil, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _clean_harbor_aggregate(reward=1.0, trial="task__fixture"):
    return {
        "n_total_trials": 1,
        "stats": {
            "n_completed_trials": 1,
            "n_errored_trials": 0,
            "n_running_trials": 0,
            "n_pending_trials": 0,
            "n_cancelled_trials": 0,
            "n_retries": 0,
            "evals": {
                "oracle__adhoc": {
                    "n_trials": 1,
                    "n_errors": 0,
                    "metrics": [{"mean": reward}],
                    "reward_stats": {"reward": {str(reward): [trial]}},
                    "exception_stats": {},
                }
            },
        },
    }


def test_package_imports_without_private_stack():
    import terminal_daily_bench as tdb
    from terminal_daily_bench import quality, scoring, harbor_score, cli  # noqa: F401
    from terminal_daily_bench.adapters import REGISTRY
    assert tdb.__version__
    assert set(REGISTRY) >= {"single_shot", "terminus"}


# Import prefixes that must never appear in this package. The names are already
# what they are; what this comment deliberately does NOT do is describe the
# layout, history or tooling of anything outside this repository. A public repo
# that explains a private one's internals has leaked the private one.
#
# Prefix-matching a namespace rather than each submodule is the point: a module
# added over there must not silently become importable here.
#
# BOTH generations are listed because a prefix list is a fail-OPEN guard -- drop
# a name and this test keeps passing while the thing it exists to catch walks
# straight through. Add first, and only remove a legacy prefix once nothing
# anywhere can still emit it.
_PRIVATE_IMPORT_PREFIXES = tuple(
    f"{kw} {mod}"
    for kw in ("from", "import")
    for mod in ("td_pipeline", "rcvh", "td_phase0", "terminal_daily.")
)


def test_no_private_imports_in_package():
    bad = []
    for f in (ROOT / "terminal_daily_bench").rglob("*.py"):
        for i, line in enumerate(f.read_text().splitlines(), 1):
            s = line.strip()
            if s.startswith(_PRIVATE_IMPORT_PREFIXES):
                bad.append(f"{f.name}:{i}")
    assert not bad, bad


def test_private_import_guard_actually_matches():
    """The guard above is a string-prefix test, so it fails open if a name rots.

    This proves it still fires: every prefix must reject a synthetic line. Without
    it, renaming a private package silently disarms the isolation contract and
    nothing goes red.
    """
    for prefix in _PRIVATE_IMPORT_PREFIXES:
        line = f"{prefix}foo import bar" if prefix.endswith(".") else f"{prefix} import bar"
        assert line.strip().startswith(_PRIVATE_IMPORT_PREFIXES), prefix
    assert not "from terminal_daily_bench import scoring".startswith(
        _PRIVATE_IMPORT_PREFIXES
    ), "the guard must not reject this package's own imports"


def test_false_accept_is_zero_by_contract():
    from terminal_daily_bench import scoring
    assert scoring.false_accept_check()["false_accept"] == 0
    assert scoring.false_accept_check()["model_is_judge"] is False


def test_quality_card_over_matrix():
    from terminal_daily_bench import quality as q
    m = [[1, 0, 0, 0], [0, 0, 0, 0], [1, 1, 1, 0], [1, 1, 0, 0]]
    card = q.benchmark_quality_report(m, deep=True, ci_n_boot=100)
    assert 0.0 <= card["msq"]["D"] <= 1.0
    assert "readiness" not in card  # readiness is a separate call
    assert q.benchmark_readiness(m, ci_n_boot=50)["ready"] in (True, False)


def test_release_check_script_passes():
    # strip transient bytecode created by importing the package in earlier tests --
    # the gate checks the *shippable* bundle, not this test process's __pycache__.
    for pc in ROOT.rglob("__pycache__"):
        shutil.rmtree(pc, ignore_errors=True)
    r = subprocess.run(["bash", str(ROOT / "scripts" / "release_check.sh")],
                       capture_output=True, text=True)
    assert "RELEASE CHECK: PASS" in r.stdout, r.stdout[-800:]


def test_read_harbor_reward_parses_result_json(tmp_path):
    """The extracted reward reader must WORK on a real harbor result.json
    (regression: it once called a helper that wasn't lifted from the private stack)."""
    from terminal_daily_bench import harbor_score
    d = tmp_path / "trial1"; d.mkdir()
    (d / "result.json").write_text(json.dumps(_clean_harbor_aggregate()))
    assert harbor_score.read_harbor_reward(str(tmp_path)) == 1.0
    assert harbor_score.read_harbor_reward(str(tmp_path / "empty")) is None


def test_harbor_reward_strict_aggregate_gate():
    """Only one complete, internally consistent, error-free cell is scored."""
    from terminal_daily_bench import harbor_score

    def reward_for(aggregate):
        snapshot = harbor_score.HarborResultSnapshot(
            "run/result.json", json.dumps(aggregate).encode()
        )
        return harbor_score.reward_from_harbor_result_snapshot(snapshot)

    clean = _clean_harbor_aggregate(1.0)
    assert reward_for(clean) == 1.0

    errored = _clean_harbor_aggregate(0.0)
    errored["stats"]["n_errored_trials"] = 1
    errored_eval = next(iter(errored["stats"]["evals"].values()))
    errored_eval["n_errors"] = 1
    errored_eval["exception_stats"] = {
        "NonZeroAgentExitCodeError": ["task__fixture"]
    }
    assert reward_for(errored) is None

    missing_counter = _clean_harbor_aggregate(1.0)
    del missing_counter["stats"]["n_pending_trials"]
    assert reward_for(missing_counter) is None

    inconsistent = _clean_harbor_aggregate(1.0)
    inconsistent_eval = next(iter(inconsistent["stats"]["evals"].values()))
    inconsistent_eval["reward_stats"] = {
        "reward": {"0.0": ["task__fixture"]}
    }
    assert reward_for(inconsistent) is None

    multi_trial = _clean_harbor_aggregate(1.0)
    multi_trial["n_total_trials"] = 2
    multi_trial["stats"]["n_completed_trials"] = 2
    multi_eval = next(iter(multi_trial["stats"]["evals"].values()))
    multi_eval["n_trials"] = 2
    multi_eval["reward_stats"] = {
        "reward": {"1.0": ["task__fixture", "task__second"]}
    }
    assert reward_for(multi_trial) is None


def test_harbor_reward_accepts_real_0131_aggregate_plus_bound_trial_result(tmp_path):
    """Harbor 0.13.1 writes both run/result.json and run/trial/result.json."""
    from terminal_daily_bench import harbor_score

    run = tmp_path / "2026-08-05__22-48-35"
    trial = run / "task__fixture"
    trial.mkdir(parents=True)
    (run / "result.json").write_text(json.dumps({
        "id": "job-fixture",
        "n_total_trials": 1,
        "stats": {
            "n_completed_trials": 1,
            "n_errored_trials": 0,
            "n_running_trials": 0,
            "n_pending_trials": 0,
            "n_cancelled_trials": 0,
            "n_retries": 0,
            "evals": {"codex__adhoc": {
                "n_trials": 1,
                "n_errors": 0,
                "metrics": [{"mean": 1.0}],
                "reward_stats": {"reward": {"1.0": ["task__fixture"]}},
                "exception_stats": {},
            }},
        },
    }))
    (trial / "result.json").write_text(json.dumps({
        "trial_name": "task__fixture",
        "verifier_result": {"rewards": {"reward": 1.0}},
    }))

    snapshot = harbor_score.authoritative_harbor_result_snapshot(str(tmp_path))
    assert snapshot is not None
    assert snapshot.relative_path == "2026-08-05__22-48-35/result.json"
    assert harbor_score.reward_from_harbor_result_snapshot(snapshot) == 1.0


def test_harbor_reward_rejects_non_mapping_aggregate_with_nested_trial(tmp_path):
    from terminal_daily_bench import harbor_score

    run = tmp_path / "run"
    trial = run / "task__fixture"
    trial.mkdir(parents=True)
    (run / "result.json").write_text("[]")
    (trial / "result.json").write_text("{}")

    assert harbor_score.authoritative_harbor_result_snapshot(str(tmp_path)) is None
    assert harbor_score.read_harbor_reward(str(tmp_path)) is None


def test_harbor_reward_rejects_cross_run_deep_or_unbound_nested_shadows(tmp_path):
    from terminal_daily_bench import harbor_score

    run = tmp_path / "run"
    trial = run / "task__fixture"
    trial.mkdir(parents=True)
    aggregate = _clean_harbor_aggregate()
    aggregate["stats"]["evals"] = {
        "codex__adhoc": aggregate["stats"]["evals"].pop("oracle__adhoc")
    }
    (run / "result.json").write_text(json.dumps(aggregate))
    (trial / "result.json").write_text("{}")

    deep = trial / "agent" / "result.json"
    deep.parent.mkdir()
    deep.write_text("{}")
    assert harbor_score.authoritative_harbor_result_snapshot(str(tmp_path)) is None
    deep.unlink()

    cross = tmp_path / "other-run" / "task__fixture" / "result.json"
    cross.parent.mkdir(parents=True)
    cross.write_text("{}")
    assert harbor_score.authoritative_harbor_result_snapshot(str(tmp_path)) is None
    cross.unlink()

    aggregate["stats"]["evals"]["codex__adhoc"]["reward_stats"] = {
        "reward": {"1.0": ["task__different"]}
    }
    (run / "result.json").write_text(json.dumps(aggregate))
    assert harbor_score.authoritative_harbor_result_snapshot(str(tmp_path)) is None


def test_harbor_reward_fails_closed_on_multiple_or_ambiguous_results(tmp_path):
    from terminal_daily_bench import harbor_score
    valid = _clean_harbor_aggregate(0.0)
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir(); second.mkdir()
    (first / "result.json").write_text(json.dumps(valid))
    forged = _clean_harbor_aggregate(1.0)
    forged["stats"]["evals"] = {
        "forged": forged["stats"]["evals"].pop("oracle__adhoc")
    }
    (second / "result.json").write_text(json.dumps(forged))
    assert harbor_score.read_harbor_reward(str(tmp_path)) is None

    (second / "result.json").unlink()
    (first / "result.json").write_text(json.dumps({
        "stats": {"evals": {
            "one": {"metrics": [{"mean": 0.0}]},
            "two": {"metrics": [{"mean": 1.0}]},
        }}
    }))
    assert harbor_score.read_harbor_reward(str(tmp_path)) is None


def test_harbor_reward_rejects_hardlinked_authority(tmp_path):
    import os
    from terminal_daily_bench import harbor_score

    trial = tmp_path / "trial"
    trial.mkdir()
    result = trial / "result.json"
    result.write_text(json.dumps(_clean_harbor_aggregate()))
    os.link(result, tmp_path / "attacker-alias")

    assert harbor_score.authoritative_harbor_result_snapshot(str(tmp_path)) is None
    assert harbor_score.read_harbor_reward(str(tmp_path)) is None


def test_harbor_result_open_race_fails_closed(tmp_path, monkeypatch):
    import os
    from terminal_daily_bench import harbor_score

    trial = tmp_path / "trial"
    trial.mkdir()
    result = trial / "result.json"
    result.write_text(json.dumps(_clean_harbor_aggregate(0.0)))
    replacement = trial / "replacement.json"
    forged = _clean_harbor_aggregate(1.0)
    forged["stats"]["evals"] = {
        "forged": forged["stats"]["evals"].pop("oracle__adhoc")
    }
    replacement.write_text(json.dumps(forged))
    original_open = harbor_score.os.open
    raced = False

    def replace_between_lstat_and_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal raced
        if path == "result.json" and dir_fd is not None and not raced:
            raced = True
            os.replace(replacement, result)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(harbor_score.os, "open", replace_between_lstat_and_open)
    assert harbor_score.authoritative_harbor_result_snapshot(str(tmp_path)) is None
    assert raced is True


def test_harbor_score_parses_task_toml_without_nameerror(tmp_path):
    """P0-1 regression: harbor_score used re.search without importing re, so any
    real task.toml parse raised NameError and third-party scoring never worked."""
    from terminal_daily_bench import harbor_score
    cmd = ["harbor", "run", "-p", str(tmp_path)]      # it reads the -p task dir
    (tmp_path / "task.toml").write_text("[environment]\nallow_internet = false\n")
    assert harbor_score._task_declares_run_offline(cmd) is True
    (tmp_path / "task.toml").write_text("[environment]\nallow_internet = true\n")
    assert harbor_score._task_declares_run_offline(cmd) is False


def test_harbor_network_policy_reads_environment_table_not_first_matching_key(tmp_path):
    from terminal_daily_bench import harbor_score
    cmd = ["harbor", "run", "-p", str(tmp_path), "-e", "singularity"]
    (tmp_path / "task.toml").write_text(
        "[agent]\nallow_internet = true\n"
        "[environment]\nallow_internet = false\n"
        "[verifier]\nallow_internet = true\n"
    )
    assert harbor_score._task_declares_run_offline(cmd) is True
    injected = harbor_score.maybe_inject_offline_eks(cmd)
    assert "singularity_disable_internet=true" in injected


def test_eval_finish_exits_nonzero_on_error(tmp_path):
    """P0-2 regression: a total failure used to exit 0, which is how the missing
    import shipped. An error must be visible in the exit status."""
    from terminal_daily_bench import eval as ev
    out = str(tmp_path / "r.json")
    assert ev._finish({"model": "m", "error": "boom"}, out, 0.0) == 1
    assert ev._finish({"model": "m", "reward": 0.0, "error": None}, out, 0.0) == 0


def test_release_check_is_idempotent():
    """The gate must not create the artifact it forbids: it imports harbor_score to
    prove the module stands alone, which used to write __pycache__ and fail the very
    next run. Running it twice (and after the test suite) must stay green."""
    for _ in range(2):
        r = subprocess.run(["bash", str(ROOT / "scripts" / "release_check.sh")],
                           capture_output=True, text=True)
        assert "RELEASE CHECK: PASS" in r.stdout, r.stdout[-800:]


def test_no_private_doc_paths_in_shipped_pages():
    """docs/ is the GitHub Pages root: every byte there is published. Internal report
    paths/filenames must not leak into shipped HTML (they name the private repo layout)."""
    import re
    leaks = []
    for f in (ROOT / "docs").rglob("*.html"):
        for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            if re.search(r"reports/v2-campaign|forward-plan/|MSQ_METHODS\.md"
                         r"|CERTIFIED_YIELD_PROOF\.md|UNIVERSE_EXPANSION\.md", line):
                leaks.append(f"{f.relative_to(ROOT)}:{i}")
    assert not leaks, leaks


def test_live_packages_do_not_publish_the_upstream_merge():
    """A LIVE task withholds solution/ and the protected test bodies. That premise is
    void if the package also publishes the upstream merge coordinates: our tasks come
    from PUBLIC merged GitHub PRs, so `git show <merge_sha>` returns both the withheld
    gold patch AND the withheld tests -- offline, from inside a fully network-severed
    container. `oracle_patch_sha256` is worse than a hint: it lets an attacker confirm
    byte-equality with the gold before submitting.

    ARCHIVE packages ship solution/ anyway, so they keep full provenance -- that is
    what makes an archived task reproducible.
    """
    import json as _json
    sys.path.insert(0, str(ROOT / "tasks"))
    import publish_tasks as pt

    toml = ('[metadata]\nsource_repo = "o/r"\npr_number = 1451\n'
            'base_sha = "2abeb0f"\nmerge_sha = "b782e56"\n'
            'oracle_patch_sha256 = "1e843ef"\ndocker_image = "/host/x.sif"\n')
    prov = _json.dumps({"source_repo": "o/r", "source_ref": "b782e56"})

    live_toml = pt._sanitize_task_toml(toml, live=True)
    for key in ("pr_number", "base_sha", "merge_sha", "oracle_patch_sha256"):
        assert key not in live_toml, f"{key} leaked into a LIVE task.toml"
    assert "source_repo" in live_toml, "repo identity is not the secret; the commit is"

    live_prov = _json.loads(pt._sanitize_provenance(prov, live=True))
    assert "source_ref" not in live_prov, "merge sha leaked into LIVE PROVENANCE.json"

    # ARCHIVE keeps everything (minus the host image path, which is unrelated).
    arch_toml = pt._sanitize_task_toml(toml, live=False)
    for key in ("pr_number", "merge_sha", "oracle_patch_sha256"):
        assert key in arch_toml, f"{key} must survive on an ARCHIVE task"
    assert "source_ref" in _json.loads(pt._sanitize_provenance(prov, live=False))

    # An unparseable provenance must fail CLOSED on a live task, never pass through.
    assert "b782e56" not in pt._sanitize_provenance("{not json", live=True)


def test_shipped_live_tasks_carry_no_merge_sha():
    """Regression on the actual shipped tree, not just the function: the release we
    push to GitHub Pages must contain no upstream commit pointer under tasks/live/."""
    import re
    live = ROOT / "tasks" / "live"
    if not live.is_dir():
        return
    leaks = []
    for f in list(live.rglob("task.toml")) + list(live.rglob("PROVENANCE.json")):
        for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            if re.search(r"merge_sha|source_ref|oracle_patch_sha256|pr_number", line):
                leaks.append(f"{f.relative_to(ROOT)}:{i}: {line.strip()}")
    assert not leaks, "LIVE package leaks the gold's coordinates:\n" + "\n".join(leaks)


def test_pending_submission_never_reports_a_false_accept_number():
    """`false_accept` is a property of a GATE DECISION. A pending submission has had no
    decision made about it, so writing 0 there would let the community board print
    "0 false accepts" about rows nothing ever adjudicated -- an unearned safety claim.

    Also pins the fail-closed posture: pending rows live in an unranked review view
    and can never enter the verified denominator.
    """
    import json as _json, tempfile, os
    sys.path.insert(0, str(ROOT / "web"))
    import submit_result as sr

    d = tempfile.mkdtemp()
    out = os.path.join(d, "lb.json")
    sub = {"date": "2026-07-30", "submitter": "x", "model": "m",
           "model_build": "m@build-1", "scaffold": "s",
           "harness_version": "s@1",
           "task": "td-fc90ea8b76d5f6b6", "patch": "diff --git a/a b/a\n",
           "reward_claimed": 1.0}
    entry = sr.record(sub, d, authenticated_submitter="github:x")
    assert entry["false_accept"] is None, "a pending row must not claim a measured FA"
    assert entry["verified_reward"] is None

    board = sr.rebuild_leaderboard(d, out)
    assert board["community_verified"] == []
    assert board["community_pending"][0]["pending"] == 1

    # A legacy self-hashed v1 receipt is forgeable and must never promote a row.
    # v2 additionally requires an authority signature and pinned manifest/key paths.
    claimed = sr.claim_for_replay(d, entry["id"])
    digest = "a" * 64
    receipt = {
        "schema": "terminal-daily-replay-receipt/v1",
        "submission_id": entry["id"], "date": entry["date"],
        "patch_sha256": entry["patch_sha256"],
        "task": entry["task"], "suite_sha256": digest,
        "task_sha256": digest, "verifier_sha256": digest,
        "runner_sha256": digest, "result_sha256": digest, "reward": 1.0,
        "network_isolation": {"requested": True},
    }
    receipt_sha = __import__("hashlib").sha256(sr._canonical_json(receipt)).hexdigest()
    receipt["receipt_sha256"] = receipt_sha
    receipt_dir = pathlib.Path(d) / "receipts" / entry["id"]
    receipt_dir.mkdir(parents=True)
    (receipt_dir / f"{receipt_sha}.json").write_text(_json.dumps(receipt))
    with __import__("pytest").raises(ValueError):
        sr.apply_verification(
            d, entry["id"], receipt, attempt_id=claimed["attempt_id"],
            trusted_keys=pathlib.Path(d) / "untrusted-keys.json",
            manifest_path=pathlib.Path(d) / "untrusted-manifest.json",
        )
    assert sr.get_entry(d, entry["id"])["verified_reward"] is None
    assert sr.rebuild_leaderboard(d, out)["community_verified"] == []

    with __import__("pytest").raises(RuntimeError):
        sr.apply_verified(d, entry["id"], 1.0)
