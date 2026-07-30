"""Release smoke tests: the public package is self-contained and FA=0 holds."""
import pathlib, shutil, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_package_imports_without_private_stack():
    import terminal_daily_bench as tdb
    from terminal_daily_bench import quality, scoring, harbor_score, cli  # noqa: F401
    from terminal_daily_bench.adapters import REGISTRY
    assert tdb.__version__
    assert set(REGISTRY) >= {"single_shot", "terminus"}


def test_no_private_imports_in_package():
    bad = []
    for f in (ROOT / "terminal_daily_bench").rglob("*.py"):
        for i, line in enumerate(f.read_text().splitlines(), 1):
            s = line.strip()
            if s.startswith(("from td_pipeline", "import td_pipeline",
                             "from rcvh", "import rcvh")):
                bad.append(f"{f.name}:{i}")
    assert not bad, bad


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
    import json
    from terminal_daily_bench import harbor_score
    d = tmp_path / "trial1"; d.mkdir()
    (d / "result.json").write_text(json.dumps(
        {"stats": {"evals": {"oracle__adhoc": {"metrics": [{"mean": 1.0}]}}}}))
    assert harbor_score.read_harbor_reward(str(tmp_path)) == 1.0
    assert harbor_score.read_harbor_reward(str(tmp_path / "empty")) is None


def test_harbor_score_parses_task_toml_without_nameerror(tmp_path):
    """P0-1 regression: harbor_score used re.search without importing re, so any
    real task.toml parse raised NameError and third-party scoring never worked."""
    from terminal_daily_bench import harbor_score
    cmd = ["harbor", "run", "-p", str(tmp_path)]      # it reads the -p task dir
    (tmp_path / "task.toml").write_text("[environment]\nallow_internet = false\n")
    assert harbor_score._task_declares_run_offline(cmd) is True
    (tmp_path / "task.toml").write_text("[environment]\nallow_internet = true\n")
    assert harbor_score._task_declares_run_offline(cmd) is False


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
