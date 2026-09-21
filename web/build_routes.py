#!/usr/bin/env python3
"""Build readable public paths while keeping existing bookmarks available."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = {"registry": "tasks", "benchmarks": "releases", "guide": "docs"}
CANONICAL = re.compile(r'\s*<link\b[^>]*\brel=["\']canonical["\'][^>]*>', re.I)
LINK = re.compile(r'(\bhref=)(["\'])([^"\']*)\2', re.I)


def public_path(path: str) -> str:
    head, sep, rest = path.lstrip("/").partition("/")
    return "/" + PREFIXES.get(head, head) + (sep + rest if sep else "")


def rewrite_links(raw: str, source: str) -> str:
    """Only rewrite HTML links; inline scripts keep their original source text."""
    def section(html: str) -> str:
        def link(match):
            href = match[3]
            if not href or href.startswith(("#", "//")):
                return match[0]
            parsed = urlsplit(href)
            if parsed.scheme or parsed.netloc:
                return match[0]
            resolved = urlsplit(urljoin("/" + source, href))
            new = public_path(resolved.path)
            if new == resolved.path:
                return match[0]
            # Relative paths also work when the site is hosted under a prefix.
            import posixpath
            target = posixpath.relpath(new, posixpath.dirname(public_path(source)))
            if new.endswith("/"):
                target += "/"
            target = urlunsplit(("", "", target, parsed.query, parsed.fragment))
            return match[1] + match[2] + target + match[2]
        return LINK.sub(link, html)
    return "".join(piece if i % 2 else section(piece) for i, piece in enumerate(
        re.split(r'(<script\b[^>]*>.*?</script>)', raw, flags=re.S | re.I)))


def with_canonical(raw: str, source: str, destination: str) -> str:
    import posixpath
    raw = CANONICAL.sub("", raw)
    target = posixpath.relpath(destination.removesuffix("index.html"), posixpath.dirname(source))
    if target == ".":
        target = "./"
    elif not target.endswith("/"):
        target += "/"
    return re.sub(r"\s*</head>", f'\n<link rel="canonical" href="{target}">\n</head>', raw, count=1)


def build(docs: Path) -> int:
    pairs = []
    for old, new in PREFIXES.items():
        source_dir = docs / old
        if not source_dir.is_dir():
            raise ValueError(f"Missing source section: {old}")
        for source in sorted(source_dir.rglob("*")):
            if not source.is_file() or source.suffix not in {".html", ".json"}:
                continue
            relative = source.relative_to(docs).as_posix()
            destination = new + "/" + source.relative_to(source_dir).as_posix()
            target = docs / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix == ".html":
                raw = source.read_text(encoding="utf-8")
                source.write_text(with_canonical(raw, relative, destination), encoding="utf-8", newline="\n")
                result = rewrite_links(CANONICAL.sub("", raw), relative)
                target.write_text(with_canonical(result, destination, destination), encoding="utf-8", newline="\n")
                pairs.append({"legacy": "/" + relative.removesuffix("index.html"),
                              "path": "/" + destination.removesuffix("index.html")})
            else:
                target.write_bytes(source.read_bytes())
    (docs / "data" / "routes.json").write_text(json.dumps({"routes": pairs}, indent=2) + "\n", encoding="utf-8", newline="\n")
    return len(pairs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", type=Path, default=ROOT / "docs")
    args = parser.parse_args()
    print(f"Readable routes: {build(args.docs)} pages; legacy bookmarks retained")
