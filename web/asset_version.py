#!/usr/bin/env python3
"""One source of truth for the `?v=` cache-busting token on every asset URL.

WHY A HASH AND NOT A HAND-PICKED STRING. The token existed as a literal
(`ASSET_V = "20260822b"`) in the generator, and as the same literal typed into
every hand-written page. Changing an asset therefore required remembering to
edit it in two unrelated places, and nothing checked that you had. The first
time it mattered, site.css changed, the token did not, and the browser served
the old stylesheet against the new markup -- which looks exactly like the CSS
edit never worked.

Deriving it from the bytes removes the choice. Change an asset and the token
changes; leave an asset alone and it does not, so pages stay byte-identical
across regenerations.

    python web/asset_version.py            # print the current token
    python web/asset_version.py --stamp    # rewrite every ?v= in docs/ to it
    python web/asset_version.py --check    # exit 1 if any page is stale
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent / "docs"
ASSETS = DOCS / "assets"

# The files a page links with ?v=. Anything not listed here would change without
# busting the cache, so this list is the check's coverage: keep it complete.
TRACKED = ("tw.css", "site.css", "site.js", "tdb-data.js")

_STAMP = re.compile(r'(assets/(?:' + "|".join(re.escape(n) for n in TRACKED) + r'))\?v=[A-Za-z0-9]+')


def current() -> str:
    """A short digest over every tracked asset's bytes."""
    h = hashlib.sha256()
    missing = []
    for name in TRACKED:
        path = ASSETS / name
        if not path.is_file():
            missing.append(name)
            continue
        h.update(name.encode())
        h.update(path.read_bytes())
    if missing:
        # Hashing "the files that happen to exist" would produce a confident
        # token over an incomplete set -- the failure this whole module exists
        # to prevent. Refuse instead.
        raise SystemExit("FATAL: tracked asset(s) missing from docs/assets: "
                         + ", ".join(missing))
    return h.hexdigest()[:10]


def pages() -> list[Path]:
    return sorted(DOCS.rglob("*.html"))


def stale(token: str) -> list[str]:
    out = []
    for page in pages():
        raw = page.read_text(encoding="utf-8", errors="replace")
        for m in _STAMP.finditer(raw):
            if m.group(0) != f"{m.group(1)}?v={token}":
                out.append(f"{page.relative_to(DOCS)}: {m.group(0)} != ?v={token}")
                break
    return out


def stamp(token: str) -> int:
    n = 0
    for page in pages():
        raw = page.read_text(encoding="utf-8", errors="replace")
        new = _STAMP.sub(lambda m: f"{m.group(1)}?v={token}", raw)
        if new != raw:
            page.write_text(new, encoding="utf-8", newline="\n")
            n += 1
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stamp", action="store_true", help="rewrite every ?v= in docs/")
    ap.add_argument("--check", action="store_true", help="exit 1 if any page is stale")
    args = ap.parse_args(argv)

    token = current()
    if args.stamp:
        print(f"asset version {token}: stamped {stamp(token)} page(s)")
        return 0
    if args.check:
        bad = stale(token)
        for line in bad:
            print("FAIL " + line)
        print(f"asset version {token}: {len(pages())} page(s) checked, {len(bad)} stale")
        return 1 if bad else 0
    print(token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
