"""Verify parity, repeated-attempt cost accounting and publication boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tools.make_fixtures import call_telemetry_fixture, eval_results_fixture, repeat_trials_fixture, run_details_fixture, task_run_view_fixture
from web import gen_run_details
from web.gen_run_details import DataError, board_from_eval_results, main, reconstruct_board, run_id, safe_steps, publish_details, trajectory_counts


def test_reconstructs_majority_but_preserves_failed_attempts_and_elapsed_seconds():
    fixture = run_details_fixture()
    day, details, audit = reconstruct_board(fixture["published"], fixture["board"])
    assert day["matrix"]["scaffold"] == "agent-test@high"
    assert day["matrix"]["tasks"] == ["task-alpha", "task-beta"]
    assert [r["g"] for r in day["matrix"]["rows"]] == [[1, 0], [0, 1]]
    assert day["matrix"]["rows"][0]["trials"] == [[1, 0], [1, 1], [0, 0]]
    assert details["coverage"]["matched_runs"] == 12
    assert sum(r["outcome"] for r in details["runs"]) == 6
    assert sum(r["wall_sec"] for r in details["runs"]) == 240
    assert all(r["cost_usd"] is None for r in details["runs"])
    assert all(r["input_tokens"] is None for r in details["runs"])
    assert audit["aggregate_groups_verified"] == 2
    assert day["aggregation"]["unit"] == "task"
    assert details["aggregation"]["unit"] == "attempt"
    encoded = json.dumps((day, details))
    assert "PRIVATE_" not in encoded and "/private/" not in encoded


def test_ordering_and_ids_are_stable_across_input_order():
    fixture = run_details_fixture()
    expected = reconstruct_board(fixture["published"], fixture["board"])
    fixture["board"]["results"].reverse()
    assert reconstruct_board(fixture["published"], fixture["board"]) == expected
    runs = expected[1]["runs"]
    assert len({r["id"] for r in runs}) == 12


def test_aggregate_match_is_required_and_cell_mismatch_cannot_hide_in_same_rate():
    fixture = run_details_fixture()
    altered = deepcopy(fixture["published"])
    altered["leaderboard"][0]["agent-test@high"]["solved"] = 2
    with pytest.raises(DataError, match="aggregate"):
        reconstruct_board(altered, fixture["board"])
    altered = deepcopy(fixture["published"])
    altered["matrix"] = {"scaffold": "agent-test@high", "tasks": ["task-alpha", "task-beta"],
                         "rows": [{"model": "model-a", "g": [0, 1]}]}
    with pytest.raises(DataError, match="published matrix"):
        reconstruct_board(altered, fixture["board"])


@pytest.mark.parametrize("case", ["duplicate", "missing_trial", "unobserved", "reward_disagrees", "wrong_trials"])
def test_refuses_ambiguous_or_incomplete_attempts(case):
    fixture = run_details_fixture()
    board = fixture["board"]
    if case == "duplicate":
        board["results"].append(deepcopy(board["results"][0]))
    elif case == "missing_trial":
        board["results"].pop(0)
    elif case == "unobserved":
        board["results"][0]["unobserved"] = True
    elif case == "reward_disagrees":
        board["results"][0]["reward"] = 0.0
    else:
        board["n_trials"] = 2
    with pytest.raises(DataError):
        reconstruct_board(fixture["published"], board)


def test_only_explicit_exclusions_can_remove_a_source_configuration():
    fixture = run_details_fixture()
    fixture["board"]["results"].append(fixture["excluded_row"])
    with pytest.raises(DataError, match="not published"):
        reconstruct_board(fixture["published"], fixture["board"])
    _, details, audit = reconstruct_board(fixture["published"], fixture["board"],
                                          excluded_specs=["model-a@max"])
    assert len(details["runs"]) == 12
    assert audit["excluded_specs"] == {"model-a@max": 1}


def test_zero_is_measured_missing_is_null_and_failure_cost_is_retained():
    fixture = run_details_fixture()
    fixture["board"]["results"][0]["cost_s"] = 0.0
    rid = run_id("2020-01-02", "task-alpha", "model-a", "agent-test@high", 2)
    telemetry = {rid: {"complete": True, "cost_usd": 2.5, "input_tokens": 0, "output_tokens": 5}}
    _, details, _ = reconstruct_board(fixture["published"], fixture["board"], telemetry=telemetry)
    row = next(r for r in details["runs"] if r["id"] == rid)
    assert row["outcome"] == 0 and row["cell_outcome"] == 1
    assert row["cost_usd"] == 2.5 and row["input_tokens"] == 0
    assert details["coverage"]["cost_runs"] == details["coverage"]["token_runs"] == 1
    assert details["runs"][0]["wall_sec"] == 0.0


@pytest.mark.parametrize("value", [-1, True, "2", float("nan"), float("inf")])
def test_invalid_costs_cannot_turn_into_free_or_measured_runs(value):
    fixture = run_details_fixture()
    rid = run_id("2020-01-02", "task-alpha", "model-a", "agent-test@high", 0)
    with pytest.raises(DataError):
        reconstruct_board(fixture["published"], fixture["board"],
                          telemetry={rid: {"complete": True, "cost_usd": value}})


def test_partial_or_unpublished_telemetry_is_rejected():
    fixture = run_details_fixture()
    rid = run_id("2020-01-02", "task-alpha", "model-a", "agent-test@high", 0)
    with pytest.raises(DataError, match="complete attempt"):
        reconstruct_board(fixture["published"], fixture["board"], telemetry={rid: {"input_tokens": 2}})
    with pytest.raises(DataError, match="unpublished attempt"):
        reconstruct_board(fixture["published"], fixture["board"], telemetry={"unknown": {"complete": True}})


def test_replay_contains_observed_actions_but_no_raw_text_or_inferred_success():
    fixture = run_details_fixture()
    steps = safe_steps(fixture["trajectory"])
    assert [step["title"] for step in steps] == ["Ran pytest", "Submitted a patch"]
    assert all(step["status"] == "recorded" for step in steps)
    encoded = json.dumps(steps)
    assert "PRIVATE_" not in encoded and "TOKEN_FOR_TEST" not in encoded and "/private/" not in encoded
    assert safe_steps(None) == []


def run_view_js(script, data=None):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for the shipped task viewer runtime")
    path = Path(__file__).resolve().parents[1] / "docs/assets/tdb-runs.js"
    harness = r"""
