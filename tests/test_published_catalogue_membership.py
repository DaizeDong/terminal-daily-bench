"""Supplemental membership must agree with dated measurements in both directions."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT))
import verify_site
from tools.make_fixtures import site_insights_fixture


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def make_release(root):
    fixture = site_insights_fixture()
    day = fixture["day"]
    date = day["date"]
    ids = day["matrix"]["tasks"]
    tasks = [dict(t, suite=date, suite_memberships=[{"suite":date}]) for t in fixture["site"]["tasks"]]
    suite = {"id":date,"n_tasks":len(ids),"task_ids":ids,"catalogued_tasks":len(ids),
             "fresh_tasks":0,"carried_tasks":0,"unknown_origin_tasks":len(ids)}
    data = {"tasks":tasks,"suites":[suite]}
    write(root / "registry.json", {"suites":[]})
    write(root / "docs/site_data.json", data)
    write(root / "docs/data/catalogue-additions.json", data)
    write(root / "docs/data/days" / (date + ".json"), day)
    return data, day


def test_published_supplement_is_checked_against_real_roster(tmp_path):
    data, day = make_release(tmp_path)
    assert verify_site.check_suite_membership(tmp_path) == []
    day["matrix"]["tasks"] = day["matrix"]["tasks"][:-1]
    write(tmp_path / "docs/data/days" / (day["date"] + ".json"), day)
    assert any("roster differs" in e for e in verify_site.check_suite_membership(tmp_path))


def test_supplement_cannot_replace_missing_membership_or_missing_day(tmp_path):
    data, day = make_release(tmp_path)
    data["tasks"][0]["suites"] = []
    write(tmp_path / "docs/data/catalogue-additions.json", data)
    assert any("missing reverse membership" in e for e in verify_site.check_suite_membership(tmp_path))
    (tmp_path / "docs/data/days" / (day["date"] + ".json")).unlink()
    assert any("no matching published day" in e for e in verify_site.check_suite_membership(tmp_path))
