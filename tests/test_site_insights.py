"""Paired statistics and measured efficiency, executed in the shipped JS runtime."""
from __future__ import annotations

import importlib.util
import csv
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
spec = importlib.util.spec_from_file_location("insight_fixtures", ROOT / "tools/make_fixtures.py")
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


@pytest.fixture
def sample():
    return fixtures.site_insights_fixture()


def run_js(script, sample):
    if not NODE:
        pytest.skip("Node is required to execute the published statistics runtime")
    source = r"""
      const fs = require('fs'), vm = require('vm');
      const INPUT = JSON.parse(fs.readFileSync(0, 'utf8'));
      const box = {window: {TDB: {modelLabel: x => x}}, console};
      Object.defineProperty(box, 'document', {get() {throw new Error('Pure API accessed DOM');}});
      vm.createContext(box);
      for (const file of FILES) vm.runInContext(fs.readFileSync(file, 'utf8'), box);
      const T = box.window.TDB;
      function freeze(obj) {if (obj && typeof obj === 'object') {Object.values(obj).forEach(freeze); Object.freeze(obj);} return obj;}
      const original = JSON.stringify(INPUT); freeze(INPUT);
    """.replace("FILES", json.dumps([str(ROOT / "docs/assets/tdb-data.js"), str(ROOT / "docs/assets/tdb-explorer.js"), str(ROOT / "docs/assets/tdb-insights.js"), str(ROOT / "docs/assets/tdb-share.js")]))
    result = subprocess.run([NODE, "-e", source + script + "\nif (JSON.stringify(INPUT) !== original) throw Error('Input mutated');"],
                            input=json.dumps(sample), capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_comparison_uses_shared_evaluated_tasks_and_keeps_four_groups(sample):
    result = run_js("console.log(JSON.stringify(T.compareModels(INPUT.day, INPUT.site, INPUT.cap, 'model-a', 'model-b')));", sample)
    assert result["available"]
    assert result["n"] == 3
    assert result["a"] == result["b"] == {"solved": 2, "n": 3, "rate": 2 / 3}
    assert result["delta"] == 0
    assert {k: [t["id"] for t in v] for k, v in result["groups"].items()} == {
        "both": ["task-gamma"], "a_only": ["task-alpha"], "b_only": ["task-beta"], "neither": []}
    assert [t["id"] for t in result["missing"]] == ["task-new"]


def test_capability_comparison_uses_same_pair_denominator_and_preserves_empty(sample):
    result = run_js("console.log(JSON.stringify(T.compareModels(INPUT.day, INPUT.site, INPUT.cap, 'model-a', 'model-b').axes));", sample)
    by_code = {a["code"]: a for a in result}
    assert by_code["C1"]["n"] == 2
    assert by_code["C2"]["n"] == 1
    assert by_code["C2"]["a"]["rate"] == 1
    assert by_code["C3"]["n"] == 0
    assert by_code["C3"]["delta"] is None
    assert by_code["C3"]["preliminary"]


@pytest.mark.parametrize("first,second", [("model-a", "model-a"), ("absent", "model-b")])
def test_invalid_model_selection_is_not_a_zero_result(sample, first, second):
    result = run_js(f"console.log(JSON.stringify(T.compareModels(INPUT.day, INPUT.site, INPUT.cap, {json.dumps(first)}, {json.dumps(second)})));", sample)
    assert result["available"] is False
    assert result["reason"] == "selection"


def test_profile_peer_gaps_exclude_unmeasured_peers_and_cells(sample):
    result = run_js("console.log(JSON.stringify(T.modelProfile(INPUT.day, INPUT.site, INPUT.cap, 'model-b')));", sample)
    by_code = {a["code"]: a for a in result["axes"]}
    assert by_code["C2"]["n"] == 2
    assert by_code["C2"]["rate"] == .5
    assert by_code["C2"]["pairs"] == 1
    assert by_code["C2"]["peers"] == 1
    assert by_code["C2"]["delta"] == 0  # Compared only on gamma, both solved.
    assert by_code["C3"]["rate"] is None
    assert by_code["C3"]["peerRate"] is None
    assert result["failed"][0]["id"] == "task-alpha"  # Peers solved this failure.


def test_profile_does_not_call_unmeasured_model_zero_percent(sample):
    result = run_js("console.log(JSON.stringify(T.modelProfile(INPUT.day, INPUT.site, INPUT.cap, 'model-empty')));", sample)
    assert result["overall"] == {"solved": 0, "n": 0, "rate": None}
    assert all(a["delta"] is None for a in result["axes"])
    assert result["solved"] == result["failed"] == []


def test_release_comparison_joins_ids_and_separates_membership_from_outcomes(sample):
    # Different task orders must not change the paired result.
    sample["previous_day"]["matrix"]["tasks"] = ["task-old", "task-beta", "task-alpha"]
    sample["previous_day"]["matrix"]["rows"][0]["g"] = [1, 0, 0]
    result = run_js("console.log(JSON.stringify(T.compareReleases(INPUT.previous_day, INPUT.day, INPUT.site, 'model-a')));", sample)
    assert result["available"]
    assert (result["shared"], result["n"], result["delta"]) == (2, 2, -.5)
    assert [t["id"] for t in result["groups"]["b_only"]] == ["task-alpha"]
    assert {t["id"] for t in result["added"]} == {"task-gamma", "task-new"}
    assert [t["id"] for t in result["removed"]] == ["task-old"]


def test_release_comparison_excludes_missing_shared_outcomes(sample):
    result = run_js("console.log(JSON.stringify(T.compareReleases(INPUT.previous_day, INPUT.day, INPUT.site, 'model-b')));", sample)
    assert (result["shared"], result["n"]) == (2, 1)
    assert result["missing"][0]["id"] == "task-beta"


@pytest.mark.parametrize("change", ["scaffold", "settings", "missing_scaffold"])
def test_release_comparison_refuses_different_or_unknown_settings(sample, change):
    old = sample["previous_day"]["matrix"]
    if change == "scaffold":
        old["scaffold"] = "single_shot@high"
    elif change == "settings":
        old["settings"] = {"timeout": 10}
    else:
        del old["scaffold"]
    result = run_js("console.log(JSON.stringify(T.compareReleases(INPUT.previous_day, INPUT.day, INPUT.site, 'model-a')));", sample)
    assert result == {"available": False, "reason": "settings"}


def test_efficiency_counts_failed_attempt_costs_and_uses_metric_matched_success(sample):
    result = run_js("console.log(JSON.stringify(T.efficiencyData(INPUT.day, INPUT.run_details)));", sample)
    rows = {(r["model"], r["effort"]): r for r in result["rows"]}
    default = rows["model-a", "default"]
    assert (default["meanCost"], default["meanCommands"], default["n"]) == (1, 2, 3)
    assert default["costRate"] == 2 / 3
    assert rows["model-a", "high"]["meanCost"] == 3.5
    other = rows["model-b", "default"]
    assert other["meanCost"] == 2
    assert (other["costN"], other["costRate"]) == (2, .5)
    assert (other["toolN"], other["toolRate"]) == (3, 1 / 3)
    assert (other["commandN"], other["commandRate"], other["meanCommands"]) == (2, .5, 2)
    assert other["n"] == 4


def test_efficiency_filters_query_agent_effort_without_borrowing_rows(sample):
    result = run_js("console.log(JSON.stringify(T.efficiencyData(INPUT.day, INPUT.run_details, {query:'model-a', agent:'single_shot', effort:'high'})));", sample)
    assert len(result["rows"]) == 1
    assert result["rows"][0]["effort"] == "high"


def test_efficiency_missing_metrics_remain_null(sample):
    for run in sample["run_details"]["runs"]:
        run["cost_usd"] = run["command_count"] = run["tool_call_count"] = None
    result = run_js("console.log(JSON.stringify(T.efficiencyData(INPUT.day, INPUT.run_details)));", sample)
    assert result["available"]
    assert all(r["meanCost"] is None and r["meanCommands"] is None and r["meanTools"] is None and r["costRate"] is None for r in result["rows"])


@pytest.mark.parametrize("mutation", ["date", "cost", "duplicate", "unknown_model", "unknown_setting", "unknown_task", "different_outcome"])
def test_efficiency_rejects_malformed_or_unjoined_observations(sample, mutation):
    details = sample["run_details"]
    if mutation == "date":
        details["date"] = "2020-01-03"
    elif mutation == "cost":
        details["runs"][0]["cost_usd"] = -1
    elif mutation == "duplicate":
        details["runs"].append(dict(details["runs"][0]))
    elif mutation == "unknown_model":
        details["runs"][0]["model"] = "model-unpublished"
    elif mutation == "unknown_setting":
        details["runs"][0]["scaffold"] = "unpublished"
    elif mutation == "unknown_task":
        details["runs"][0]["task_id"] = "task-unpublished"
    else:
        details["runs"][0]["outcome"] = 0
    result = run_js("console.log(JSON.stringify(T.efficiencyData(INPUT.day, INPUT.run_details)));", sample)
    assert result == {"available": False, "reason": "invalid", "rows": []}


def test_missing_published_telemetry_does_not_make_a_chart(sample):
    result = run_js("console.log(JSON.stringify(T.efficiencyData(INPUT.day, null)));", sample)
    assert result == {"available": False, "reason": "missing", "rows": []}


def test_multi_trial_efficiency_uses_cell_outcomes_and_keeps_failed_attempt_cost(sample):
    result = run_js("console.log(JSON.stringify(T.efficiencyData(INPUT.multi_day, INPUT.multi_attempt_details)));", sample)
    assert result["available"]
    row, = result["rows"]
    assert (row["n"], row["taskN"], row["taskSolved"], row["rate"]) == (6, 2, 1, .5)
    assert (row["meanCost"], row["meanCommands"], row["meanTools"]) == (2, 2, 3)
    assert (row["commandN"], row["commandTaskN"], row["commandRate"]) == (6, 2, .5)
    assert (row["costN"], row["costTaskN"], row["costRate"]) == (6, 2, .5)


def test_repeated_attempt_identifiers_and_disagreeing_cell_results_are_rejected(sample):
    sample["multi_attempt_details"]["runs"][1]["attempt_index"] = 0
    result = run_js("console.log(JSON.stringify(T.efficiencyData(INPUT.multi_day, INPUT.multi_attempt_details)));", sample)
    assert result == {"available": False, "reason": "invalid", "rows": []}


def test_history_refuses_changed_trial_aggregation(sample):
    sample["day"]["aggregation"] = {"method": "strict_majority", "trials_per_cell": 3, "unit": "task"}
    result = run_js("console.log(JSON.stringify(T.compareReleases(INPUT.previous_day, INPUT.day, INPUT.site, 'model-a')));", sample)
    assert result == {"available": False, "reason": "settings"}


def test_efficiency_keeps_commands_default_when_measurements_are_unpublished(sample):
    for run in sample["run_details"]["runs"]:
        run["command_count"] = run["tool_call_count"] = None
    result = run_js("""
      const rows=T.efficiencyData(INPUT.day,INPUT.run_details).rows;
      console.log(JSON.stringify({automatic:T.efficiencyMetric(rows,null),explicit:T.efficiencyMetric(rows,'cost')}));
    """, sample)
    assert result == {"automatic": "commands", "explicit": "cost"}


def test_efficiency_normalizes_legacy_time_and_preserves_tools(sample):
    result = run_js("""
      const rows=T.efficiencyData(INPUT.day,INPUT.run_details).rows;
      console.log(JSON.stringify({automatic:T.efficiencyMetric(rows,'time'),explicit:T.efficiencyMetric(rows,'tools')}));
    """, sample)
    assert result == {"automatic": "commands", "explicit": "tools"}


@pytest.mark.parametrize("field,value", [("command_count", -1), ("tool_call_count", .5), ("command_count", True), ("command_count", 9)])
def test_efficiency_rejects_invalid_call_counts(sample, field, value):
    sample["run_details"]["runs"][0][field] = value
    result = run_js("console.log(JSON.stringify(T.efficiencyData(INPUT.day, INPUT.run_details)));", sample)
    assert result == {"available": False, "reason": "invalid", "rows": []}


def test_efficiency_does_not_infer_legacy_counts_from_steps_turns_or_time(sample):
    for run in sample["run_details"]["runs"]:
        del run["command_count"]
        del run["tool_call_count"]
    result = run_js("console.log(JSON.stringify(T.efficiencyData(INPUT.day, INPUT.run_details)));", sample)
    assert result["available"]
    assert all(row["meanCommands"] is None and row["meanTools"] is None for row in result["rows"])


def test_comparison_run_variation_uses_only_paired_tasks(sample):
    result = run_js("console.log(JSON.stringify(T.compareModels(INPUT.repeat_day,INPUT.site,INPUT.cap,'model-a','model-b')));", sample)
    assert result["n"] == 3
    assert result["a"]["repeat"]["trialRates"] == pytest.approx([2 / 3, 1, 1 / 3])
    assert result["a"]["rate"] == pytest.approx(2 / 3)
    assert result["a"]["repeat"]["sd"] == pytest.approx(1 / 3)
    assert result["b"]["rate"] == pytest.approx(2 / 3)
    assert result["b"]["repeat"]["sd"] == pytest.approx((1 / 27) ** .5)
    assert result["delta"] == 0
    assert result["a"]["repeat"]["n"] == result["b"]["repeat"]["n"] == 3
    assert [task["id"] for task in result["groups"]["a_only"]] == ["task-alpha"]


def test_profile_capability_variation_does_not_borrow_other_tasks(sample):
    result = run_js("console.log(JSON.stringify(T.modelProfile(INPUT.repeat_day,INPUT.site,INPUT.cap,'model-b')));", sample)
    axes = {axis["code"]: axis for axis in result["axes"]}
    assert axes["C1"]["rate"] == .5
    assert axes["C1"]["repeat"]["sd"] == 0
    assert axes["C1"]["repeat"]["runs"] == 3
    assert axes["C2"]["rate"] == .5
    assert axes["C2"]["repeat"]["sd"] == pytest.approx((1 / 12) ** .5)
    assert axes["C2"]["delta"] == 0
    assert axes["C3"]["rate"] is None and "repeat" not in axes["C3"]


def test_history_compares_majority_accuracy_with_run_sd_on_shared_tasks(sample):
    result = run_js("console.log(JSON.stringify(T.compareReleases(INPUT.repeat_previous_day,INPUT.repeat_day,INPUT.site,'model-a')));", sample)
    assert result["a"]["rate"] == 0
    assert result["a"]["repeat"]["sd"] == pytest.approx((1 / 12) ** .5)
    assert result["b"]["rate"] == .5
    assert result["b"]["repeat"]["sd"] == .5
    assert result["delta"] == -.5
    assert result["a"]["repeat"]["n"] == result["b"]["repeat"]["n"] == 2


def test_efficiency_variation_uses_full_runs_of_only_measured_tasks(sample):
    result = run_js("console.log(JSON.stringify(T.efficiencyData(INPUT.repeat_day,INPUT.run_details)));", sample)
    row = next(row for row in result["rows"] if row["model"] == "model-b")
    assert row["rate"] == row["taskSolved"] / row["taskN"] == .5
    assert row["commandN"] == 2 and row["commandTaskN"] == 2
    assert row["commandRepeat"]["trialRates"] == pytest.approx([.5, 0, 1])
    assert row["commandRate"] == .5
    assert row["commandRepeat"]["sd"] == .5
    assert row["meanCommands"] == 2
    assert row["toolRepeat"]["trialRates"] == pytest.approx([1 / 3] * 3)
    assert row["toolRepeat"]["sd"] == 0


def test_multi_attempt_efficiency_preserves_observed_spread_and_legacy_null(sample):
    result = run_js("console.log(JSON.stringify({multi:T.efficiencyData(INPUT.multi_day,INPUT.multi_attempt_details),legacy:T.efficiencyData(INPUT.day,INPUT.run_details)}));", sample)
    row, = result["multi"]["rows"]
    assert row["commandRepeat"]["trialRates"] == [.5, 1, 0]
    assert row["commandRate"] == .5
    assert row["commandRepeat"]["sd"] == .5
    assert all(row["repeat"] is None and row["commandRepeat"] is None for row in result["legacy"]["rows"])


@pytest.mark.parametrize("mode", ["compare", "profile", "history", "efficiency"])
def test_rendered_insights_show_inline_repeat_variation(mode, sample):
    sample["mode"] = mode
    result = run_js(r"""
      (async () => {
        T.pct = x => (100 * x).toFixed(1) + '%';
        T.getData = async path => path.endsWith('index.json') ?
          {schema:'tdb-run-details-index-v1',dates:[INPUT.repeat_day.date]} : INPUT.run_details;
        T.dayData = async () => INPUT.repeat_previous_day;
        const host = {innerHTML:'',clientWidth:880,addEventListener(){},querySelector(){return null;}};
        const view = T.createInsights(host);
        view.select('model-a');
        view.update({day:INPUT.repeat_day,site:INPUT.site,cap:INPUT.cap,mode:INPUT.mode,
          rows:[],days:[INPUT.repeat_previous_day.date,INPUT.repeat_day.date]});
        await new Promise(resolve => setImmediate(resolve));
        const snapshot = view.snapshot();
        console.log(JSON.stringify({html:host.innerHTML,snapshot,csv:T.resultsCSV(snapshot),svg:T.resultsSVG(snapshot)}));
      })();
    """, sample)
    assert result["snapshot"]["view"] == mode
    assert "tdb-acc-sd" in result["html"]
    notes = " ".join(result["snapshot"]["notes"])
    assert "majority outcomes" in notes
    assert "run standard deviation" in notes
    assert "standard deviation across 3 run accuracies" in result["html"]
    assert "\u00b1" in result["html"]
    assert "tdb-acc-range-value" not in result["html"]
    assert "95%" not in result["html"] and "Wilson" not in result["html"]
    assert "could not be loaded" not in result["html"]
    assert "\u00b1" in result["svg"] and "run standard deviation" in result["svg"]
    if mode in {"compare", "history"}:
        scores = result["snapshot"]["scores"]
        assert len(scores) == 2
        assert [score["rate"] for score in scores] == pytest.approx([2 / 3, 2 / 3] if mode == "compare" else [0, .5])
        assert [score["rate_sd"] for score in scores] == pytest.approx([1 / 3, (1 / 27) ** .5] if mode == "compare" else [(1 / 12) ** .5, .5])
        assert all(not key.endswith(("_min", "_max")) for score in scores for key in score)
        assert all(score["rate_runs"] == 3 for score in scores)
        assert all(score["n"] == (3 if mode == "compare" else 2) for score in scores)
        rows = list(csv.reader(io.StringIO(result["csv"].lstrip("\ufeff"))))
        header = rows.index(["Result", "Majority accuracy", "Run SD", "Runs", "Tasks"])
        assert [row[1] for row in rows[header + 1:header + 3]] == (["66.7%", "66.7%"] if mode == "compare" else ["0.0%", "50.0%"])
        assert "Paired success rate" in result["svg"]
        assert ("66.7% \u00b1 19.2%" if mode == "compare" else "0.0% \u00b1 28.9%") in result["svg"]
    if mode in {"efficiency", "profile"}:
        columns = {column["key"]: column for column in result["snapshot"]["columns"]}
        key = "success_rate_command_subset" if mode == "efficiency" else "rate"
        assert columns[key + "_sd"]["type"] == "percent"
        assert columns[key + "_runs"]["type"] == "number"
        assert not any(key.endswith(("_lo", "_hi", "_min", "_max")) for key in columns)
        assert all(not key.endswith(("_min", "_max")) for row in result["snapshot"]["rows"] for key in row)
    if mode == "profile":
        assert "Solved / tasks" in result["html"]
        assert "Peer differences use paired tasks." in notes
        assert "N counts" not in result["html"]
        assert notes.count("2 of 3 runs") == 1


def test_efficiency_without_measurements_exports_null_variation_instead_of_failing(sample):
    for record in sample["run_details"]["runs"]:
        record["command_count"] = record["tool_call_count"] = record["cost_usd"] = None
    result = run_js(r"""
      (async () => {
        T.pct = x => (100 * x).toFixed(1) + '%';
        T.getData = async path => path.endsWith('index.json') ?
          {schema:'tdb-run-details-index-v1',dates:[INPUT.day.date]} : INPUT.run_details;
        const host = {innerHTML:'',clientWidth:880,addEventListener(){},querySelector(){return null;}};
        const view = T.createInsights(host);
        view.update({day:INPUT.day,site:INPUT.site,cap:INPUT.cap,mode:'efficiency',rows:[]});
        await new Promise(resolve => setImmediate(resolve));
        console.log(JSON.stringify({html:host.innerHTML,snapshot:view.snapshot()}));
      })();
    """, sample)
    assert "unavailable for this date" in result["html"]
    assert "tdb-efficiency-plot" not in result["html"]
    assert len(result["snapshot"]["rows"]) == 3
    assert all(row["success_rate_command_subset_sd"] is None
               and row["success_rate_command_subset_runs"] is None
               for row in result["snapshot"]["rows"])


def test_efficiency_scatter_keeps_majority_points_and_coverage_without_error_bars(sample):
    result = run_js(r"""
      (async () => {
        T.pct = x => (100 * x).toFixed(1) + '%';
        T.getData = async path => path.endsWith('index.json') ?
          {schema:'tdb-run-details-index-v1',dates:[INPUT.outside_range_day.date]} : INPUT.outside_range_details;
        const host = {innerHTML:'',clientWidth:880,addEventListener(){},querySelector(){return null;}};
        const view = T.createInsights(host);
        view.update({day:INPUT.outside_range_day,site:INPUT.site,cap:INPUT.cap,mode:'efficiency',rows:[]});
        await new Promise(resolve => setImmediate(resolve));
        console.log(JSON.stringify({html:host.innerHTML,snapshot:view.snapshot()}));
      })();
    """, sample)
    markup = re.search(r"<svg\b.*?</svg>", result["html"], re.S)
    assert markup is not None
    svg = ET.fromstring(markup.group())
    grid = [line for line in svg.findall("line") if line.get("class") == "tdb-plot-grid"]
    y_zero, y_one = float(grid[0].get("y1")), float(grid[-1].get("y1"))
    groups = {group.get("aria-label").split(",")[0]: group for group in svg.findall("g")}
    rows = {row["model"]: row for row in result["snapshot"]["rows"]}
    assert "standard deviation" not in markup.group() and "run range" not in markup.group()
    for model, majority in (("model-a", 1), ("model-b", 0)):
        group = groups[model]
        point = group.find("circle")
        assert (y_zero - float(point.get("cy"))) / (y_zero - y_one) == majority
        assert group.findall("line") == []
        assert "9 recorded attempts" in group.get("aria-label")
        assert "3 unique tasks" in group.get("aria-label")
        assert rows[model]["success_rate_command_subset"] == majority
        assert rows[model]["success_rate_command_subset_sd"] == 0
        assert rows[model]["success_rate_command_subset_runs"] == 3
