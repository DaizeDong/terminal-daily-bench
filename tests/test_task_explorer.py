"""Execute the task explorer's pure data API against generated measurements."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "docs/assets/tdb-explorer.js"
NODE = shutil.which("node")
spec = importlib.util.spec_from_file_location("task_fixtures", ROOT / "tools/make_fixtures.py")
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


@pytest.fixture
def sample():
    return fixtures.task_matrix_fixture()


def _run(script, payload):
    if not NODE:
        pytest.skip("node is not installed; task explorer runtime checks cannot run")
    assert RUNTIME.is_file(), "The task explorer runtime has not been installed"
    source = r"""
      'use strict';
      const fs = require('fs');
      const vm = require('vm');
      const INPUT = JSON.parse(fs.readFileSync(0, 'utf8'));
      function freeze(value) {
        if (value && typeof value === 'object' && !Object.isFrozen(value)) {
          Object.values(value).forEach(freeze);
          Object.freeze(value);
        }
        return value;
      }
      const sandbox = { window: { TDB: {
        esc: function(value) {
          const entities = {'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'};
          return String(value == null ? '' : value).replace(/[&<>"']/g, c => entities[c]);
        },
        modelLabel: function(model) { return (INPUT.labels || {})[model] || model; },
        agentLabel: function(agent) { return agent; }
      } }, console: console };
      function noDOM() { throw new Error('Pure task data API accessed the DOM'); }
      Object.defineProperty(sandbox, 'document', {get: noDOM});
      Object.defineProperty(sandbox.window, 'document', {get: noDOM});
      vm.createContext(sandbox);
      vm.runInContext(fs.readFileSync(RUNTIME_PATH, 'utf8'), sandbox);
      const T = sandbox.window.TDB;
      const originalInput = JSON.stringify(INPUT);
      freeze(INPUT);
    """.replace("RUNTIME_PATH", json.dumps(str(RUNTIME)))
    source += "\n" + script + """
      if (JSON.stringify(INPUT) !== originalInput) throw new Error('Input was mutated');
    """
    with tempfile.TemporaryDirectory() as temporary:
        probe = Path(temporary) / "task-explorer-probe.js"
        probe.write_text(source, encoding="utf-8")
        result = subprocess.run(
            [NODE, str(probe)], input=json.dumps(payload),
            capture_output=True, text=True, encoding="utf-8",
        )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _grid(sample, day=None, site=None):
    return _run(
        "console.log(JSON.stringify(T.taskGrid(INPUT.day, INPUT.site)));",
        {"day": sample["day"] if day is None else day,
         "site": sample["site"] if site is None else site, "labels": sample["labels"]},
    )


def _view(sample, **options):
    return _run("""
      const grid = T.taskGrid(INPUT.day, INPUT.site);
      const originalGrid = JSON.stringify(grid);
      freeze(grid);
      const view = T.taskView(grid, INPUT.options);
      if (JSON.stringify(grid) !== originalGrid) throw new Error('Grid was mutated');
      console.log(JSON.stringify(view));
    """, {"day": sample["day"], "site": sample["site"],
          "labels": sample["labels"], "options": options})


def _stats(items, key):
    return {item[key]: (item["solved"], item["n"], item["rate"], item["rank"])
            for item in items}


def test_module_load_and_pure_apis_do_not_access_the_dom(sample):
    result = _run("""
      console.log(JSON.stringify(['taskGrid', 'taskView', 'createTaskExplorer']
        .map(name => typeof T[name])));
    """, sample)
    assert result == ["function", "function", "function"]


def test_grid_joins_metadata_by_id_without_using_catalogue_scores(sample):
    grid = _grid(sample)
    assert grid["available"] is True
    assert (grid["date"], grid["scaffold"]) == ("2020-01-01", "single_shot")
    assert [task["id"] for task in grid["tasks"]] == sample["day"]["matrix"]["tasks"]
    assert [task["index"] for task in grid["tasks"]] == list(range(7))
    by_id = {task["id"]: task for task in grid["tasks"]}
    assert (by_id["task-beta"]["title"], by_id["task-beta"]["project"]) == (
        "Repair build sequence", "example/build")
    assert isinstance(by_id["task-omega"]["title"], str) and by_id["task-omega"]["title"]
    assert by_id["task-omega"]["project"] == ""
    assert by_id["task-omega"]["href"] is None
    assert all(isinstance(task["href"], str) for task in grid["tasks"]
               if task["id"] != "task-omega")
    assert "task-unrelated" not in by_id
    assert {row["model"]: row["values"] for row in grid["rows"]} == {
        row["model"]: row["g"] for row in sample["day"]["matrix"]["rows"]}


def test_grid_preserves_untrusted_titles_as_data(sample):
    title = next(task["title"] for task in _grid(sample)["tasks"] if task["id"] == "task-alpha")
    assert title == 'Inspect <img src=x onerror="alert(1)"> & "quotes"'


def test_missing_matrix_does_not_reconstruct_results_from_the_summary(sample):
    grid = _grid(sample, day=sample["missing_day"])
    assert (grid["available"], grid["reason"]) == (False, "missing")


@pytest.mark.parametrize("case", [
    "duplicate_task", "duplicate_model", "short_row", "long_row",
    "boolean", "string", "fraction", "negative", "outside_binary",
])
def test_malformed_matrix_is_rejected_instead_of_rendered_as_empty(sample, case):
    grid = _grid(sample, day=sample["invalid_days"][case])
    assert (grid["available"], grid["reason"]) == (False, "invalid")


def test_model_count_sort_differs_from_rate_and_does_not_use_highest_effort_summary(sample):
    by_count = _view(sample, modelOrder="solved", taskOrder="solved")
    by_rate = _view(sample, modelOrder="rate", taskOrder="solved")
    assert [row["model"] for row in by_count["rows"]] == [
        "model-tie", "model-wide", "model-narrow", "model-zero", "model-unrun"]
    assert [row["model"] for row in by_rate["rows"]] == [
        "model-narrow", "model-tie", "model-wide", "model-zero", "model-unrun"]
    assert _stats(by_count["rows"], "model") == {
        "model-wide": (3, 6, 0.5, 1),
        "model-tie": (3, 5, 0.6, 1),
        "model-narrow": (2, 2, 1, 3),
        "model-zero": (0, 6, 0, 4),
        "model-unrun": (0, 0, None, None),
    }
    assert _stats(by_rate["rows"], "model") == _stats(by_count["rows"], "model")


def test_task_count_and_hardest_sorts_keep_unmeasured_tasks_last(sample):
    by_count = _view(sample, modelOrder="solved", taskOrder="solved")
    hardest = _view(sample, modelOrder="solved", taskOrder="hardest")
    assert [task["id"] for task in by_count["tasks"]] == [
        "task-beta", "task-epsilon", "task-alpha", "task-omega", "task-zeta",
        "task-delta", "task-gamma"]
    assert [task["id"] for task in hardest["tasks"]] == [
        "task-delta", "task-alpha", "task-omega", "task-zeta",
        "task-epsilon", "task-beta", "task-gamma"]
    assert _stats(by_count["tasks"], "id") == {
        "task-beta": (3, 4, 0.75, 1),
        "task-epsilon": (2, 3, 2 / 3, 2),
        "task-alpha": (1, 3, 1 / 3, 3),
        "task-omega": (1, 3, 1 / 3, 3),
        "task-zeta": (1, 3, 1 / 3, 3),
        "task-delta": (0, 3, 0, 6),
        "task-gamma": (0, 0, None, None),
    }
    assert _stats(hardest["tasks"], "id") == _stats(by_count["tasks"], "id")


def test_task_filter_recomputes_model_counts_and_changes_the_leader(sample):
    view = _view(sample, taskQuery="quotes", modelOrder="solved", taskOrder="solved")
    assert [task["id"] for task in view["tasks"]] == ["task-alpha"]
    assert [row["model"] for row in view["rows"]] == [
        "model-narrow", "model-wide", "model-zero", "model-tie", "model-unrun"]
    assert _stats(view["rows"], "model") == {
        "model-narrow": (1, 1, 1, 1), "model-wide": (0, 1, 0, 2),
        "model-zero": (0, 1, 0, 2), "model-tie": (0, 0, None, None),
        "model-unrun": (0, 0, None, None),
    }


def test_model_filter_recomputes_task_difficulty_before_sorting(sample):
    view = _view(sample, modelQuery="model-wide", taskOrder="hardest", modelOrder="solved")
    assert [task["id"] for task in view["tasks"]] == [
        "task-alpha", "task-delta", "task-omega",
        "task-beta", "task-epsilon", "task-zeta", "task-gamma"]
    by_id = {task["id"]: task for task in view["tasks"]}
    assert (by_id["task-alpha"]["solved"], by_id["task-alpha"]["n"], by_id["task-alpha"]["rate"]) == (0, 1, 0)
    assert (by_id["task-beta"]["solved"], by_id["task-beta"]["n"], by_id["task-beta"]["rate"]) == (1, 1, 1)


def test_both_queries_share_the_filtered_scope_and_match_display_names(sample):
    view = _view(sample, modelQuery="  DISPLAY SPECIALIST  ", taskQuery="example/build",
                 modelOrder="solved", taskOrder="hardest")
    assert [row["model"] for row in view["rows"]] == ["model-narrow"]
    assert _stats(view["rows"], "model") == {"model-narrow": (1, 1, 1, 1)}
    assert [task["id"] for task in view["tasks"]] == ["task-beta", "task-delta"]
    assert _stats(view["tasks"], "id") == {
        "task-beta": (1, 1, 1, 1), "task-delta": (0, 0, None, None)}


def test_noncontiguous_filter_and_sort_keep_original_values_and_indices(sample):
    view = _view(sample, taskQuery="example/parse", modelOrder="solved", taskOrder="solved")
    assert [(task["id"], task["index"]) for task in view["tasks"]] == [
        ("task-epsilon", 2), ("task-zeta", 0)]
    values = {row["model"]: row["g"] for row in sample["day"]["matrix"]["rows"]}
    for row in view["rows"]:
        assert row["values"] == values[row["model"]]
        assert [row["values"][task["index"]] for task in view["tasks"]] == [
            values[row["model"]][2], values[row["model"]][0]]


def test_task_query_matches_hidden_id_when_metadata_is_missing(sample):
    view = _view(sample, taskQuery="TASK-OMEGA", modelOrder="solved", taskOrder="solved")
    assert [(task["id"], task["index"]) for task in view["tasks"]] == [("task-omega", 6)]
    assert _stats(view["tasks"], "id") == {"task-omega": (1, 3, 1 / 3, 1)}


@pytest.mark.parametrize("options", [
    {"modelQuery": "absent-model"}, {"taskQuery": "absent-task"},
    {"modelQuery": "absent-model", "taskQuery": "absent-task"},
])
def test_queries_without_matches_return_empty_axes_without_inventing_rates(sample, options):
    view = _view(sample, **options)
    if "modelQuery" in options:
        assert view["rows"] == []
    if "taskQuery" in options:
        assert view["tasks"] == []
    assert all(item["n"] == 0 and item["rate"] is None and item["rank"] is None
               for item in view["rows"] + view["tasks"])


def test_rank_is_count_based_even_when_display_order_is_name(sample):
    by_count = _view(sample, modelOrder="solved", taskOrder="solved")
    by_name = _view(sample, modelOrder="name", taskOrder="name")
    assert _stats(by_name["rows"], "model") == _stats(by_count["rows"], "model")
    assert _stats(by_name["tasks"], "id") == _stats(by_count["tasks"], "id")
    assert by_name["rows"][-1]["model"] == "model-unrun"
    assert by_name["tasks"][-1]["id"] == "task-gamma"


def test_repeated_views_are_deterministic_and_do_not_mutate_inputs(sample):
    result = _run("""
      const grid = T.taskGrid(INPUT.day, INPUT.site);
      freeze(grid);
      const before = JSON.stringify(grid);
      const options = freeze({modelOrder: 'solved', taskOrder: 'hardest'});
      const first = T.taskView(grid, options);
      T.taskView(grid, {modelQuery: 'model-wide', taskQuery: 'example/build'});
      const again = T.taskView(grid, options);
      console.log(JSON.stringify({first: first, again: again, before: before, after: JSON.stringify(grid)}));
    """, sample)
    assert result["first"] == result["again"]
    assert result["before"] == result["after"]


def test_new_date_uses_its_own_roster_configuration_and_results(sample):
    result = _run("""
      const first = T.taskGrid(INPUT.day, INPUT.site);
      const next = T.taskGrid(INPUT.next_day, INPUT.site);
      const missing = T.taskGrid(INPUT.missing_day, INPUT.site);
      const last = T.taskGrid(INPUT.day, INPUT.site);
      console.log(JSON.stringify({
        first: first, next: next, missing: missing, last: last,
        view: T.taskView(next, {modelOrder: 'solved', taskOrder: 'solved'})
      }));
    """, sample)
    assert result["first"] == result["last"]
    assert (result["next"]["date"], result["next"]["scaffold"]) == (
        "2020-01-02", "agent-test@high")
    assert [task["id"] for task in result["next"]["tasks"]] == ["task-next-b", "task-next-a"]
    assert _stats(result["view"]["rows"], "model") == {
        "model-fresh": (1, 1, 1, 1), "model-narrow": (1, 2, 0.5, 1)}
    assert (result["missing"]["available"], result["missing"]["reason"]) == (False, "missing")
