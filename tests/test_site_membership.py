"""Regression tests for the public site's many-to-many suite catalogue."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import gen_pages  # noqa: E402
import gen_site_data  # noqa: E402
import verify_site  # noqa: E402


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")


def test_site_catalogue_retains_timestamp_only_for_identical_payload():
    old = {
        "generated": "2026-08-06T12:00:00Z",
        "scoring": {"official_ranking": False},
        "suites": [],
        "tasks": [],
    }
    same = dict(old, generated="2026-08-06T12:10:00Z")
    kept = gen_site_data.retain_generated_timestamp(old, same)
    assert kept["generated"] == "2026-08-06T12:00:00Z"
    assert same["generated"] == "2026-08-06T12:10:00Z"

    changed = dict(same, tasks=[{"id": "td-new"}])
    refreshed = gen_site_data.retain_generated_timestamp(old, changed)
    assert refreshed["generated"] == "2026-08-06T12:10:00Z"


def _package(release: Path, split: str, tid: str, pr: int) -> None:
    package = release / "tasks" / split / tid
    package.mkdir(parents=True, exist_ok=True)
    _write_json(package / "record.json", {
        "repo": "example/project",
        "pr_number": pr,
        "language": "python",
        "fail_to_pass": [f"tests/test_{pr}.py::test_regression"],
    })
    _write_json(package / "PROVENANCE.json", {
        "source_repo": "example/project",
        "source_license_spdx": "MIT",
    })
    (package / "instruction.md").write_text(
        f"# Repair regression {pr}\n\nMake the protected test pass.\n",
        encoding="utf-8",
    )


def _member(tid: str, mode: str, origin: str) -> dict:
    return {
        "task": tid,
        "mode": mode,
        "suite_window": {
            "origin": origin,
            "certified_date": "2026-08-05" if origin == "carried" else "2026-08-06",
            "age_days": 1 if origin == "carried" else 0,
            "source_ledger": f"history/{tid}/accepted.json",
        },
    }


def _daily_release(tmp_path: Path) -> tuple[Path, dict]:
    release = tmp_path / "release"
    _package(release, "archive", "td-shared", 1)
    _package(release, "archive", "td-old", 2)
    _package(release, "live", "td-new", 3)
    _write_json(release / "registry.json", {
        "suites": [
            {
                "id": "2026-08-05", "status": "archive", "n_tasks": 2,
                "fresh_tasks": 2, "carried_tasks": 0, "unknown_origin_tasks": 0,
            },
            {
                "id": "2026-08-06", "status": "live", "n_tasks": 2,
                "fresh_tasks": 1, "carried_tasks": 1, "unknown_origin_tasks": 0,
            },
        ]
    })
    _write_json(release / "tasks" / ".suite-2026-08-05.json", [
        _member("td-shared", "archive", "fresh"),
        _member("td-old", "archive", "fresh"),
    ])
    _write_json(release / "tasks" / ".suite-2026-08-06.json", [
        _member("td-shared", "archive", "carried"),
        _member("td-new", "live", "fresh"),
    ])
    data = gen_site_data.collect(release, {})
    _write_json(release / "docs" / "site_data.json", data)
    return release, data


def test_carried_task_keeps_both_suites_and_newest_target(tmp_path):
    release, data = _daily_release(tmp_path)
    tasks = {row["id"]: row for row in data["tasks"]}
    suites = {row["id"]: row for row in data["suites"]}

    shared = tasks["td-shared"]
    assert shared["suites"] == ["2026-08-05", "2026-08-06"]
    assert shared["suite"] == "2026-08-06"
    assert {
        row["suite"]: row["origin"] for row in shared["suite_memberships"]
    } == {"2026-08-05": "fresh", "2026-08-06": "carried"}

    assert suites["2026-08-05"]["task_ids"] == ["td-old", "td-shared"]
    assert suites["2026-08-06"]["task_ids"] == ["td-new", "td-shared"]
    assert suites["2026-08-06"]["catalogued_tasks"] == 2
    assert suites["2026-08-06"]["fresh_tasks"] == 1
    assert suites["2026-08-06"]["carried_tasks"] == 1
    assert suites["2026-08-06"]["unknown_origin_tasks"] == 0

    indexed = gen_pages.index_tasks_by_suite(data["tasks"])
    assert {task["id"] for task in indexed["2026-08-05"]} == {
        "td-old", "td-shared"
    }
    assert {task["id"] for task in indexed["2026-08-06"]} == {
        "td-new", "td-shared"
    }
    assert verify_site.check_suite_membership(release) == []


def test_archive_live_sample_copy_merges_fallback_memberships(tmp_path):
    release = tmp_path / "release"
    _package(release, "archive", "td-sample", 7)
    _package(release, "live", "td-sample", 7)
    _write_json(release / "registry.json", {"suites": [
        {
            "id": "sample", "status": "archive", "n_tasks": 1,
            "path": "tasks/archive",
        },
        {
            "id": "sample-live", "status": "live", "n_tasks": 1,
            "path": "tasks/live",
        },
    ]})

    data = gen_site_data.collect(release, {})
    _write_json(release / "docs" / "site_data.json", data)

    assert len(data["tasks"]) == 1
    task = data["tasks"][0]
    assert task["suites"] == ["sample", "sample-live"]
    assert task["suite"] == "sample-live"
    assert task["status"] == "archive"
    assert task["also_in"] == ["live"]
    assert [row["suite"] for row in task["suite_memberships"]] == [
        "sample", "sample-live"
    ]
    assert {
        row["id"]: row["task_ids"] for row in data["suites"]
    } == {"sample": ["td-sample"], "sample-live": ["td-sample"]}
    assert verify_site.check_suite_membership(release) == []


def _formal_relative_report(
    roster_n: int = 50,
    *,
    publishable: bool = True,
    task_ids: list[str] | None = None,
) -> dict:
    task_ids = task_ids or [f"td-formal-{number:02d}" for number in range(roster_n)]
    return {
        "schema_version": "td-relative-capability-v3",
        "input": {
            "frozen_task_roster_n": roster_n,
            "frozen_task_roster_sha256": "1" * 64,
            "frozen_task_id_roster_sha256": (
                gen_site_data._task_id_roster_sha256(task_ids)
            ),
            "task_roster_digest_trusted": True,
            "cell_manifest_sha256": "2" * 64,
            "cell_manifest_digest_trusted": True,
        },
        "axes": [{
            "axis": "overall",
            "entities": {
                "model": {
                    "ratings": [{
                        "name": "model-a",
                        "relative_score": 12.0,
                        "ci": [8.0, 16.0],
                        "publishable": publishable,
                    }]
                }
            },
        }],
    }


def _bound_publication(report: dict, matrix: dict) -> dict:
    tasks = matrix["tasks"]
    return {
        "relative_capability": report,
        "matrix": matrix,
        "publication_authority": {
            "schema_version": "td-relative-publication-bundle-v1",
            "relative_report_sha256": gen_site_data.canonical_sha256(report),
            "matrix_sha256": gen_site_data.canonical_sha256(matrix),
            "matrix_task_id_roster_sha256": (
                gen_site_data._task_id_roster_sha256(tasks)
            ),
        },
    }


def _approve_publication(monkeypatch, board: dict) -> None:
    authority_sha256 = gen_site_data.canonical_sha256(
        board["publication_authority"]
    )
    monkeypatch.setattr(
        gen_site_data,
        "APPROVED_PUBLICATION_BUNDLE_SHA256S",
        frozenset({authority_sha256}),
    )
    monkeypatch.setattr(gen_site_data, "ANTI_CHEAT_DEPLOYMENT_ACTIVE", True)


def test_legacy_matrix_cannot_mint_task_scores_or_difficulty(tmp_path):
    release = tmp_path / "release"
    _package(release, "archive", "td-legacy", 9)
    _write_json(release / "registry.json", {"suites": [{
        "id": "sample", "status": "archive", "n_tasks": 1,
        "path": "tasks/archive",
    }]})
    board = {
        "date": "2026-07-23",
        "n_models": 1,
        "leaderboard": [{"model": "legacy-model"}],
        "matrix": {
            "tasks": ["td-legacy"],
            "rows": [{"model": "legacy-model", "g": [0]}],
        },
    }

    data = gen_site_data.collect(release, board)
    task = data["tasks"][0]

    assert data["scoring"]["official_ranking"] is False
    assert data["scoring"]["legacy_snapshot_present"] is True
    assert data["scoring"]["state"] == "awaiting-certified-50-task-results"
    assert task["solved_by"] is None
    assert task["n_models"] is None
    assert task["difficulty"] == ""


def test_code_approved_v3_report_can_bind_exact_matrix(tmp_path, monkeypatch):
    release = tmp_path / "release"
    _package(release, "archive", "td-formal-00", 10)
    _write_json(release / "registry.json", {"suites": [{
        "id": "formal", "status": "archive", "n_tasks": 1,
        "path": "tasks/archive",
    }]})
    tasks = [f"td-formal-{number:02d}" for number in range(50)]
    matrix = {
        "tasks": tasks,
        "rows": [
            {"model": "model-a", "g": [1] + [0] * 49},
            {"model": "model-b", "g": [0] * 50},
        ],
    }
    board = _bound_publication(
        _formal_relative_report(task_ids=tasks), matrix
    )
    _approve_publication(monkeypatch, board)

    data = gen_site_data.collect(release, board)
    task = data["tasks"][0]

    assert data["scoring"]["official_ranking"] is True
    assert data["scoring"]["matrix_published"] is True
    assert data["scoring"]["formal_roster_n"] == 50
    assert task["solved_by"] == 1
    assert task["n_models"] == 2
    assert task["difficulty"] == "medium"


@pytest.mark.parametrize("mutation", ["swapped_tasks", "arbitrary_outcomes"])
def test_bound_report_rejects_swapped_or_arbitrary_unbound_matrix(
    tmp_path, monkeypatch, mutation
):
    release = tmp_path / "release"
    _package(release, "archive", "td-formal-00", 10)
    _write_json(release / "registry.json", {"suites": [{
        "id": "formal", "status": "archive", "n_tasks": 1,
        "path": "tasks/archive",
    }]})
    tasks = [f"td-formal-{number:02d}" for number in range(50)]
    matrix = {
        "tasks": tasks,
        "rows": [
            {"model": "model-a", "g": [1] + [0] * 49},
            {"model": "model-b", "g": [0] * 50},
        ],
    }
    board = _bound_publication(
        _formal_relative_report(task_ids=tasks), matrix
    )
    _approve_publication(monkeypatch, board)
    if mutation == "swapped_tasks":
        board["matrix"]["tasks"][0], board["matrix"]["tasks"][1] = (
            board["matrix"]["tasks"][1],
            board["matrix"]["tasks"][0],
        )
    else:
        board["matrix"]["rows"][0]["g"][0] = 0

    data = gen_site_data.collect(release, board)
    task = data["tasks"][0]

    # The report artifact remains code-approved, but the changed matrix no
    # longer matches its canonical pin and therefore cannot mint task scores.
    assert data["scoring"]["official_ranking"] is True
    assert data["scoring"]["matrix_published"] is False
    assert data["scoring"]["matrix_digest_matches"] is False
    assert task["solved_by"] is None
    assert task["n_models"] is None
    assert task["difficulty"] == ""


def test_self_signed_report_and_matrix_cannot_approve_themselves(tmp_path):
    release = tmp_path / "release"
    _package(release, "archive", "td-formal-00", 10)
    _write_json(release / "registry.json", {"suites": [{
        "id": "formal", "status": "archive", "n_tasks": 1,
        "path": "tasks/archive",
    }]})
    tasks = [f"td-formal-{number:02d}" for number in range(50)]
    matrix = {
        "tasks": tasks,
        "rows": [{"model": "model-a", "g": [1] + [0] * 49}],
    }
    board = _bound_publication(
        _formal_relative_report(task_ids=tasks), matrix
    )

    data = gen_site_data.collect(release, board)
    task = data["tasks"][0]

    assert data["scoring"]["publication_registry_mode"] == (
        "code-controlled-allowlist"
    )
    assert data["scoring"]["publication_bundle_approved"] is False
    assert data["scoring"]["anti_cheat_deployment_active"] is False
    assert data["scoring"]["official_ranking"] is False
    assert data["scoring"]["matrix_published"] is False
    assert task["solved_by"] is None


@pytest.mark.parametrize(
    "report",
    [
        _formal_relative_report(49),
        _formal_relative_report(50, publishable=False),
        {
            **_formal_relative_report(),
            "input": {
                **_formal_relative_report()["input"],
                "cell_manifest_digest_trusted": False,
            },
        },
    ],
)
def test_incomplete_or_untrusted_v3_report_stays_unranked(report):
    status = gen_site_data.scoring_status({"relative_capability": report})

    assert status["official_ranking"] is False
    assert status["state"] == "unranked-incomplete-or-untrusted"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("registry_count", "registry suite '2026-08-06': n_tasks=3"),
        ("site_task_ids", "site_data suite '2026-08-06': task_ids do not match"),
        ("origin_count", "site_data suite '2026-08-06': carried_tasks=0"),
        ("reverse_edge", "site_data task 'td-shared': suites do not match"),
        ("primary_drift", "primary suite '2026-08-05' drifted from '2026-08-06'"),
    ],
)
def test_membership_gate_rejects_count_origin_and_target_drift(
    tmp_path, mutation, message
):
    release, _ = _daily_release(tmp_path)
    registry_path = release / "registry.json"
    site_path = release / "docs" / "site_data.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    site = json.loads(site_path.read_text(encoding="utf-8"))
    suites = {row["id"]: row for row in site["suites"]}
    tasks = {row["id"]: row for row in site["tasks"]}

    if mutation == "registry_count":
        next(row for row in registry["suites"] if row["id"] == "2026-08-06")[
            "n_tasks"
        ] = 3
        _write_json(registry_path, registry)
    elif mutation == "site_task_ids":
        suites["2026-08-06"]["task_ids"] = ["td-new"]
        suites["2026-08-06"]["catalogued_tasks"] = 1
        _write_json(site_path, site)
    elif mutation == "origin_count":
        suites["2026-08-06"]["carried_tasks"] = 0
        _write_json(site_path, site)
    elif mutation == "reverse_edge":
        tasks["td-shared"]["suites"] = ["2026-08-05"]
        _write_json(site_path, site)
    elif mutation == "primary_drift":
        tasks["td-shared"]["suite"] = "2026-08-05"
        _write_json(site_path, site)

    errors = verify_site.check_suite_membership(release)
    assert any(message in error for error in errors), errors


def test_generated_detail_pages_are_idempotent_and_include_all_suites(
    tmp_path, monkeypatch, capsys
):
    release, data = _daily_release(tmp_path)
    docs = release / "docs"
    monkeypatch.setattr(gen_pages, "RELEASE", release)
    monkeypatch.setattr(gen_pages, "TASKS", release / "tasks")

    assert gen_pages.main(["--docs", str(docs)]) == 0
    first = {
        path.relative_to(docs): path.read_bytes()
        for path in sorted(docs.rglob("*.html"))
    }
    capsys.readouterr()
    assert gen_pages.main(["--docs", str(docs)]) == 0
    second_output = capsys.readouterr().out
    second = {
        path.relative_to(docs): path.read_bytes()
        for path in sorted(docs.rglob("*.html"))
    }

    assert first == second
    assert "0 updated, 5 unchanged" in second_output
    for sid in ("2026-08-05", "2026-08-06"):
        suite_page = (docs / "benchmarks" / sid / "index.html").read_text(
            encoding="utf-8"
        )
        assert "td-shared" in suite_page
    task_page = (docs / "registry" / "td-shared" / "index.html").read_text(
        encoding="utf-8"
    )
    # "Suite <id>", capitalised: the label is English and the id is not, and
    # gen_pages emits both halves. The id stays lowercase and is what this
    # assertion is really about -- a task page must name every suite it is in.
    assert "Suite 2026-08-05" in task_page
    assert "Suite 2026-08-06" in task_page
    assert len(data["tasks"]) == 3


def test_public_indexes_use_shared_many_to_many_helper():
    """Suite membership is many-to-many, so no page may hand-roll the test.

    This used to name the three pages that filtered tasks by suite, home among
    them. The home page was rebuilt to lead with the leaderboard and no longer
    lists tasks at all, so naming it asserted a layout rather than the rule.
    The rule is that the shared helpers exist, are actually used, and that
    nowhere reaches past them into the raw field -- which binds every page,
    including ones that do not exist yet.
    """
    shell = (ROOT / "docs" / "assets" / "site.js").read_text(encoding="utf-8")
    suites = (ROOT / "docs" / "benchmarks" / "index.html").read_text(
        encoding="utf-8"
    )
    registry = (ROOT / "docs" / "registry" / "index.html").read_text(
        encoding="utf-8"
    )

    assert "function taskSuites(task)" in shell
    assert "function taskInSuite(task, suiteId)" in shell
    assert "T.taskInSuite(task, suite.id)" in suites
    assert "T.taskSuites(t)" in registry

    # A page that filters by suite must go through the helper. `task.suite` is
    # the legacy single-valued field: reading it directly is how a task that
    # belongs to several suites silently disappears from all but one of them.
    for page in sorted((ROOT / "docs").rglob("*.html")):
        source = page.read_text(encoding="utf-8", errors="replace")
        assert ".suite ===" not in source, (
            f"{page.relative_to(ROOT)} hand-rolls suite membership")
