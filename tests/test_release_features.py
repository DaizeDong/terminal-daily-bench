"""Release history and outcome denominators use the shipped browser runtime."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "tools"))
import gen_pages
import gen_site_data
from make_fixtures import release_insights_fixture, detail_content_fixture


def run_js(script, fixture, *, catalogue=False):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to exercise the published release runtime")
    source = """
const fs = require('fs'), vm = require('vm');
const INPUT = JSON.parse(fs.readFileSync(0, 'utf8'));
const box = {window: {TDB: {taskSuites: t => t.suites || (t.suite ? [t.suite] : [])}}, console, URL, URLSearchParams};
vm.createContext(box);
for (const file of FILES) vm.runInContext(fs.readFileSync(file, 'utf8'), box);
const T = box.window.TDB;
""".replace("FILES", json.dumps([str(ROOT / "docs/assets/tdb-data.js"), str(ROOT / "docs/assets/tdb-releases.js")]))
    if catalogue:
        page = (ROOT / "docs/registry/index.html").read_text(encoding="utf-8")
        pure = page[page.index('  var T = window.TDB;'):page.index('  Promise.all([')]
        probe = "(function () {\n" + pure + "\nObject.assign(globalThis, {prepareTasks, readTaskState, filterTasks, sortTasks, taskRow, taskStateUrl});\n})();"
        source += "vm.runInContext(" + json.dumps(probe) + ", box);\n"
    result = subprocess.run([node, "-e", source + script], input=json.dumps(fixture),
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_history_distinguishes_first_seen_from_returning_tasks():
    fixture = release_insights_fixture()
    result = run_js("console.log(JSON.stringify(T.releaseHistory(INPUT.site)));", fixture)
    assert result[0]["new"] == ["task-removed", "task-retained", "task-return"]
    assert result[1]["removed"] == ["task-removed", "task-return"]
    latest = result[2]
    assert latest["previous"] == "2020-01-02"
    assert latest["new"] == ["task-new"]
    assert latest["retained"] == ["task-retained"]
    assert latest["returned"] == ["task-return"]
    assert latest["removed"] == ["task-middle"]


def test_history_ignores_fresh_counter_input_order_and_duplicate_memberships():
    fixture = release_insights_fixture()
    original = run_js("console.log(JSON.stringify(T.releaseHistory(INPUT.site)));", fixture)
    fixture["site"]["suites"].reverse()
    fixture["site"]["tasks"].reverse()
    for task in fixture["site"]["tasks"]:
        task["suites"] += task["suites"] + ["sample"]
    for suite in fixture["site"]["suites"]:
        suite["fresh_tasks"] = 999
    assert run_js("console.log(JSON.stringify(T.releaseHistory(INPUT.site)));", fixture) == original


def test_prior_release_rosters_preserve_first_seen_when_task_edges_are_incomplete():
    fixture = release_insights_fixture()
    returning = next(task for task in fixture["site"]["tasks"] if task["id"] == "task-return")
    returning["suites"] = returning["suites"][-1:]
    result = run_js("console.log(JSON.stringify(T.releaseHistory(INPUT.site)));", fixture)
    assert result[-1]["new"] == ["task-new"]
    assert result[-1]["returned"] == ["task-return"]


def test_task_catalogue_merges_duplicate_ids_without_losing_release_history():
    fixture = release_insights_fixture()
    retained = next(task for task in fixture["site"]["tasks"] if task["id"] == "task-retained")
    latest = dict(retained, title=detail_content_fixture()["summary"], suites=retained["suites"][1:])
    retained["suites"] = retained["suites"][:1]
    fixture["site"]["tasks"].append(latest)
    result = run_js(
        "const before = JSON.stringify(INPUT.site);"
        "const tasks = T.uniqueTaskCatalogue(INPUT.site);"
        "console.log(JSON.stringify({tasks, unchanged:before === JSON.stringify(INPUT.site),"
        "history:T.releaseHistory({suites:INPUT.site.suites,tasks})}));", fixture,
    )
    assert len(result["tasks"]) == len({task["id"] for task in fixture["site"]["tasks"]})
    merged = next(task for task in result["tasks"] if task["id"] == retained["id"])
    assert merged["title"] == latest["title"]
    assert merged["suite"] == "2020-01-03"
    assert merged["suites"] == sorted(fixture["memberships"])
    assert {row["suite"] for row in merged["suite_memberships"]} == set(fixture["memberships"])
    assert result["unchanged"]
    assert {row["id"]: row["ids"] for row in result["history"]} == {
        day: sorted(ids) for day, ids in fixture["memberships"].items()
    }


def test_catalogue_latest_release_uses_rosters_and_memberships_and_keeps_distinct_ids():
    fixture = release_insights_fixture()
    for task in fixture["site"]["tasks"]:
        task["suite_memberships"] = [{"suite": day} for day in task["suites"]]
        task["suites"] = []
    fixture["site"]["tasks"][0]["title"] = fixture["site"]["tasks"][1]["title"]
    result = run_js(
        "const tasks = box.prepareTasks(INPUT.site, null);"
        "const state = box.readTaskState('');"
        "console.log(JSON.stringify(box.sortTasks(tasks,state).map(t=>({id:t.id,suites:t._suites}))));",
        fixture, catalogue=True,
    )
    assert len(result) == len(fixture["site"]["tasks"])
    assert [task["suites"][0] for task in result] == [
        "2020-01-03", "2020-01-03", "2020-01-03", "2020-01-02", "2020-01-01",
    ]
    memberships_only = dict(fixture, site=dict(fixture["site"], suites=[]))
    assert run_js("console.log(JSON.stringify(T.releaseHistory(INPUT.site)));", memberships_only) == run_js(
        "console.log(JSON.stringify(T.releaseHistory(INPUT.site)));", fixture,
    )


def test_catalogue_older_release_filter_preserves_latest_date_in_rows():
    fixture = release_insights_fixture()
    result = run_js(
        "const tasks = box.prepareTasks(INPUT.site,null);"
        "const state = box.readTaskState('?release=2020-01-01');"
        "const rows = box.sortTasks(box.filterTasks(tasks,state),state);"
        "const retained = rows.find(t=>t.id==='task-retained');"
        "console.log(JSON.stringify({ids:rows.map(t=>t.id), row:box.taskRow(retained,state,false,{})}));",
        fixture, catalogue=True,
    )
    assert set(result["ids"]) == set(fixture["memberships"]["2020-01-01"])
    assert 'data-label="Latest release"' in result["row"]
    assert ">2020-01-03</a>" in result["row"]
    assert ">2020-01-01</a>" not in result["row"]
    assert "tdb-task-memberships" not in result["row"]


def test_unsolved_counts_only_tasks_with_actual_binary_outcomes():
    fixture = release_insights_fixture()
    fixture["latest_day"]["matrix"]["rows"][1]["g"][2] = None
    result = run_js("console.log(JSON.stringify(T.outcomeCoverage(INPUT.latest_day, INPUT.memberships['2020-01-03'])));", fixture)
    assert (result["tasks"], result["evaluated"], result["unsolved"], result["cells"]) == (3, 2, 1, 3)
    assert result["byTask"]["task-new"] == {"passed": 0, "evaluated": 0}
    assert result["byTask"]["task-retained"] == {"passed": 0, "evaluated": 1}


def test_missing_day_is_unmeasured_not_all_failed():
    fixture = release_insights_fixture()
    result = run_js("console.log(JSON.stringify(T.outcomeCoverage(null, INPUT.memberships['2020-01-03'])));", fixture)
    assert result["evaluated"] == result["unsolved"] == result["cells"] == 0


def test_outcomes_join_task_ids_and_do_not_borrow_other_dates():
    fixture = release_insights_fixture()
    result = run_js("console.log(JSON.stringify(T.outcomeCoverage(INPUT.previous_day, INPUT.memberships['2020-01-03'])));", fixture)
    assert result["byTask"]["task-return"]["evaluated"] == 0
    assert result["byTask"]["task-new"]["evaluated"] == 0
    assert result["byTask"]["task-retained"] == {"passed": 1, "evaluated": 2}


@pytest.mark.parametrize("scope,expected", [("new", ["task-new"]), ("retained", ["task-retained"]),
                                           ("returned", ["task-return"]), ("removed", ["task-middle"])])
def test_catalogue_scope_filters_include_removed_tasks(scope, expected):
    result = run_js(
        "const tasks = box.prepareTasks(INPUT.site, null);"
        f"const state = box.readTaskState('?release=2020-01-03&scope={scope}');"
        "console.log(JSON.stringify(box.filterTasks(tasks, state).map(t => t.id)));",
        release_insights_fixture(), catalogue=True,
    )
    assert result == expected


def test_catalogue_keeps_old_links_and_writes_public_query_names():
    result = run_js(
        "const state = box.readTaskState('?suite=2020-01-03&scope=new&q=repair&repo=example%2Fproject&dir=asc');"
        "console.log(JSON.stringify({state, url:String(box.taskStateUrl('https://example.com/tasks/?suite=2020-01-03&q=repair',state))}));",
        release_insights_fixture(), catalogue=True,
    )
    assert result["state"]["suite"] == "2020-01-03"
    assert "release=2020-01-03" in result["url"] and "query=repair" in result["url"]
    assert "project=example%2Fproject" in result["url"] and "order=asc" in result["url"]
    assert "suite=" not in result["url"] and "q=" not in result["url"]


def test_title_cleanup_matches_python_without_changing_formulas():
    fixture = release_insights_fixture()
    result = run_js("console.log(JSON.stringify(INPUT.title_cases.map(pair => T.cleanTaskTitle(pair[0]))));", fixture)
    assert result == [gen_pages.clean_task_title(raw) for raw, _ in fixture["title_cases"]]
    assert result == [expected for _, expected in fixture["title_cases"]]


def test_task_details_mount_dated_outcomes_without_global_counts():
    fixture = detail_content_fixture()
    task = dict(fixture["task"], solved_by=0, n_models=3)
    page = gen_pages.task_page_body(task, fixture["package"])
    assert 'data-task-runs="task-parser"' in page
    assert "Models solved" not in page and "0/3" not in page
    assert "Success criterion:" in page
    assert fixture["summary"] in page


def test_reconstructed_instruction_preamble_does_not_become_task_summary():
    fixture = detail_content_fixture()
    instruction = fixture["package"]["instruction"].replace("description below alone", "specification below alone")
    instruction = instruction.replace("Context (de-identified)", "Required behaviour")
    assert gen_pages.task_summary(instruction) == fixture["summary"]


def test_public_task_detail_mapping_accepts_only_metadata_fields(tmp_path):
    fixture = detail_content_fixture()
    path = tmp_path / "task-details.json"
    mapping = {fixture["task"]["id"]: fixture["package"]}
    path.write_text(json.dumps(mapping), encoding="utf-8")
    assert gen_pages.load_detail_data(path) == mapping
    mapping[fixture["task"]["id"]]["solution"] = fixture["summary"]
    path.write_text(json.dumps(mapping), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported"):
        gen_pages.load_detail_data(path)


def test_public_task_detail_mapping_rejects_path_ids_and_nontext_instruction(tmp_path):
    fixture = detail_content_fixture()
    path = tmp_path / "task-details.json"
    path.write_text(json.dumps({"../" + fixture["task"]["id"]: fixture["package"]}), encoding="utf-8")
    with pytest.raises(ValueError, match="identity"):
        gen_pages.load_detail_data(path)
    package = dict(fixture["package"], instruction=[fixture["summary"]])
    path.write_text(json.dumps({fixture["task"]["id"]: package}), encoding="utf-8")
    with pytest.raises(ValueError, match="string"):
        gen_pages.load_detail_data(path)


def test_instruction_cleanup_preserves_literal_comments_and_removes_generation_notes():
    fixture = detail_content_fixture()
    source = fixture["generation_comment"] + "\n" + fixture["package"]["instruction"] + "\n" + fixture["literal_comment"]
    cleaned = gen_pages.clean_instruction_text(source)
    assert fixture["generation_comment"] not in cleaned
    assert fixture["literal_comment"] in cleaned
    assert "upstream provenance" not in cleaned
    assert fixture["summary"] in cleaned
    assert gen_pages.clean_instruction_text(cleaned) == cleaned


def test_metadata_summary_is_rendered_when_original_has_no_safe_excerpt(tmp_path):
    fixture = detail_content_fixture()
    package = dict(fixture["package"], instruction=fixture["invalid"][0], summary=fixture["summary"])
    path = tmp_path / "task-details.json"
    path.write_text(json.dumps({fixture["task"]["id"]: package}), encoding="utf-8")
    package = gen_pages.load_detail_data(path)[fixture["task"]["id"]]
    page = gen_pages.task_page_body(fixture["task"], package)
    assert fixture["summary"] in page
    assert "no task description provided" not in page


def test_catalogue_additions_survive_without_local_packages_and_repeat(tmp_path):
    fixture = release_insights_fixture()
    additions = tmp_path / "docs/data/catalogue-additions.json"
    additions.parent.mkdir(parents=True)
    additions.write_text(json.dumps(fixture["site"]), encoding="utf-8")
    first = gen_site_data.collect(tmp_path, {})
    assert {task["id"] for task in first["tasks"]} == {task["id"] for task in fixture["site"]["tasks"]}
    assert {suite["id"]: suite["task_ids"] for suite in first["suites"]} == {
        day: sorted(ids) for day, ids in fixture["memberships"].items()
    }
    (tmp_path / "docs/site_data.json").write_text(json.dumps(first), encoding="utf-8")
    second = gen_site_data.collect(tmp_path, {})
    assert first["tasks"] == second["tasks"] and first["suites"] == second["suites"]


def test_catalogue_additions_keep_newer_existing_metadata_and_memberships():
    fixture = release_insights_fixture()
    import copy
    additions = copy.deepcopy(fixture["site"])
    existing = copy.deepcopy(fixture["site"])
    current = existing["tasks"][0]
    current["title"] = detail_content_fixture()["summary"]
    additions["tasks"] = additions["tasks"][:-1]
    additions["suites"] = additions["suites"][:-1]
    merged = gen_site_data.merge_catalogue_additions({"tasks": [], "suites": []}, additions, existing)
    found = {task["id"]: task for task in merged["tasks"]}
    assert found[current["id"]]["title"] == current["title"]
    assert found[current["id"]]["suites"] == current["suites"]
    assert set(found) == {task["id"] for task in existing["tasks"]}
    assert len(merged["suites"]) == len(existing["suites"])


def test_local_package_metadata_remains_primary_over_additions(tmp_path):
    fixture = detail_content_fixture()
    task = fixture["task"]
    package = tmp_path / "tasks/archive" / task["id"]
    package.mkdir(parents=True)
    (package / "instruction.md").write_text(fixture["package"]["instruction"], encoding="utf-8")
    (package / "record.json").write_text(json.dumps({"repo": task["repo"], "pr_number": task["pr_number"]}), encoding="utf-8")
    additions = tmp_path / "docs/data/catalogue-additions.json"
    additions.parent.mkdir(parents=True)
    source = dict(task, title=fixture["summary"])
    additions.write_text(json.dumps({"tasks": [source], "suites": []}), encoding="utf-8")
    data = gen_site_data.collect(tmp_path, {})
    assert data["tasks"][0]["title"] == task["title"]
    assert set(task["suites"]) <= set(data["tasks"][0]["suites"])


@pytest.mark.parametrize("field", ["solved_by", "source_files"])
def test_additions_reject_score_authority_and_nonmetadata_fields(field):
    fixture = release_insights_fixture()
    fixture["site"]["tasks"][0][field] = 1
    with pytest.raises(ValueError):
        gen_site_data.validate_catalogue_additions(fixture["site"])
