# fix: export page properties report nested in third-party app macros

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

[redacted-ref].

A Page Properties Report that exports correctly on its own produced **no table at all** once it was nested inside a third-party Connect app macro such as StiltSoft Table Filter — silently, with no warning.

Confluence does not server-render the body of a Connect `dynamicContentMacros` app macro into `body.view`. It emits only an empty placeholder plus an iframe bootstrap script:

```html
<div class="ap-container conf-macro output-block"
     data-macro-name="table-filter" data-macro-id="..." data-hasbody="true">
  <div class="ap-content"> </div>
  <script class="ap-iframe-body-script">...</script>
</div>
```

The nested report survives there only as a **truncated** string inside that script's JSON options (alongside `"macro.truncated": "true"`), so it cannot be recovered from `body.view`. The `<table class="metadata-summary-macro">` element simply never exists in the converter's input, so `convert_table` never dispatches to `convert_page_properties_report`. Nothing was dropping the table; it was never there. That is also why the failure was silent — the existing `return ""` guards were never reached.

`body.export_view` does render the report fully, with the app macro wrapper stripped and every attribute the existing code path needs still intact (`data-cql`, `data-headings`, `data-sort-by`, `data-current-space-key`).

So this is a **routing problem, not a conversion problem**. The fix is one preprocessing pass, `_inline_app_macro_bodies`, added alongside the existing `_strip_excerpt_include_panel_titles` pass in `Converter.markdown`. It replaces each empty `ap-container` placeholder with the matching report table from `body.export_view`, after which all existing handling applies unchanged — including the full-pagination fetch from [redacted-ref], and the `dataview` output format.

Matching is done on the CQL of the nested `detailssummary` macro in `body.storage`, because `body.export_view` contains no `data-macro-id` or `data-macro-name` attributes at all, leaving the CQL as the only reliable join key.

Keying on `ap-container` rather than on the literal name `table-filter` means other third-party wrappers (Table Excerpt, Chart from Table, and similar) are covered at no extra cost.

### A parser detail worth flagging

`_nested_report_cqls` parses `body.storage` with `html.parser` rather than the `xml` parser used elsewhere in this file.

Confluence storage can contain HTML entities that are **undefined in XML** — third-party macro parameters emit e.g. `&sbquo;`. Those put lxml into error recovery, where it silently drops *unrelated* entities elsewhere in the same document, including the `&quot;` wrapping CQL values. The result is a CQL like `label = my-label and ...` instead of `label = "my-label" and ...`, so the join key never matches.

This cost me a debugging cycle, and it is worth being aware of: the same fragility applies in principle to the other `xml`-parser storage lookups in this file (`_storage_plantuml_macros`, `_extract_include_target_title`, `_extract_uml_from_editor2`). I have deliberately **not** changed those here to keep this PR scoped, but I am happy to open a follow-up issue if you would like them hardened too.

### Logging behaviour

Because the original bug's defining trait was that content vanished with **nothing logged**, the failure paths here are explicit:

- A report present in `body.storage` but with no matching table in `body.export_view` logs a **warning** and is omitted.
- Multiple reports sharing an identical CQL log a **warning** (only the first rendered table can be indexed, since `export_view` has no macro IDs).
- An app macro that wraps no report at all logs at **debug** only. Most app macros legitimately have no report inside them, so warning here would be pure noise.

The CQL string itself is deliberately kept out of warning-level messages and logged at debug instead. It is macro configuration and can embed labels or free-text filters, and every other warning in this module logs metadata only, never a macro's parameter values.

### Known limitations

- Table Filter applies its filtering, sorting and column hiding **client-side** inside the app iframe, and none of that is represented in the REST data. The export is therefore the full, unfiltered report rather than the filtered view seen in the browser. This is documented in `docs/features.md`.
- Static content (for example a plain `<table>`) inside an app macro is still not recovered, since there is no join key available for it. Out of scope here.

## Test Plan

`uv run pytest` — **459 passed** (442 before this change, 17 new). `uv run ruff check` clean.

New test class `TestAppMacroNestedPagePropertiesReport` covers:

- placeholder replaced with the report table, and the report reaching the Markdown output
- the pass being wired into `Converter.markdown`, not merely available
- HTML without an app macro returned unchanged
- an app macro that **did** render content server-side being left alone, so nothing is discarded
- unknown macro id, CQL absent from `body.export_view`, and missing `body.storage` all degrading quietly instead of crashing
- two reports inside one wrapper, both emitted in document order
- the same report referenced by two placeholders being emitted twice
- nested `ap-container` placeholders not crashing the export
- the logging contract above: warning on an unresolvable report, debug-only for an app macro with no report, and no raw CQL at warning level
- `export.page_properties_report_format = "dataview"` still applying to a spliced report
- **regression test for the entity issue above** — storage containing `&sbquo;` alongside `&quot;`-wrapped CQL

The five tests that pin a specific defect — the entity corruption, the shared-table copy, the nested-placeholder crash, and the two logging assertions — were each checked by reverting the corresponding fix and confirming the test fails, so they do not pass vacuously.

Fixtures include the iframe bootstrap `<script>` that the real placeholder always carries. An earlier fixture that omitted it passed while the real page still failed, which is worth mentioning because it is the trap this whole area invites.

Verified end-to-end against a real Confluence Cloud page with a Page Properties Report nested in a Table Filter macro: the table is absent before the change and fully exported after it, with **35 data rows** — more than the 30-row `body.export_view` snapshot, confirming the pagination path runs rather than the truncated snapshot. No leftover placeholder markup, no warnings emitted.

### Review history

This branch went through two review passes. The first found two real defects, both since fixed and covered by the tests above:

- `insert_before` **moves** a node rather than copying it, so a table referenced by two placeholders was silently lost — now inserts a copy.
- Placeholders are collected before the mutation loop, so a nested `ap-container` crashed the whole export once the outer one was decomposed — now guarded.

The second pass found no defects; it produced the logging refinements described above.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
