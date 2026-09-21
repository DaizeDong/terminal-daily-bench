#!/usr/bin/env python3
"""Build shared styles, detail pages, search data, and readable public routes."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"
FEATURE_CSS = ("tdb-insights.css", "tdb-releases.css", "tdb-tools.css")
MARKER = re.compile(r"\n/\* BEGIN GENERATED FEATURE STYLES \*/.*?/\* END GENERATED FEATURE STYLES \*/\n?", re.S)


def bundle_styles() -> None:
    path = ASSETS / "site.css"
    main = MARKER.sub("", path.read_text(encoding="utf-8")).rstrip()
    feature = []
    for name in FEATURE_CSS:
        source = ASSETS / name
        if source.exists():
            feature.append(f"/* {name} */\n" + source.read_text(encoding="utf-8").strip())
    if feature:
        main += "\n\n/* BEGIN GENERATED FEATURE STYLES */\n" + "\n\n".join(feature) + "\n/* END GENERATED FEATURE STYLES */"
    path.write_text(main + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--styles-only", action="store_true")
    args = parser.parse_args()
    bundle_styles()
    if args.styles_only:
        print("Shared styles bundled")
        return 0
    for script in ("gen_pages.py", "gen_docs_index.py", "build_routes.py"):
        subprocess.run([sys.executable, str(ROOT / "web" / script)], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "web" / "asset_version.py"), "--stamp"], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
