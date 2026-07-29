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
