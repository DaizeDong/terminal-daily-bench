"""Readable routes preserve bookmarks, project prefixes, and query state."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT))
from build_routes import build
from tools.make_fixtures import site_routes_fixture


def test_route_generation_preserves_sources_and_is_repeatable(tmp_path):
    fixture = site_routes_fixture()
    (tmp_path / "data").mkdir()
    for case in fixture["cases"]:
        path = tmp_path / case["path"]
        path.parent.mkdir()
        path.write_text("<head></head><body>" + case["html"] + "</body>", encoding="utf-8")
    assert build(tmp_path) == len(fixture["cases"])
    first = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert build(tmp_path) == len(fixture["cases"])
    second = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert first == second
    for case in fixture["cases"]:
        original = (tmp_path / case["path"]).read_text(encoding="utf-8")
        canonical = (tmp_path / case["expected_path"]).read_text(encoding="utf-8")
        assert case["html"] in original
        assert 'rel="canonical" href="./"' in canonical
        assert f'data-page="{case["path"].split("/")[0]}"' in canonical
        assert 'href="../registry/"' not in canonical
        assert 'href="../guide/"' not in canonical


def test_runtime_routes_keep_prefix_and_normalize_query_aliases():
    fixture = site_routes_fixture()
    script = r"""
      const fs=require('fs'), vm=require('vm'), fixture=JSON.parse(process.argv[1]);
      const document={baseURI:fixture.base+'leaderboard/',currentScript:{getAttribute:k=>k==='data-root'?'..':'leaderboard'},
        readyState:'loading',addEventListener:()=>{},querySelectorAll:()=>[],
        documentElement:{classList:{add:()=>{},remove:()=>{}},style:{},setAttribute:()=>{}}};
      const context={URL,document,window:{}};
      vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
      const T=context.window.TDB;
      const result=fixture.query_cases.map(x=>T.canonicalUrl(x.url).href);
      const links=fixture.cases.map(x=>T.routeUrl(x.path));
      process.stdout.write(JSON.stringify({result,links,external:T.canonicalUrl('https://outside.example/registry/?q=x').href}));
    """
    result = subprocess.run(["node", "-e", script, json.dumps(fixture), str(ROOT / "docs/assets/site.js")],
                            capture_output=True, text=True, encoding="utf-8", check=True)
    data = json.loads(result.stdout)
    assert data["result"] == [row["expected"] for row in fixture["query_cases"]]
    assert data["links"] == [fixture["base"] + row["expected_name"] + "/" for row in fixture["cases"]]
    assert data["external"] == "https://outside.example/registry/?q=x"
