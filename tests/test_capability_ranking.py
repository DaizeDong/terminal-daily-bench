"""The per-capability ranking on /leaderboard/, checked by RUNNING it.

Every other frontend fixture in this directory reads the page as text. That is
the right tool for "is this claim still published" and the wrong one for the
three things this view can get wrong, because all three are arithmetic:

  * a null counted as a zero -- the difference between "this model was never
    run on the two tasks carrying C8" and "this model solved neither of them";
  * an axis with no task quietly dropped -- which reads as an axis that does
    not exist rather than one nothing measures;
  * a rate printed without the denominator it was computed from -- 100% off
    one task, indistinguishable from 100% off fifty.

A substring test cannot tell any of those apart, so this file EXECUTES the
shipped functions. Nothing here reimplements them: `_runtime()` lifts the
capability renderers out of docs/leaderboard/index.html, `esc` out of
tdb-data.js and `wilson`/`pct` out of site.js, by matching braces from each
`function NAME(` -- so a mutation anywhere inside any of those bodies changes
what these assertions see. The only code this file contributes is a loader and
the fixtures.

Node is the interpreter. Where it is absent the executed half skips and says
so, and the static half below still runs -- a file that can only skip is a file
that protects nothing.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from tools.make_fixtures import repeat_score_fixture

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
LEADERBOARD = (DOCS / "leaderboard" / "index.html").read_text(encoding="utf-8")
DATA_RUNTIME = (DOCS / "assets" / "tdb-data.js").read_text(encoding="utf-8")
SHELL = (DOCS / "assets" / "site.js").read_text(encoding="utf-8")
CAPABILITY = json.loads((DOCS / "data" / "capability.json").read_text(encoding="utf-8"))
BOARD = json.loads((DOCS / "leaderboard_data.json").read_text(encoding="utf-8"))
SITE = json.loads((DOCS / "site_data.json").read_text(encoding="utf-8"))

NODE = shutil.which("node")

# Lifted from the page, in the order they have to be declared.
PAGE_FUNCS = (
    "hasOwn", "pointEstimate", "axisTally", "resolution", "overallPoint",
    "capabilityAxes", "capabilityRows", "provenanceWord", "capCell",
    "axisNoteHtml", "capabilityColors", "capColorStyle", "capHeatCell",
    "capColumns", "rankCell", "capabilitySummary", "buildCapability",
)


def _extract(source: str, name: str) -> str:
    """Return the whole text of `function name(...) { ... }`.

    Braces are matched rather than lines counted: a body containing a `}` in a
    string literal or a nested closure would defeat any regex that stopped at
    the first one, and every function here contains both.
    """
    start = source.find("function " + name + "(")
    assert start >= 0, f"{name}() is not defined in the source it was expected in"
    i = source.index("{", start)
    depth = 0
    while i < len(source):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
        i += 1
    raise AssertionError(f"{name}() is not brace-balanced")


def _runtime() -> str:
    """The shipped capability renderers, ready to run under Node."""
    parts = [
        "'use strict';",
        _extract(DATA_RUNTIME, "esc"),
        _extract(SHELL, "wilson"),
        _extract(SHELL, "pct"),
        "var T = { wilson: wilson, pct: pct };",
        _extract(DATA_RUNTIME, "modelLabel"),
        _extract(DATA_RUNTIME, "agentLabel"),
        "T.modelLabel = modelLabel; T.agentLabel = agentLabel;",
    ]
    for name in ("repeatStats", "resultStats", "scoreEstimate", "scoreCell"):
        parts.append(_extract(DATA_RUNTIME, name))
        parts.append(f"T.{name} = {name};")
    # OVERALL_AXIS is a declaration, not a function, and capCell's overall call
    # site reads it -- so it is lifted by name too rather than restated here.
    m = re.search(r"var OVERALL_AXIS = \{[^}]*\};", LEADERBOARD)
    assert m, "OVERALL_AXIS is no longer declared on the leaderboard page"
    parts.extend(_extract(LEADERBOARD, name) for name in PAGE_FUNCS)
    parts.append(m.group(0))
    return "\n".join(parts)


def _run(script: str, payload: dict) -> dict:
    """Run `script` against `payload`, both under the shipped runtime."""
    if not NODE:
        pytest.skip("node is not installed: the executed half of this file "
                    "cannot run, so it reports nothing rather than passing")
    src = (_runtime() + "\nvar INPUT = " + json.dumps(payload) + ";\n"
           + script + "\n")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "probe.js"
        path.write_text(src, encoding="utf-8")
        proc = subprocess.run([NODE, str(path)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, (
        "the shipped capability renderers threw under Node:\n" + proc.stderr)
    return json.loads(proc.stdout)


# --------------------------------------------------------------------------
# A synthetic grid, so the null case is present at all.
#
# The published matrix has no nulls today, which means the real data cannot
# demonstrate the failure this file most needs to catch. A fixture can: model
# "never-ran" has null on every task carrying axis AX, and 0 on every task
# carrying axis BX. If the two come out the same, `|| 0` is back.
# --------------------------------------------------------------------------
SYNTH_BOARD = {
    "date": "2026-01-01",
    "n_models": 2,
    "pooled": {"claude-code": {}},
    "matrix": {
        "scaffold": "claude-code",
        "tasks": ["t1", "t2", "t3", "t4", "t5", "t6", "t7"],
        "rows": [
            {"model": "never-ran", "g": [None, None, 0, 0, 0, 0, 0]},
            {"model": "solved-all", "g": [1, 1, 1, 1, 1, 1, 1]},
        ],
    },
}
SYNTH_CAP = {
    "publish_gate": {"min_tasks": 5},
    "axes": [
        {"code": "AX", "name": "nulled", "task_ids": ["t1", "t2"]},
        {"code": "BX", "name": "zeroed", "task_ids": ["t3", "t4"]},
        {"code": "CX", "name": "empty", "task_ids": []},
        {"code": "DX", "name": "wide",
         "task_ids": ["t1", "t2", "t3", "t4", "t5", "t6", "t7"]},
    ],
}


def test_a_null_cell_is_not_a_zero_solve():
    """An unmeasured cell leaves BOTH counters alone and prints no number.

    The two axes below differ only in whether the model's cells are null or 0.
    A denominator that counts nulls makes them identical -- 0/2 either way --
    and the em dash the null case has to render becomes a confident 0%.
    """
    out = _run("""
      var cap = buildCapability(INPUT.board, INPUT.cap, null);
      var byCode = {};
      cap.axes.forEach(function (a) { byCode[a.code] = a; });
      var row = null;
      cap.rows.forEach(function (r) { if (r.model === "never-ran") { row = r; } });
      console.log(JSON.stringify({
        nulled: row.axis.AX,
        zeroed: row.axis.BX,
        overall: row.overall,
        nulledCell: capCell(row.axis.AX, byCode.AX),
        zeroedCell: capCell(row.axis.BX, byCode.BX),
        rank: rankCell(row)
      }));
    """, {"board": SYNTH_BOARD, "cap": SYNTH_CAP})

    # The whole point: two nulls are not two failures.
    assert out["nulled"] == {"solved": 0, "n": 0}, (
        "a null cell entered the denominator: two never-run tasks were "
        "counted as two tasks this model failed")
    assert out["zeroed"] == {"solved": 0, "n": 2}
    assert out["nulled"] != out["zeroed"], (
        "unmeasured and unsolved render identically")

    # And it reaches the screen as an em dash with no number of any kind.
    assert out["nulledCell"] == '<span class="text-muted-foreground">&mdash;</span>'
    assert "%" not in out["nulledCell"] and "0/" not in out["nulledCell"]
    # while the genuine zero keeps its measurement.
    assert "2 tasks" in out["zeroedCell"] and ">0%<" in out["zeroedCell"]
    assert "tdb-acc-sd" not in out["zeroedCell"]

    # The overall column drops the two nulls from its denominator too, rather
    # than scoring the model out of 7.
    assert out["overall"] == {"solved": 0, "n": 5}


def test_an_axis_with_no_task_is_listed_named_and_at_zero():
    """A zero-task axis survives the join, the columns and the header.

    Three places could drop it -- a `.filter` in capabilityAxes, a skipped
    push in capColumns, or a header that renders nothing -- so all three are
    asserted against the catalogue's own axis list.
    """
    out = _run("""
      var cap = buildCapability(INPUT.board, INPUT.cap, INPUT.site);
      console.log(JSON.stringify({
        codes: cap.axes.map(function (a) { return a.code; }),
        empty: cap.axes.filter(function (a) { return a.n === 0; })
                 .map(function (a) { return { code: a.code, name: a.name,
                                              n: a.n, ranked: a.ranked }; }),
        colKeys: cap.cols.map(function (c) { return c.key; }),
        notes: cap.axes.map(function (a) { return axisNoteHtml(a); }),
        empties: cap.summary.empty
      }));
    """, {"board": BOARD, "cap": CAPABILITY, "site": SITE})

    published = [a["code"] for a in CAPABILITY["axes"]]
    assert out["codes"] == published, (
        "the capability view does not carry every published axis: "
        f"{sorted(set(published) - set(out['codes']))} were dropped")

    # The fixture is only meaningful while the catalogue actually has some.
    assert out["empty"], (
        "no axis in the published catalogue is empty, so this test proves "
        "nothing -- rewrite it against a fixture that has one")
    for axis in out["empty"]:
        assert axis["name"], f"{axis['code']} is listed without its name"
        assert axis["ranked"] is False
    assert out["empties"] == len(out["empty"])

    # One column per axis, plus rank / model / overall.
    for code in published:
        assert "cap:" + code in out["colKeys"], (
            f"axis {code} has no column: it exists in the data and not in "
            "the table, which is the failure this view exists to avoid")
    assert len(out["colKeys"]) == len(published) + 3

    # And the head SAYS zero rather than leaving the column blank.
    #
    # An axis's task set is the UNION of the catalogue's two lists: the labels
    # the generator re-derived from a package's own oracle patch (`task_ids`)
    # and the ones a live package only declares in its task.toml, which the
    # generator cannot re-derive because the patch is withheld
    # (`declared_unverified.task_ids`). This loop used to read `task_ids`
    # alone, which was the same set only while the board was archive tasks. On
    # a live board it is nearly empty -- 9 of 342 columns join through it on
    # 2026-09-10 -- so every axis looked empty here and the assertion demanded
    # "no task" from column heads that carry hundreds. What the assertion is
    # for is unchanged: an axis nothing measures must say so rather than
    # render blank. Only the definition of "nothing measures it" follows the
    # join the view actually performs.
    for axis, note in zip(CAPABILITY["axes"], out["notes"]):
        joined = set(axis["task_ids"]) | set(
            (axis.get("declared_unverified") or {}).get("task_ids") or [])
        if not [t for t in joined if t in BOARD["matrix"]["tasks"]]:
            assert note == "no task", (
                f"{axis['code']} carries no task and its column head does not "
                f"say so: {note!r}")


def test_no_rate_is_ever_rendered_without_its_denominator():
    """Every percentage on the grid is accompanied by its measured task count.

    Checked over the whole published grid -- 12 models by 14 axes plus the
    overall column -- rather than one sampled cell, and the counts are matched
    against the tally the same cell was computed from, so a denominator
    rendered from a different field than the numerator is a failure here.
    """
    out = _run("""
      var cap = buildCapability(INPUT.board, INPUT.cap, INPUT.site);
      var cells = [];
      cap.rows.forEach(function (r) {
        cells.push({ code: "overall", model: r.model, t: r.overall,
                     html: capCell(r.overall, OVERALL_AXIS), ranked: true });
        cap.axes.forEach(function (a) {
          cells.push({ code: a.code, model: r.model, t: r.axis[a.code],
                       html: capCell(r.axis[a.code], a), ranked: a.ranked });
        });
      });
      console.log(JSON.stringify(cells));
    """, {"board": BOARD, "cap": CAPABILITY, "site": SITE})

    assert len(out) == len(BOARD["matrix"]["rows"]) * (len(CAPABILITY["axes"]) + 1)
    rated = 0
    for cell in out:
        html, tally = cell["html"], cell["t"]
        counts = "{} tasks".format(tally["n"])
        if "%" in html:
            rated += 1
            assert 'class="tdb-cap-n"' in html, (
                f"{cell['model']} / {cell['code']}: a rate with no denominator "
                f"element: {html}")
            assert counts in html, (
                f"{cell['model']} / {cell['code']}: the rate is drawn from a "
                f"different count than the one printed: {html} vs {counts}")
            assert tally["n"] > 0
        elif tally["n"]:
            assert counts in html, (
                f"{cell['model']} / {cell['code']}: a measured cell shows "
                f"neither a rate nor its counts: {html}")
        else:
            assert html == '<span class="text-muted-foreground">&mdash;</span>'
    assert rated, "no cell on the published grid printed a rate at all"


def test_small_samples_show_observed_accuracy_without_becoming_rankable():
    """The refusal is the mechanism, and the floor comes from the file.

    An axis under `publish_gate.min_tasks` shows its observed percentage and
    denominator with a small-sample label, but cannot be used to rank models.
    And a catalogue that publishes NO floor leaves every axis unranked, rather
    than falling back to a floor invented on the page.
    """
    out = _run("""
      var withGate = buildCapability(INPUT.board, INPUT.cap, INPUT.site);
      var bare = JSON.parse(JSON.stringify(INPUT.cap));
      delete bare.publish_gate;
      var noGate = buildCapability(INPUT.board, bare, INPUT.site);
      var small = [];
      withGate.axes.forEach(function (a) {
        if (a.n > 0 && !a.ranked) {
          small.push({ code: a.code, n: a.n, note: axisNoteHtml(a),
                       cell: capCell(withGate.rows[0].axis[a.code], a) });
        }
      });
      console.log(JSON.stringify({
        floor: withGate.floor,
        small: small,
        staticKeys: withGate.cols.filter(function (c) { return c.static; })
                      .map(function (c) { return c.key; }),
        sortValues: withGate.cols.filter(function (c) { return c.static; })
                      .map(function (c) { return c.value(withGate.rows[0]); }),
        noGateRanked: noGate.axes.filter(function (a) { return a.ranked; }).length,
        noGateFloor: noGate.floor
      }));
    """, {"board": BOARD, "cap": CAPABILITY, "site": SITE})

    assert out["floor"] == CAPABILITY["publish_gate"]["min_tasks"], (
        "the ranking floor is not the catalogue's published one")
    assert out["small"], (
        "no published axis falls below the floor, so this test proves "
        "nothing about the refusal it is here to check")
    for axis in out["small"]:
        assert axis["n"] < out["floor"]
        assert "%" in axis["cell"] and "small sample" in axis["cell"], (
            f"{axis['code']} carries {axis['n']} tasks and still prints a "
            f"rate without its small-sample label: {axis['cell']}")
        assert f'{axis["n"]} tasks' in axis["cell"], (
            f"{axis['code']} prints neither a rate nor its counts")
        assert "unranked" in axis["note"], (
            f"{axis['code']} is unranked and its column head does not say so: "
            f"{axis['note']!r}")
        assert "cap:" + axis["code"] in out["staticKeys"], (
            f"{axis['code']} cannot be ranked and its header is still a "
            "sort control -- the refusal is decorative")
    # A static column sorts as blank in both directions, so even a stale
    # ?sort= arriving in the URL cannot order the table by it.
    assert out["sortValues"] and all(v is None for v in out["sortValues"])

    assert out["noGateFloor"] is None
    assert out["noGateRanked"] == 0, (
        "a catalogue with no published floor still ranked "
        f"{out['noGateRanked']} axes -- the fallback is the bug")


def test_the_view_explains_scope_without_internal_field_names():
    """The rendered explanation uses its own counts and distinguishes missing evidence."""
    script = _extract(LEADERBOARD, "splitScaffold") + "\n"
    script += _extract(LEADERBOARD, "capFootHtml") + "\n"
    script += """
      var CAP = buildCapability(INPUT.board, INPUT.cap, null);
      console.log(JSON.stringify({html: capFootHtml(INPUT.board)}));
    """
    out = _run(script, {"board": SYNTH_BOARD, "cap": SYNTH_CAP})
    text = out["html"]
    assert "2 models and 7 tasks" in text
    assert "at least 5" in text.lower()
    assert "settings may differ from the overall view" in text
    assert "Unlabeled tasks do not imply missing skills" in text
    assert "not been independently checked" in text
    assert "Missing results are left out" in text
    assert "more than half its runs succeed" in text
    assert "Run range" not in text
    assert "standard deviation" not in text and "±" not in text
    assert "95%" not in text and "Wilson" not in text
    assert 'href="../guide/quality-methods/"' in text
    for internal in ("capability_profile()", "graded gate states", "score_accepted"):
        assert internal not in text


def test_the_capability_view_reuses_the_leaderboard_table():
    """One table, two views -- not a second component.

    The finding this site has been rebuilt around twice is that it had no way
    to state a fact except by adding a surface. A ranking belongs on the
    leaderboard, so this asserts the view renders into the SAME #head/#body
    the overall table uses and that no second <table> was introduced.
    """
    assert LEADERBOARD.count("<table data-slot=\"table\"") == 1, (
        "the leaderboard page grew a second table")
    assert 'key: "capability"' in LEADERBOARD
    assert 'closest("button[data-view]")' in LEADERBOARD
    assert "renderCap" in LEADERBOARD and "capMode()" in LEADERBOARD
    # The switch reads the same row/cell helpers as the overall view.
    for shared in ("function cell(", "function headHtml(", "function sortRows("):
        assert shared in LEADERBOARD
    # And the capability foot replaces the overall foot rather than stacking
    # under it, so the page never shows two scope statements at once.
    assert "byId(\"foot\").innerHTML = capFootHtml(day);" in LEADERBOARD


def test_capability_heat_colors_keep_rates_counts_and_small_samples_distinct():
    out = _run("""
      var cap = buildCapability(INPUT.board, INPUT.cap, null);
      var colors = capabilityColors(cap.rows, cap.axes);
      var row = cap.rows.find(function(r) { return r.model === 'never-ran'; });
      var axes = Object.fromEntries(cap.axes.map(function(a) { return [a.code, a]; }));
      console.log(JSON.stringify({colors:colors,
        missing:capHeatCell(row.axis.AX, axes.AX, colors, 'rate'),
        zero:capHeatCell(row.axis.DX, axes.DX, colors, 'rate'),
        peers:capHeatCell(row.axis.DX, axes.DX, colors, 'peers'),
        small:capHeatCell(row.axis.BX, axes.BX, colors, 'peers'),
        high:capHeatCell(cap.rows[0].axis.DX, axes.DX, colors, 'peers')}));
    """, {"board": SYNTH_BOARD, "cap": SYNTH_CAP})
    # 0/5 and 7/7 have a mean model accuracy of 50%, not pooled 7/12.
    assert out["colors"]["columns"]["DX"] == {"mean": 0.5, "models": 2}
    assert out["colors"]["columns"]["AX"] == {"mean": 1, "models": 1}
    assert out["colors"]["columns"]["CX"] == {"mean": None, "models": 0}
    assert out["colors"]["span"] == 0.5
    assert 'data-state="missing"' in out["missing"]
    assert 'data-rate=' not in out["missing"] and "&mdash;" in out["missing"]
    for mode in ("zero", "peers"):
        assert 'data-rate="0"' in out[mode] and 'data-n="5"' in out[mode]
        assert "5 evaluated tasks" in out[mode]
        assert '<strong>0%</strong>' in out[mode]
        assert "Run range" not in out[mode] and "standard deviation" not in out[mode]
        assert "95%" not in out[mode] and "tdb-cap-range-value" not in out[mode]
        assert "NaN" not in out[mode]
    assert "-50.0 percentage points below" in out["peers"]
    assert "+50.0 percentage points above" in out["high"]
    assert "Color scale: -50 to +50 percentage points" in out["peers"]
    assert "statistical significance" in out["peers"]
    assert 'data-state="small"' in out["small"] and 'data-ranked="false"' in out["small"]
    assert "2 evaluated tasks" in out["small"] and '<strong>0%</strong>' in out["small"]
    assert "at least 5 evaluated tasks" in out["small"]
    assert "style=" not in out["small"]


def test_legacy_scores_show_observed_rate_without_invented_variation():
    """A score without repeat records has no measured SD, including endpoints."""
    out = _run("""
      var cap = buildCapability(INPUT.board, INPUT.cap, null);
      var zero = cap.rows.find(function(r) { return r.model === 'never-ran'; });
      var full = cap.rows.find(function(r) { return r.model === 'solved-all'; });
      console.log(JSON.stringify({
        zero:T.scoreCell(zero.overall.solved, zero.overall.n),
        full:T.scoreCell(full.overall.solved, full.overall.n),
        small:T.scoreCell(zero.axis.BX.solved, zero.axis.BX.n),
        missing:T.scoreCell(zero.axis.AX.solved, zero.axis.AX.n)
      }));
    """, {"board": SYNTH_BOARD, "cap": SYNTH_CAP})
    for key, expected in {
        "zero": "0%",
        "full": "100%",
        "small": "0%",
    }.items():
        visible = re.search(r'<strong class="tabular-nums">([^<]+)</strong>', out[key])
        assert visible and visible.group(1) == expected, out[key]
        assert 'class="tdb-acc-track"' in out[key]
        assert "run variation unavailable" in out[key]
        assert "95%" not in out[key] and "tdb-acc-sd" not in out[key]
        assert 'class="tdb-acc-range"' not in out[key]
    assert "&mdash;" in out["missing"]
    assert "tdb-acc-ci" not in out["missing"] and "%" not in out["missing"]


def test_capability_heat_relative_colors_require_more_than_one_measured_model():
    out = _run("""
      var board = JSON.parse(JSON.stringify(INPUT.board));
      board.matrix.rows = board.matrix.rows.filter(function(r) { return r.model === 'solved-all'; });
      var cap = buildCapability(board, INPUT.cap, null);
      var axis = cap.axes.find(function(a) { return a.code === 'DX'; });
      var colors = capabilityColors(cap.rows, cap.axes);
      console.log(JSON.stringify({html:capHeatCell(cap.rows[0].axis.DX, axis, colors, 'peers')}));
    """, {"board": SYNTH_BOARD, "cap": SYNTH_CAP})
    assert 'data-state="uncompared"' in out["html"]
    assert '<strong>100%</strong>' in out["html"] and "7 evaluated tasks" in out["html"]
    assert "At least two measured models" in out["html"]
    assert "style=" not in out["html"]


def test_capability_keeps_majority_and_subset_sd_but_only_score_bars_show_uncertainty():
    sample = repeat_score_fixture()
    out = _run("""
      var cap = buildCapability(INPUT.day, INPUT.cap, null);
      var axes = Object.fromEntries(cap.axes.map(a => [a.code, a]));
      var colors = capabilityColors(cap.rows, cap.axes);
      console.log(JSON.stringify(cap.rows.map(r => ({model:r.model, overall:r.overall,
        subset:r.axis.C2, missing:r.axis.C9,
        overallHtml:capCell(r.overall, OVERALL_AXIS),
        subsetBar:capCell(r.axis.C2, axes.C2),
        subsetHtml:capHeatCell(r.axis.C2, axes.C2, colors, 'rate'),
        missingHtml:capHeatCell(r.axis.C9, axes.C9, colors, 'rate')}))));
    """, sample)
    a, b = out
    assert [a["model"], b["model"]] == ["model-a", "model-b"]
    assert a["overall"]["solved"] == 2
    assert a["overall"]["repeat"]["min"] == pytest.approx(1 / 3)
    assert a["overall"]["repeat"]["max"] == 1
    assert a["overall"]["repeat"]["sd"] == pytest.approx(1 / 3)
    assert a["subset"]["repeat"]["trialRates"] == [.5, 1., 0.]
    assert a["subset"]["repeat"]["min"] == 0
    assert a["subset"]["repeat"]["max"] == 1
    assert a["subset"]["repeat"]["sd"] == .5
    assert '<span class="tdb-acc-sd">± 50%</span>' in a["subsetBar"]
    assert b["overall"]["solved"] == 0
    assert b["overall"]["repeat"]["mean"] == pytest.approx(1 / 3)
    assert b["overall"]["repeat"]["min"] == b["overall"]["repeat"]["max"] == 1 / 3
    assert '<strong class="tabular-nums">0%</strong>' in b["overallHtml"]
    assert '<span class="tdb-acc-sd">± 0%</span>' in b["overallHtml"]
    assert 'data-rate="0"' in b["subsetHtml"]
    assert '<strong>0%</strong>' in b["subsetHtml"]
    for item in out:
        assert item["overall"]["n"] == 3 and item["subset"]["n"] == 2
        assert item["overall"]["repeat"]["runs"] == 3
        assert "3 tasks" in item["overallHtml"] and "2 evaluated tasks" in item["subsetHtml"]
        assert "tdb-acc-sd" in item["overallHtml"]
        assert "95%" not in item["overallHtml"] + item["subsetHtml"]
        assert item["overallHtml"].count("±") == 1
        assert "tdb-acc-range-value" not in item["overallHtml"]
        assert "±" not in item["subsetHtml"]
        assert "standard deviation" not in item["subsetHtml"] and "Run range" not in item["subsetHtml"]
        assert "tdb-cap-sd" not in item["subsetHtml"] and "tdb-cap-range-value" not in item["subsetHtml"]
        assert 'data-state="missing"' in item["missingHtml"]
        assert "tdb-cap-range-value" not in item["missingHtml"]


def test_capability_and_overall_ranks_follow_majority_despite_reversed_repeat_means():
    sample = repeat_score_fixture("rank")
    out = _run("""
      var cap = buildCapability(INPUT.day, INPUT.cap, null);
      var score = cap.cols.find(c => c.key === 'cap:C4');
      console.log(JSON.stringify(cap.rows.map(r => ({model:r.model, rank:r.rank,
        overall:overallPoint(r), capability:score.value(r), solved:r.overall.solved}))));
    """, sample)
    assert [row["model"] for row in out] == ["model-b", "model-a"]
    assert [row["solved"] for row in out] == [2, 1]
    assert [row["rank"] for row in out] == [1, 2]
    assert [row["overall"] for row in out] == pytest.approx([2 / 3, 1 / 3])
    assert [row["capability"] for row in out] == pytest.approx([2 / 3, 1 / 3])


def test_majority_ties_remain_tied_despite_different_repeat_means_and_sd():
    out = _run("""
      var cap = buildCapability(INPUT.day, INPUT.cap, null);
      var score = cap.cols.find(c => c.key === 'cap:C4');
      console.log(JSON.stringify(cap.rows.map(r => ({model:r.model, rank:r.rank,
        overall:overallPoint(r), capability:score.value(r), repeat:r.overall.repeat}))));
    """, repeat_score_fixture("tie"))
    assert [row["rank"] for row in out] == [1, 1]
    assert [row["overall"] for row in out] == pytest.approx([1 / 3, 1 / 3])
    assert [row["capability"] for row in out] == pytest.approx([1 / 3, 1 / 3])
    by_model = {row["model"]: row for row in out}
    assert by_model["model-a"]["repeat"]["mean"] > by_model["model-b"]["repeat"]["mean"]
    assert by_model["model-a"]["repeat"]["sd"] > by_model["model-b"]["repeat"]["sd"]


def test_capability_heat_uses_majority_and_never_displays_repeat_uncertainty():
    out = _run("""
      var cap = buildCapability(INPUT.day, INPUT.cap, null);
      var colors = capabilityColors(cap.rows, cap.axes);
      var axis = cap.axes.find(a => a.code === 'C4');
      console.log(JSON.stringify({colors:colors.columns.C4,
        rows:cap.rows.map(r => ({model:r.model,
          rate:capHeatCell(r.axis.C4, axis, colors, 'rate'),
          peers:capHeatCell(r.axis.C4, axis, colors, 'peers')}))}));
    """, repeat_score_fixture("outside"))
    assert out["colors"] == {"mean": .5, "models": 2}
    for row, center in zip(out["rows"], (1, 0)):
        for html in (row["rate"], row["peers"]):
            assert f'data-rate="{center}"' in html
            assert f'<strong>{center * 100}%</strong>' in html
            assert "tdb-cap-range-value" not in html and "tdb-cap-sd" not in html
            assert "Run range" not in html and "standard deviation" not in html
            assert "±" not in html and "95%" not in html


def test_small_repeated_capability_keeps_variation_but_cannot_be_sorted():
    sample = repeat_score_fixture()
    sample["cap"]["publish_gate"]["min_tasks"] = 3
    out = _run("""
      var cap = buildCapability(INPUT.day, INPUT.cap, null);
      var axis = cap.axes.find(a => a.code === 'C2');
      var col = cap.cols.find(c => c.key === 'cap:C2');
      console.log(JSON.stringify({static:col.static, value:col.value(cap.rows[0]),
        cell:capCell(cap.rows[0].axis.C2, axis)}));
    """, sample)
    assert out["static"] is True and out["value"] is None
    assert "small sample" in out["cell"] and "2 tasks" in out["cell"]
    assert '<span class="tdb-acc-sd">± 50%</span>' in out["cell"]
    assert '<strong class="tabular-nums">50%</strong>' in out["cell"]


def test_capability_trial_count_mismatch_never_invents_sd():
    sample = repeat_score_fixture()
    sample["day"]["aggregation"]["trials_per_cell"] = 4
    out = _run("""
      var cap = buildCapability(INPUT.day, INPUT.cap, null);
      console.log(JSON.stringify(cap.rows.map(r => ({overall:r.overall,
        html:capCell(r.overall, OVERALL_AXIS)}))));
    """, sample)
    for row in out:
        assert "repeat" not in row["overall"]
        assert "tdb-acc-sd" not in row["html"] and "tdb-acc-range" not in row["html"]


def test_capability_url_restores_axis_color_sort_and_clears_absent_state():
    functions = "\n".join(_extract(LEADERBOARD, name) for name in ("capMode", "colByKey", "readUrl", "writeUrl"))
    out = _run(functions + """
      var MODE_DEFAULT='overall', MODE='overall', CAP=true, COLS=[{key:'rank'}];
      var SORT_KEY_DEFAULT='rank', SORT_DIR_DEFAULT='asc', sortKey='rank', sortDir='asc';
      var capAxis='all', capColor='rate', GROUPS=['agent','effort'], facet={};
      var search={value:''}; function byId(id){return id==='q'?search:null;}
      var window={URL:URL,location:{href:'https://example.com/leaderboard/?day=2020-01-01&view=capability&cap=C5&capColor=peers&sort=cap:C5&dir=desc&q=Model#results'},
        history:{state:null,replaceState:function(state,title,url){window.location.href=String(url);}}};
      readUrl(); writeUrl(search.value);
      var restored={mode:MODE,axis:capAxis,color:capColor,sort:sortKey,dir:sortDir,q:search.value,url:window.location.href};
      window.location.href='https://example.com/leaderboard/?day=2020-01-02&view=capability';
      readUrl();
      var cleared={mode:MODE,axis:capAxis,color:capColor,sort:sortKey,dir:sortDir,q:search.value};
      window.location.href='https://example.com/leaderboard/?day=2020-01-02';
      readUrl();
      console.log(JSON.stringify({restored:restored,cleared:cleared,overall:MODE}));
    """, {})
    assert out["restored"] | {"url": ""} == {
        "mode": "capability", "axis": "C5", "color": "peers", "sort": "cap:C5", "dir": "desc", "q": "Model", "url": ""}
    assert "day=2020-01-01" in out["restored"]["url"]
    assert "color=peers" in out["restored"]["url"] and out["restored"]["url"].endswith("#results")
    assert "capColor=" not in out["restored"]["url"]
    assert out["cleared"] == {"mode": "capability", "axis": "all", "color": "rate", "sort": "rank", "dir": "asc", "q": ""}
    assert out["overall"] == "overall"
