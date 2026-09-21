"""Supplemental task labels must remain declared, including after rebuilds."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT))
from gen_capability_data import merge_declared_metadata, axis_rows
from tools.make_fixtures import site_insights_fixture, site_capability_metadata_fixture


def test_supplement_stays_unverified_and_does_not_replace_packages():
    fixture = site_insights_fixture()
    axis = fixture["cap"]["axes"][0]
    first, second = axis["task_ids"]
    original = {"id": first, "declared": [], "verifiable": True}
    tasks = {first: original.copy()}
    assert merge_declared_metadata(tasks, {first: [axis["code"]], second: [axis["code"]]}) == 1
    assert tasks[first] == original
    assert tasks[second]["verifiable"] is False
    rows = axis_rows([], [tasks[second]])
    result = next(row for row in rows if row["code"] == axis["code"])
    assert result["n_tasks"] == 0
    assert result["declared_unverified"]["task_ids"] == [second]
    assert result["gate_verdict"] != "pass"
    assert merge_declared_metadata(tasks, {second: [axis["code"]]}) == 0


@pytest.mark.parametrize("labels", site_capability_metadata_fixture()["invalid_labels"])
def test_malformed_supplement_refused(labels):
    with pytest.raises(ValueError):
        merge_declared_metadata({}, labels)
