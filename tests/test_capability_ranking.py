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
    "capabilityAxes", "capabilityRows", "capCell", "axisNoteHtml",
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
    ]
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
        proc = subprocess.run([NODE, str(path)], capture_output=True, text=True)
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
    assert "0/2" in out["zeroedCell"]

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
    for axis, note in zip(CAPABILITY["axes"], out["notes"]):
        if not [t for t in axis["task_ids"] if t in BOARD["matrix"]["tasks"]]:
            assert note == "no task", (
                f"{axis['code']} carries no task and its column head does not "
                f"say so: {note!r}")


def test_no_rate_is_ever_rendered_without_its_denominator():
    """Every percentage on the grid is accompanied by its solved/n.

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
        counts = "{}/{}".format(tally["solved"], tally["n"])
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


def test_an_axis_below_the_published_floor_is_never_ranked():
    """The refusal is the mechanism, and the floor comes from the file.

    Two halves. An axis under `publish_gate.min_tasks` prints counts and no
    percentage, and its column is static so the table cannot be ordered by it.
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
        assert "%" not in axis["cell"], (
            f"{axis['code']} carries {axis['n']} tasks and still prints a "
            f"rate: {axis['cell']}")
        assert "/" in axis["cell"], (
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


def test_the_view_states_its_scope_and_its_two_missing_measurements():
    """The three sentences that make the numbers readable are on the page.

    Static on purpose: these are claims, not arithmetic. Each one exists
    because a reader who does not have it will draw a wrong conclusion from a
    correct number -- that the axis columns split the ranking, that the 22
    unlabelled tasks have no capability, or that four conditional angles the
    code can compute were measured and withheld.
    """
    foot = LEADERBOARD[LEADERBOARD.index("function capFootHtml"):]
    foot = foot[:foot.index("\n  function show(")] if "\n  function show(" in foot else foot

    assert "reproduce the overall ranking rather than" in foot, (
        "the page no longer says the carrier axes restate the overall ranking")
    assert "oracle patch" in foot and "tagger" in foot, (
        "the page no longer says WHY most tasks carry no capability label")
    assert "capability_profile()" in foot, (
        "the page no longer names the four-angle decomposition it cannot run")
    assert "graded gate states" in foot and "1, 0 or null" in foot, (
        "the page no longer says WHY the four conditional angles cannot be "
        "computed: they need graded states and the matrix ships three values")
    # The scope warning is the capability view's own, not the main table's.
    assert "different measurements" in foot and "cannot be read against" in foot

    # None of the counts in those sentences is typed: each is interpolated
    # from the join, so regenerating either input file updates the sentence
    # instead of falsifying it.
    for typed in ("28 of 50", "27 and 28", "seven axes", "12 models under"):
        assert typed not in foot, (
            f"{typed!r} is written into the page as a literal; it must be "
            "computed, or it outlives the day it describes")


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