const fs = require('fs'), vm = require('vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const original = JSON.stringify(input);
const box = {window:{TDB:{}}, URL, console};
vm.createContext(box);
vm.runInContext(fs.readFileSync(SOURCE, 'utf8'), box);
const T = box.window.TDB;
""".replace("SOURCE", json.dumps(str(path)))
    result = subprocess.run([node, "-e", harness + script + "\nif(JSON.stringify(input)!==original) throw Error('Input mutated');"],
                            input=json.dumps(data or task_run_view_fixture()), capture_output=True,
                            text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_viewer_distinguishes_attempt_failure_from_successful_majority():
    result = run_view_js("console.log(JSON.stringify(T.taskRunData(input.day,input.details,input.task)));")
    assert result["available"]
    assert len(result["runs"]) == 3
    assert [row["outcome"] for row in result["runs"]] == [1, 1, 0]
    assert all(row["cell_outcome"] == 1 and row["cell_passes"] == 2 for row in result["runs"])
    assert len(result["outcomes"]) == 3


def test_viewer_keeps_legacy_matrix_outcomes_when_telemetry_was_not_published():
    result = run_view_js("console.log(JSON.stringify(T.taskRunData(input.legacy_day,null,input.task)));")
    assert result["available"] and result["runs"] == []
    assert len(result["outcomes"]) == 2
    assert all(row["outcome"] == 0 for row in result["outcomes"])


@pytest.mark.parametrize("case", ["date", "duplicate", "cost", "incomplete", "outcome"])
def test_viewer_refuses_invalid_attempt_data_but_preserves_existing_outcomes(case):
    sample = task_run_view_fixture()
    if case == "date":
        sample["details"]["date"] = "2020-01-01"
    elif case == "duplicate":
        sample["details"]["runs"].append(deepcopy(sample["details"]["runs"][0]))
    elif case == "cost":
        sample["details"]["runs"][0]["cost_usd"] = -1
    elif case == "incomplete":
        sample["details"]["runs"].pop(0)
    else:
        sample["details"]["runs"][0]["cell_outcome"] = 0
    result = run_view_js("console.log(JSON.stringify(T.taskRunData(input.day,input.details,input.task)));", sample)
    assert result["available"] is False and result["reason"] == "telemetry"
    assert result["runs"] == [] and len(result["outcomes"]) == 3


def test_viewer_pagination_opens_requested_attempt_on_its_page():
    result = run_view_js("console.log(JSON.stringify(T.taskRunPage(input.pagination_rows,{model:'model-a',run:'page-run-042'})));")
    assert result["page"] == 3 and result["pages"] == 3
    assert result["start"] == 41 and result["end"] == 45
    assert result["total"] == 45 and result["selectedRunFound"]
    assert len(result["rows"]) == 5


def test_viewer_shared_state_keeps_date_model_setting_attempt_and_project_prefix():
    from urllib.parse import parse_qs, urlsplit
    result = run_view_js("console.log(JSON.stringify(T.taskRunUrl('https://example.com/project/tasks/task-alpha/?d=2020-01-01&query=parser',{date:'2020-01-02',model:'model-a',scaffold:'single_shot@high',run:'page-run-042',page:3}).href));")
    url = urlsplit(result)
    assert url.path == "/project/tasks/task-alpha/"
    assert parse_qs(url.query) == {"date": ["2020-01-02"], "model": ["model-a"],
        "agent": ["single_shot"], "effort": ["high"], "run": ["page-run-042"],
        "run-page": ["3"], "query": ["parser"]}


def test_publishing_splits_preserve_every_attempt_and_scope_coverage_to_task(tmp_path):
    fixture = run_details_fixture()
    _, details, _ = reconstruct_board(fixture["published"], fixture["board"])
    index = publish_details(tmp_path, {details["date"]: details})
    files = index["task_files"][details["date"]]
    assert set(files) == {"task-alpha", "task-beta"}
    ids = []
    for task, relative in files.items():
        document = json.loads((tmp_path / relative).read_text(encoding="utf-8"))
        assert document["task_id"] == task
        assert {r["task_id"] for r in document["runs"]} == {task}
        assert document["coverage"]["published_cells"] == 2
        assert document["coverage"]["matched_runs"] == 6
        ids.extend(r["id"] for r in document["runs"])
    assert sorted(ids) == sorted(r["id"] for r in details["runs"])
    assert json.loads((tmp_path / "2020-01-02.json").read_text(encoding="utf-8")) == details


@pytest.mark.parametrize("case,counts", [("complete", (2, 3)), ("empty", (0, 0)), ("unknown", (None, 4)), ("terminus", (1, 2)), ("raw", (None, None))])
def test_complete_trajectory_counts_calls_without_splitting_shell_strings(case, counts):
    assert trajectory_counts(call_telemetry_fixture()[case]) == counts
    assert trajectory_counts(None) == (None, None)


@pytest.mark.parametrize("case", ["malformed", "partial", "continued"])
def test_partial_or_malformed_trajectory_cannot_supply_totals(case):
    with pytest.raises(DataError):
        trajectory_counts(call_telemetry_fixture()[case])


def test_converter_counts_unknown_tools_even_when_safe_replay_omits_them():
    sample = run_details_fixture()
    rid = run_id("2020-01-02", "task-alpha", "model-a", "agent-test@high", 0)
    _, details, _ = reconstruct_board(sample["published"], sample["board"],
        telemetry={rid: {"complete": True, "trajectory": sample["trajectory"]}})
    row = next(row for row in details["runs"] if row["id"] == rid)
    assert row["command_count"] is None and row["tool_call_count"] == 3
    assert len(row["steps"]) == 2
    assert details["coverage"]["tool_call_runs"] == 1
    assert details["availability"]["command_count"] == "unavailable"
    assert "PRIVATE_" not in json.dumps(details)


def test_finalized_evaluator_aliases_flow_to_bound_public_fields():
    sample = run_details_fixture()
    sample["board"]["results"][0]["harness"] = call_telemetry_fixture()["harness"]
    _, details, _ = reconstruct_board(sample["published"], sample["board"])
    row = details["runs"][0]
    assert (row["command_count"], row["tool_call_count"], row["input_tokens"], row["output_tokens"]) == (2, 3, 8, 2)
    assert details["coverage"]["command_runs"] == details["coverage"]["tool_call_runs"] == 1
    assert all(r["command_count"] is None for r in details["runs"][1:])
    sample["board"]["results"][0]["harness"]["trajectory_complete"] = False
    _, details, _ = reconstruct_board(sample["published"], sample["board"])
    assert all(r["command_count"] is None and r["tool_call_count"] is None for r in details["runs"])


@pytest.mark.parametrize("value", call_telemetry_fixture()["invalid_counts"])
def test_invalid_bound_counts_do_not_turn_into_measurements(value):
    sample = run_details_fixture()
    rid = run_id("2020-01-02", "task-alpha", "model-a", "agent-test@high", 0)
    with pytest.raises(DataError):
        reconstruct_board(sample["published"], sample["board"],
            telemetry={rid: {"complete": True, "n_command_calls": value}})


def test_conflicting_counts_and_aliases_are_rejected():
    sample = run_details_fixture()
    rid = run_id("2020-01-02", "task-alpha", "model-a", "agent-test@high", 0)
    payload = {"complete": True, **call_telemetry_fixture()["harness"]}
    payload["command_count"] = 1
    with pytest.raises(DataError, match="aliases"):
        reconstruct_board(sample["published"], sample["board"], telemetry={rid: payload})
    payload.pop("command_count")
    payload["n_command_calls"] = 4
    with pytest.raises(DataError, match="exceeds"):
        reconstruct_board(sample["published"], sample["board"], telemetry={rid: payload})


@pytest.mark.parametrize("value", [-1, .5, True, 2])
def test_task_viewer_rejects_invalid_or_inconsistent_counts(value):
    sample = task_run_view_fixture()
    sample["details"]["runs"][0]["command_count"] = value
    result = run_view_js("console.log(JSON.stringify(T.taskRunData(input.day,input.details,input.task)));", sample)
    assert not result["available"] and result["reason"] == "telemetry"


def test_task_viewer_preserves_measured_zero_commands():
    result = run_view_js("console.log(JSON.stringify(T.taskRunData(input.day,input.details,input.task)));")
    assert result["runs"][0]["command_count"] == 0
    assert result["runs"][0]["tool_call_count"] == 1


def test_partial_marker_cannot_be_overridden_by_bound_count_aliases():
    sample = run_details_fixture()
    rid = run_id("2020-01-02", "task-alpha", "model-a", "agent-test@high", 0)
    payload = {"complete": True, **call_telemetry_fixture()["harness"]}
    payload["trajectory_complete"] = False
    with pytest.raises(DataError, match="partial trajectory"):
        reconstruct_board(sample["published"], sample["board"], telemetry={rid: payload})


def test_persisted_eval_json_adapter_keeps_every_attempt_and_public_counts():
    sample = eval_results_fixture()
    original = deepcopy(sample)
    board = board_from_eval_results(sample["records"])
    day, details, _ = reconstruct_board(sample["published"], board)
    assert day["leaderboard"] == sample["published"]["leaderboard"]
    original_matrix = deepcopy(day["matrix"])
    for row in original_matrix["rows"]:
        assert len(row.pop("trials")) == 3
    assert original_matrix == sample["published"]["matrix"]
    assert len(details["runs"]) == 12 and sum(row["outcome"] for row in details["runs"]) == 6
    assert all((row["command_count"], row["tool_call_count"]) == (2, 3) for row in details["runs"])
    actual = {(row["task_id"], row["model"], row["scaffold"], row["attempt_index"]):
              (row["outcome"], row["wall_sec"]) for row in details["runs"]}
    expected = {(row["task_id"], row["model"].split("@")[0], row["scaffold"] + "@high", row["trial"]):
                (int(row["passed"]), row["cost_s"]) for row in sample["records"]}
    assert actual == expected
    assert sample == original
    assert all(row["cost_usd"] is None and row["input_tokens"] is None and row["steps"] == []
               for row in details["runs"])
    encoded = json.dumps((board, day, details))
    assert "/private/" not in encoded and "advisory" not in encoded


@pytest.mark.parametrize("case", ["advisory", "unobserved", "unparsed_reward", "unequal", "aggregate", "cell",
                                  "duplicate", "missing_trial", "reward_disagrees", "harness", "certificate"])
def test_eval_json_adapter_refuses_unproven_publication(case):
    sample = eval_results_fixture(case)
    with pytest.raises(DataError):
        reconstruct_board(sample["published"], board_from_eval_results(sample["records"]))


def test_eval_json_explicit_exclusion_does_not_change_included_trial_count():
    sample = eval_results_fixture("excluded")
    exclusions = ["model-a@max"]
    with pytest.raises(DataError):
        board_from_eval_results(sample["records"])
    board = board_from_eval_results(sample["records"], excluded_specs=exclusions)
    _, details, audit = reconstruct_board(sample["published"], board, excluded_specs=exclusions)
    assert board["n_trials"] == 3 and len(details["runs"]) == 12
    assert audit["excluded_specs"] == {"model-a@max": 1}


def test_eval_json_preserves_measured_zero_and_unavailable_counts():
    sample = eval_results_fixture("zero_missing")
    _, details, _ = reconstruct_board(sample["published"], board_from_eval_results(sample["records"]))
    assert [(row["command_count"], row["tool_call_count"]) for row in details["runs"][:3]] == [
        (0, 0), (None, None), (None, None)]


@pytest.mark.parametrize("case", ["complete", "excluded", "cell"])
def test_eval_results_cli_checks_parity_before_writing_public_files(tmp_path, case):
    sample = eval_results_fixture(case)
    source = tmp_path / "eval.json"
    published = tmp_path / "published.json"
    source.write_text(json.dumps(sample["records"]), encoding="utf-8")
    published.write_text(json.dumps(sample["published"]), encoding="utf-8")
    out = tmp_path / "public" / "runs.json"
    day_out = tmp_path / "public" / "day.json"
    audit_out = tmp_path / "private" / "audit.json"
    publish_dir = tmp_path / "public" / "run-details"
    script = Path(__file__).resolve().parents[1] / "web/gen_run_details.py"
    command = [sys.executable, str(script), "--published", str(published), "--eval-results", str(source),
               "--out", str(out), "--day-out", str(day_out), "--audit-out", str(audit_out),
               "--publish-dir", str(publish_dir)]
    if case == "excluded":
        command.extend(["--exclude-spec", "model-a@max"])
    result = subprocess.run(command, capture_output=True, text=True)
    if case == "cell":
        assert result.returncode != 0 and "published matrix" in result.stderr
        assert not out.exists() and not day_out.exists() and not audit_out.exists()
        assert not publish_dir.exists()
        return
    assert result.returncode == 0, result.stderr
    details = json.loads(out.read_text(encoding="utf-8"))
    day = json.loads(day_out.read_text(encoding="utf-8"))
    audit = json.loads(audit_out.read_text(encoding="utf-8"))
    assert day["leaderboard"] == sample["published"]["leaderboard"]
    original_matrix = deepcopy(day["matrix"])
    for row in original_matrix["rows"]:
        assert len(row.pop("trials")) == 3
    assert original_matrix == sample["published"]["matrix"]
    assert len(details["runs"]) == audit["attempts_preserved"] == 12
    assert audit["aggregate_groups_verified"] == 2 and audit["cells_verified"] == 4
    assert audit["sources"][1]["path"] == str(source.resolve())
    assert json.loads((publish_dir / "2020-01-02.json").read_text(encoding="utf-8")) == details
    for public_path in (tmp_path / "public").rglob("*.json"):
        encoded = public_path.read_text(encoding="utf-8")
        assert "/private/" not in encoded and "trajectory_path" not in encoded and "advisory" not in encoded


@pytest.mark.parametrize("source_flag", ["--board", "--eval-results"])
def test_cli_rejects_raw_inputs_inside_public_checkout(tmp_path, source_flag):
    repo = Path(__file__).resolve().parents[1]
    with pytest.raises(SystemExit) as caught:
        main(["--published", str(tmp_path / "published.json"), source_flag, str(repo / "raw-input.json"),
              "--out", str(tmp_path / "runs.json"), "--day-out", str(tmp_path / "day.json"),
              "--audit-out", str(tmp_path / "audit.json")])
    assert caught.value.code == 2


def test_attach_repeat_trials_preserves_scores_metadata_and_aligns_all_matrix_orders():
    sample = repeat_trials_fixture()
    before = deepcopy(sample)
    day = gen_run_details.attach_repeat_trials(sample["day"], sample["details"])
    assert sample == before
    assert day["matrix"]["rows"][0]["trials"] == [[0, None, 1], [1, None, 1], [0, None, 0]]
    assert day["matrices"]["agent-test@high"]["rows"][0]["trials"] == [[1, 0, None], [1, 1, None], [0, 0, None]]
    for matrix in [day["matrix"], *day["matrices"].values()]:
        for row in matrix["rows"]:
            row.pop("trials")
    assert day == before["day"]


@pytest.mark.parametrize("case", ["duplicate", "truncated", "missing_cell", "unobserved",
    "invalid_outcome", "invalid_index", "wrong_count", "wrong_id", "wrong_date", "wrong_group",
    "wrong_cell", "wrong_majority", "aggregate", "conflicting_null", "existing_boolean", "invalid_aggregation"])
def test_attach_repeat_trials_refuses_ambiguous_or_incomplete_public_records(case):
    sample = repeat_trials_fixture(case)
    before = deepcopy(sample)
    with pytest.raises(DataError):
        gen_run_details.attach_repeat_trials(sample["day"], sample["details"])
    assert sample == before


def test_attach_repeat_trials_keeps_single_run_as_one_round():
    sample = repeat_trials_fixture("single")
    day = gen_run_details.attach_repeat_trials(sample["day"], sample["details"])
    assert day["matrix"]["rows"][0]["trials"] == [[0, None, 1]]


def test_repeat_rounds_reproduce_mean_and_sample_standard_deviation():
    import statistics
    sample = repeat_trials_fixture()
    day = gen_run_details.attach_repeat_trials(sample["day"], sample["details"])
    rates = [sum(value for value in trial if value is not None) / 2
             for trial in day["matrix"]["rows"][0]["trials"]]
    assert rates == [.5, 1., 0.]
    assert statistics.mean(rates) == .5
    assert statistics.stdev(rates) == .5
