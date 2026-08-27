#!/usr/bin/env python3
"""Build docs/guide/search-index.json -- what the Ctrl+K modal searches.

The site has no server, so search has to be a file. This walks the shipped
guide pages and emits one record per addressable SECTION, because a section is
what a reader can actually be sent to: every `<h2 id>`/`<h3 id>` inside the
page's `<article class="prose">` already carries a stable id (the "on this
page" rail is built from those same ids at runtime), so `<page>#<id>` is a
link that exists rather than one this generator invents.

    gen_docs_index.py [--docs DIR] [--out DIR/guide/search-index.json]

Reads:
    <docs>/guide/*/index.html      the four guide pages (NOT guide/index.html,
                                   which is a table of contents for them)

Emits:
    { generated, pages, entries: [{url, page, heading, id, level, text}] }

``url`` is relative to the SITE ROOT, not to this file, so site.js can resolve
it as ROOT + "/" + url from any depth. ``text`` is the prose that follows the
heading up to the next one, flattened and trimmed to a preview: it is what
makes a query match a section whose title does not contain the word.

Nothing here is authored. Rename a heading and its record moves with it; the
index cannot claim a section the page does not have, and it cannot silently
keep one the page dropped -- which is the failure mode of a hand-written list.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import html
import json
import re
from pathlib import Path

# The prose column. Everything outside it is shell, breadcrumb and footer --
# chrome that is identical on all four pages and would therefore match every
# query equally, which is the same as matching nothing.
_ARTICLE = re.compile(r'<article[^>]*\bclass="[^"]*\bprose\b[^"]*"[^>]*>(.*?)</article>', re.S)
_H1 = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.S | re.I)
_HEADING = re.compile(r"<h([23])\b([^>]*)>(.*?)</h\1\s*>", re.S | re.I)
_ID_ATTR = re.compile(r'\bid="([^"]+)"')
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_PRE = re.compile(r"<pre\b[^>]*>.*?</pre>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")

SNIPPET_CHARS = 220


def _text(fragment: str) -> str:
    """Visible text of an HTML fragment, entities resolved, spaces collapsed."""
    return " ".join(html.unescape(_TAG.sub(" ", fragment)).split())


def _snippet(fragment: str) -> str:
    """The section's prose preview.

    Code blocks are dropped FIRST and only put back when a section is nothing
    but code: a preview that opens with `schema_version = "1.1"` tells a reader
    less about the section than the two sentences underneath it, but a section
    with no sentences at all is better previewed by its command than by "".
    """
    prose = _text(_PRE.sub(" ", fragment))
    body = prose or _text(fragment)
    if len(body) <= SNIPPET_CHARS:
        return body
    cut = body[:SNIPPET_CHARS]
    space = cut.rfind(" ")
    if space > SNIPPET_CHARS // 2:
        cut = cut[:space]
    return cut.rstrip(" ,;:.") + "\u2026"


def collect_page(page: Path, docs: Path) -> tuple[str, str, list[dict]]:
    """Return (url, page title, section records) for one guide page."""
    raw = _COMMENT.sub(" ", page.read_text(encoding="utf-8", errors="replace"))
    url = page.parent.relative_to(docs).as_posix() + "/"
    h1 = _H1.search(raw)
    title = _text(h1.group(1)) if h1 else url.strip("/").rsplit("/", 1)[-1]

    article = _ARTICLE.search(raw)
    if not article:
        return url, title, []
    body = article.group(1)

    heads = list(_HEADING.finditer(body))
    rows: list[dict] = []
    for i, m in enumerate(heads):
        attrs = _ID_ATTR.search(m.group(2))
        heading = _text(m.group(3))
        if not attrs or not heading:
            # No id means no link target; an entry that cannot be navigated to
            # is worse than a missing one, because it looks like a dead result.
            continue
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        rows.append({
            "url": url,
            "page": title,
            "heading": heading,
            "id": attrs.group(1),
            "level": int(m.group(1)),
            "text": _snippet(body[m.end():end]),
        })
    return url, title, rows


def collect(docs: Path) -> dict:
    pages: list[dict] = []
    entries: list[dict] = []
    for page in sorted((docs / "guide").glob("*/index.html")):
        url, title, rows = collect_page(page, docs)
        pages.append({"url": url, "title": title, "n_sections": len(rows)})
        entries.extend(rows)
    return {
        "generated": datetime.datetime.now(datetime.timezone.utc)
                             .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": "td-docs-search-index-v1",
        "pages": pages,
        "entries": entries,
    }


def canonical_sha256(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


_UTC_SECOND = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def retain_generated_timestamp(existing, candidate: dict) -> dict:
    """Keep the build timestamp when the emitted index is byte-stable.

    Same contract as gen_site_data.py: ``generated`` is publication metadata,
    not content, so re-running over unchanged pages must not change the file.
    Without this every site build rewrites the index and a no-op build is
    indistinguishable from a real one in a diff.
    """
    if not isinstance(candidate, dict):
        raise TypeError("candidate index must be a dict")
    result = dict(candidate)
    if not isinstance(existing, dict):
        return result
    stamp = existing.get("generated")
    if not isinstance(stamp, str) or not _UTC_SECOND.fullmatch(stamp):
        return result
    old = {k: v for k, v in existing.items() if k != "generated"}
    new = {k: v for k, v in result.items() if k != "generated"}
    if canonical_sha256(old) == canonical_sha256(new):
        result["generated"] = stamp
    return result


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- a missing/odd file just means no reuse
        return {}


def main() -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default=str(here.parent / "docs"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    docs = Path(a.docs)
    out = Path(a.out) if a.out else docs / "guide" / "search-index.json"
    data = retain_generated_timestamp(_read_json(out), collect(docs))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"docs search index: {len(data['pages'])} guide pages, "
          f"{len(data['entries'])} sections -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
