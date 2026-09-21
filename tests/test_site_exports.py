"""Export guards preserve numeric meaning, sample scope and bounded artifacts."""
from __future__ import annotations
import csv
import importlib.util
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
spec = importlib.util.spec_from_file_location("export_fixtures", ROOT / "tools/make_fixtures.py")
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


@pytest.fixture
def sample():
    return fixtures.site_export_fixture()


def run_js(script, payload):
    if not NODE:
        pytest.skip("Node is required to execute the shipped export runtime")
    source = r"""
      const fs=require('fs'), vm=require('vm');
      const INPUT=JSON.parse(fs.readFileSync(0,'utf8'));
      const box={URL,console,location:{href:INPUT.url || 'https://example.com/leaderboard/'}};
      vm.createContext(box);vm.runInContext(fs.readFileSync(RUNTIME,'utf8'),box);
      const T=box.TDB;
      const original=JSON.stringify(INPUT);
      function freeze(x){if(x&&typeof x==='object'){Object.values(x).forEach(freeze);Object.freeze(x);}}freeze(INPUT);
    """.replace("RUNTIME", json.dumps(str(ROOT / "docs/assets/tdb-share.js")))
    result = subprocess.run([NODE, "-e", source + script + "\nif(JSON.stringify(INPUT)!==original)throw Error('Input mutated');"],
                            input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def svg_text(svg):
    document = ET.fromstring(svg)
    return document, " ".join(document.itertext())


def test_csv_escapes_formulas_without_turning_numeric_negative_percent_into_text(sample):
    result = run_js("console.log(JSON.stringify(T.resultsCSV(INPUT.snapshot)));", sample)
    rows = list(csv.reader(io.StringIO(result.lstrip("\ufeff"))))
    header = rows.index(["Model", "Success rate", "Tasks"])
    values = rows[header + 1:]
    assert [row[0] for row in values[:-1]] == ["'" + text for text in sample["prefixes"]]
    assert values[0][1] == "-25.0%"
    assert values[-1][1] == ""
    assert values[-1][2] == "0"


def test_svg_limits_long_text_rows_and_dimensions_while_csv_remains_complete(sample):
    sample["snapshot"]["rows"] *= 20
    output = run_js("console.log(JSON.stringify({svg:T.resultsSVG(INPUT.snapshot),csv:T.resultsCSV(INPUT.snapshot)}));", sample)
    document, text = svg_text(output["svg"])
    assert int(document.attrib["height"]) <= 4096
    assert int(document.attrib["width"]) <= 2400
    assert len(output["svg"]) < 100_000
    assert "Long text shortened" in text
    assert "CSV includes every selected result" in text
    assert sample["snapshot"]["rows"][-1]["model"] in output["csv"]


@pytest.mark.parametrize("metric", ["commands", "tools", "cost"])
def test_efficiency_image_preserves_active_measurement_and_both_sample_counts(sample, metric):
    sample["efficiency"]["metric"] = metric
    sample["efficiency"]["title"] = "Efficiency: " + metric + " per attempt"
    result = run_js("console.log(JSON.stringify(T.resultsSVG(INPUT.efficiency)));", sample)
    _, text = svg_text(result)
    normalized = text.lower()
    assert {"commands": "mean commands / attempt", "tools": "mean tool calls / attempt", "cost": "mean cost / attempt (usd)"}[metric] in normalized
    assert "success rate" in normalized
    assert "95%" not in normalized and "confidence" not in normalized
    assert "measured attempts" in normalized
    assert "measured tasks" in normalized
    assert {"commands": "40.0%", "tools": "50.0%", "cost": "75.0%"}[metric] in text
    value = {"commands": "40.0% \u00b1 10.0%", "tools": "50.0% \u00b1 20.0%", "cost": "75.0% \u00b1 30.0%"}[metric]
    document = ET.fromstring(result)
    assert any(node.text == value for node in document.iter("{http://www.w3.org/2000/svg}text"))
    assert "3 recorded runs" in text


def test_svg_preserves_zero_sd_and_keeps_missing_variation_unavailable(sample):
    sample["profile"]["rows"][0]["rate_sd"] = 0
    svg = run_js("console.log(JSON.stringify(T.resultsSVG(INPUT.profile)));", sample)
    _, text = svg_text(svg)
    assert "50.0% \u00b1 0.0%" in text
    sample["profile"]["rows"][0]["rate_sd"] = None
    sample["profile"]["rows"][0]["rate_runs"] = None
    svg = run_js("console.log(JSON.stringify(T.resultsSVG(INPUT.profile)));", sample)
    _, text = svg_text(svg)
    assert "50.0%" in text
    assert "\u00b1" not in text


def test_csv_exports_majority_accuracy_and_run_sd_as_separate_numeric_columns(sample):
    csv_text = run_js("console.log(JSON.stringify(T.resultsCSV(INPUT.profile)));", sample)
    rows = list(csv.reader(io.StringIO(csv_text.lstrip("\ufeff"))))
    headers = [column["label"] for column in sample["profile"]["columns"]]
    row = rows[rows.index(headers) + 1]
    values = {column["key"]: value for column, value in zip(sample["profile"]["columns"], row)}
    assert values["rate"] == "50.0%"
    assert (values["rate_sd"], values["rate_runs"]) == ("10.0%", "3")
    assert not any(key.endswith(("_min", "_max")) for key in values)


def test_svg_centers_zero_sd_on_majority_instead_of_round_mean(sample):
    result = run_js("console.log(JSON.stringify(T.resultsSVG(INPUT.outside_range_profile)));", sample)
    document, text = svg_text(result)
    svg_ns = "{http://www.w3.org/2000/svg}"
    tracks = [node for node in document.iter(svg_ns + "rect") if node.get("fill") == "#eef2f8"]
    centers = [node for node in document.iter(svg_ns + "rect") if node.get("fill") == "#315aba"]
    ranges = [node for node in document.iter(svg_ns + "path") if node.get("stroke") == "#15223b"]
    assert len(tracks) == len(centers) == len(ranges) == 2
    for track, center, interval, majority in zip(tracks, centers, ranges, (1, 0)):
        x, span = float(track.get("x")), float(track.get("width"))
        assert float(center.get("width")) / span == majority
        match = re.match(r"M([\d.]+) [\d.]+H([\d.]+)", interval.get("d"))
        assert match is not None
        assert (float(match[1]) - x) / span == pytest.approx(majority)
        assert float(match[1]) == float(match[2])
    assert "100.0% \u00b1 0.0%" in text
    assert "0.0% \u00b1 0.0%" in text


def test_capability_svg_omits_uncertainty_but_keeps_scores_and_task_counts(sample):
    output = run_js("console.log(JSON.stringify({svg:T.resultsSVG(INPUT.capability),csv:T.resultsCSV(INPUT.capability)}));", sample)
    document, text = svg_text(output["svg"])
    assert "50.0%" in text and "N=4" in text and "preliminary" in text
    assert "\u00b1" not in text and "standard deviation" not in text
    assert not any(node.get("stroke") == "#15223b" for node in document.iter("{http://www.w3.org/2000/svg}path"))
    rows = list(csv.reader(io.StringIO(output["csv"].lstrip("\ufeff"))))
    columns = sample["capability"]["columns"]
    header = rows.index([column["label"] for column in columns])
    values = {column["key"]: value for column, value in zip(columns, rows[header + 1])}
    assert values["overall_sd"] == values["cap:C1_sd"] == "10.0%"
    assert values["overall_runs"] == values["cap:C1_runs"] == "3"


def test_profile_image_keeps_peer_pairs_preliminary_and_negative_gap(sample):
    result = run_js("console.log(JSON.stringify(T.resultsSVG(INPUT.profile)));", sample)
    _, text = svg_text(result)
    assert "Peer Pairs" in text
    assert "Preliminary" in text
    assert "-25.0%" in text
    assert "Google Sans Code" in result


def test_explicit_image_columns_follow_snapshot_contract(sample):
    sample["snapshot"]["imageColumns"] = ["n", "rate"]
    result = run_js("console.log(JSON.stringify(T.resultsSVG(INPUT.snapshot)));", sample)
    _, text = svg_text(result)
    assert text.index("Tasks") < text.index("Success rate")
    assert "=Synthetic formula" not in text


@pytest.mark.parametrize("keys", [["rate_sd", "rate_runs"], ["model", "rate_sd"], ["rate_runs", "rate_sd"]])
def test_explicit_image_columns_preserve_requested_sd_metadata(sample, keys):
    sample["profile"]["imageColumns"] = keys
    result = run_js("console.log(JSON.stringify(T.resultsSVG(INPUT.profile)));", sample)
    document, text = svg_text(result)
    labels = {column["key"]: column["label"] for column in sample["profile"]["columns"]}
    nodes = [node.text for node in document.iter("{http://www.w3.org/2000/svg}text")]
    assert all(labels[key] in nodes for key in keys)
    assert nodes.index(labels[keys[0]]) < nodes.index(labels[keys[1]])
    assert all(labels[key] not in nodes for key in labels if key not in keys)
    assert "50.0% \u00b1 10.0%" not in text


@pytest.mark.parametrize("dimensions", [(1200, 2000), (2400, 4096), (1200, 100_000)])
def test_raster_allocation_caps_pixels_and_sides(sample, dimensions):
    sample["dimensions"] = dimensions
    result = run_js("console.log(JSON.stringify(T.resultsRasterSize(...INPUT.dimensions)));", sample)
    assert result["width"] <= 8192 and result["height"] <= 8192
    assert result["width"] * result["height"] <= 20_000_000
    if dimensions == (1200, 2000):
        assert result == {"width": 2400, "height": 4000}


def test_share_with_null_snapshot_preserves_current_requested_date(sample):
    sample["url"] = "https://example.com/leaderboard/?date=2020-01-01&view=compare"
    result = run_js("console.log(JSON.stringify([T.resultsShareUrl(null),T.resultsShareUrl(INPUT.snapshot)]));", sample)
    assert all("date=2020-01-01" in url for url in result)


def test_share_adds_known_date_only_when_current_url_does_not_have_one(sample):
    sample["url"] = "https://example.com/leaderboard/?view=compare&compare=model-a&compare=model-b&audit=1#tasks"
    result = run_js("console.log(JSON.stringify(T.resultsShareUrl(INPUT.snapshot)));", sample)
    assert "date=2020-01-02" in result
    assert "compare=model-a&compare=model-b" in result
    assert "audit=" not in result
    assert result.endswith("#tasks")
