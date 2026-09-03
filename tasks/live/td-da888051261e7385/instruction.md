# fix: render content-tree (page-tree) macro as nested page links

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## What

Adds a handler for the **Content Tree** / **Page Tree** macro (`content-tree`, legacy `pagetree`, and the related `children` / Children Display macro). It resolves the tree's child pages from the API and emits a nested Markdown bullet list of page links.

## Why

The macro renders as an empty JavaScript placeholder in `body.view`, so it was silently dropped during export. Pages that use it as a navigation index exported with an empty body (only the title). See [redacted-ref].

## How

- New `convert_pagetree` handler, dispatched from `convert_div` by `data-macro-name` (`content-tree`, `pagetree`, `children`) and by CSS class (`content-tree`, `plugin_pagetree`) as a fallback for when the rendered placeholder lacks `data-macro-name`.
- Macro parameters are read from the storage-format XML (`editor2` / `body_storage`), matched by `macro-id` (mirroring the existing `include` macro handling). The `root` value is taken from its nested `ri:page` `ri:content-title` attribute, which is how Confluence actually stores it (verified against a live page), with a fallback to element text for other variants.
- Root resolution: `@self` / empty -> current page; `@home` -> space homepage; a page title -> best-effort CQL lookup. The lookup honors the root reference's `ri:space-key` (so a root in another space resolves correctly), falls back to the current space when absent, escapes backslashes/quotes, and requires an exact title match so a fuzzy CQL hit cannot resolve to the wrong page.
- Depth: `depth` (Children Display) is preferred, then `startDepth` (Page Tree, which maps to the same "Tree depth" UI field on the instances observed). The `children` macro defaults to direct children only unless `all=true` or an explicit depth is set; Content Tree / Page Tree default to the full subtree.
- The tree is built from `Page.descendants`, nested via each node's ancestor chain and limited to the configured depth. Children are ordered by title (Confluence's manual "position" order is not available via the CQL descendants query). Descendants with a missing id are skipped so one malformed node cannot abort the page.
- Links reuse the existing `convert_page_link` helper, so wiki/relative href modes and title disambiguation are handled consistently.

## Tests

New `tests/unit/test_pagetree_conversion.py` covering: nested rendering, depth limiting, `@self` / `@home` roots, missing homepage, unresolvable title root, empty subtree, dispatch via `convert_div`, plain-text vs. `ri:content-title` root, cross-space root resolution, exact-title rejection, the `children` default/`all`/`depth` behavior, the unmatched-`macro-id` warning, and the zero-id descendant guard. Full suite passes (457 tests); lint and format clean.

## Notes

- Verified end-to-end against a live Confluence page: the previously empty page now renders its 15 child pages as links.
- The exact rendered markup (`data-macro-name` vs. CSS class) can vary between Confluence Cloud and Server/DC; detection covers both.

[redacted-ref].

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
