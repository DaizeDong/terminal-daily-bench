"""Generated details retain their release and explain only public task text."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "tools"))

import gen_pages  # noqa: E402
from make_fixtures import detail_content_fixture  # noqa: E402


def test_task_summary_extracts_public_prose_and_omits_unusable_fragments():
    fixture = detail_content_fixture()
    assert gen_pages.task_summary(fixture["package"]["instruction"]) == fixture["summary"]
    assert "j**2 + 4*j + 3" in gen_pages.task_summary(fixture["formula"])
    for instruction in fixture["invalid"]:
        assert gen_pages.task_summary(instruction) == ""


def test_release_results_keep_the_release_date_and_omit_unmeasured_column():
    task = detail_content_fixture()["task"]
    suite = {"id": task["suites"][0], "status": "live"}
    page = gen_pages.suite_page_body(suite, [task], set(task["suites"]))
    assert 'href="../../leaderboard/?d=2020-01-01"' in page
    assert "Models solved" not in page
    assert "Model results" not in gen_pages.suite_page_body(suite, [task], set())

    measured = dict(task, solved_by=0, n_models=3)
    measured_page = gen_pages.suite_page_body(suite, [measured], set(task["suites"]))
    assert "Models solved" not in measured_page
    assert '<span class="tabular-nums">0/3</span>' not in measured_page
    assert 'data-release-tasks="2020-01-01"' in measured_page


def test_task_detail_uses_summary_and_preserves_every_membership():
    fixture = detail_content_fixture()
    page = gen_pages.task_page_body(fixture["task"], fixture["package"])
    assert fixture["summary"] in page
    assert 'class="tdb-task-summary"' in page
    assert "Submit results" in page
    assert "Submit a solution" not in page
    assert "[redacted" not in page
    for day in fixture["task"]["suites"]:
        assert f'href="../../benchmarks/{day}/">{day}</a>' in page
