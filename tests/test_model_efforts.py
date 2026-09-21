"""Execute the shared grouping code against generated synthetic measurements."""
import importlib.util
import json
from pathlib import Path

from test_capability_ranking import _run

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("make_fixtures", ROOT / "tools/make_fixtures.py")
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


def group(rows, preferred="agent-a", inspect_input=False):
    runtime = (ROOT / "docs/assets/tdb-data.js").read_text(encoding="utf-8")
    out = _run("var window = { TDB: T };\n" + runtime + "\n" + """
      var groups = window.TDB.groupModelEfforts(INPUT.rows, INPUT.preferred);
      console.log(JSON.stringify({groups: groups, input: INPUT.rows}));
    """, {"rows": rows, "preferred": preferred})
    return out if inspect_input else out["groups"]


def test_each_model_uses_highest_effort_even_when_lower_effort_scored_better():
    grouped = group(fixtures.effort_rows())
    assert len(grouped) == 3
    a = next(r for r in grouped if r["model"] == "Model A")
    assert (a["effort"], a["solved"], a["n"], a["rate"]) == ("xhigh", 3, 5, 0.6)
    assert len(a["variants"]) == 4
    assert a["agent"] == "agent-a"
    assert next(r for r in grouped if r["model"] == "Model B")["effort"] is None
    assert next(r for r in grouped if r["model"] == "Model C")["effort"] == "medium"


def test_explicit_effort_filter_changes_representative_without_merging_counts():
    rows = [r for r in fixtures.effort_rows() if r["effort"] == "high"]
    grouped = group(rows)
    assert len(grouped) == 1
    assert (grouped[0]["effort"], grouped[0]["solved"], grouped[0]["n"]) == ("high", 7, 10)


def test_grouping_is_order_independent_and_does_not_modify_measurements():
    rows = fixtures.effort_rows()
    original = json.loads(json.dumps(rows))
    assert group(rows) == group(list(reversed(rows)))
    assert group(rows, inspect_input=True)["input"] == original
