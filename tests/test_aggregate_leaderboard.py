import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import aggregate_leaderboard as aggregate


def _write_result(root, name, integrity):
    payload = {
        "model": name,
        "task": "td-0123456789abcdef",
        "reward": 1.0,
        "solved": True,
    }
    if integrity is not ...:
        payload["false_accept_check"] = integrity
    (root / f"{name}.json").write_text(json.dumps(payload))


def test_missing_or_legacy_integrity_never_defaults_semantic_fa_to_zero(tmp_path):
    _write_result(tmp_path, "missing", ...)
    _write_result(tmp_path, "legacy", {"false_accept": 0})

    rows = aggregate.load(str(tmp_path), "codex")

    assert len(rows) == 2
    assert all(row["fa"] is None for row in rows)
    payload = aggregate.build_payload(rows, "2026-08-05")
    assert payload["total_fa"] is None
    assert payload["total_fa_n"] == 0
    assert all(row["codex"]["fa"] is None for row in payload["leaderboard"])


def test_explicit_semantic_exploit_measurement_is_aggregated_with_denominator(tmp_path):
    _write_result(tmp_path, "caught", {"semantic_false_accept": 1})
    _write_result(tmp_path, "clean", {"semantic_false_accept": 0})
    _write_result(tmp_path, "unmeasured", {
        "scope": "protected_test_replay_integrity",
        "false_accept": 0,
        "semantic_false_accept": None,
    })

    rows = aggregate.load(str(tmp_path), "claude-code")
    payload = aggregate.build_payload(rows, "2026-08-05")

    assert payload["total_fa"] == 1
    assert payload["total_fa_n"] == 2
    by_model = {row["model"]: row["claude-code"] for row in payload["leaderboard"]}
    assert by_model["caught"]["fa"] == 1 and by_model["caught"]["fa_n"] == 1
    assert by_model["clean"]["fa"] == 0 and by_model["clean"]["fa_n"] == 1
    assert by_model["unmeasured"]["fa"] is None
    assert by_model["unmeasured"]["fa_n"] == 0
