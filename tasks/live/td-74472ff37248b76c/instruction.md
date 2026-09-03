# feat(confluence): export plantumlcloud macro as a code block

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref]

## Summary

Pages using the [Flowchart, PlantUML Diagrams for Confluence]([redacted-url]) app currently export with the diagram missing entirely: no code block, no image, not even a marker.

On Confluence Cloud that app registers the macro name **`plantumlcloud`**, while only `plantuml` was dispatched in `macro_handlers`. Being a Connect app, it renders nothing but an empty iframe placeholder into `body.view` and writes nothing to `editor2`, so the unhandled macro fell through to markdownify's default `convert_div` and produced an empty string.

`docs/features.md` already linked to this exact marketplace app and promised fenced PlantUML blocks, so this closes a gap between the documented and actual behaviour.

### What it does

The diagram source lives in `body.storage`, in the macro's `data` parameter: base64, and when the sibling `compressed` parameter is `true`, additionally raw-DEFLATE-compressed and percent-encoded (the mxgraph/draw.io encoding). The new `convert_plantumlcloud` handler recovers it and emits a fenced `plantuml` block, matching what the existing Server/DC `plantuml` handler produces.

The rendered `.svg`/`.png` attachments are deliberately **not** embedded; the diagram source is exported, as documented.

### Decoding is deliberately defensive

`body.storage` is remote content, so every failure mode degrades to a visible `<!-- PlantUML diagram (source not found) -->` marker plus a log warning, never to wrong or empty output:

- the inflate is bounded at 4 MB and rejects truncated streams, which inflate without raising and would otherwise be exported as a silently partial diagram;
- base64 decoding tolerates line wrapping, but never falls back to emitting the undecoded parameter;
- percent-decoding is applied only when the text is actually encoded, because PlantUML sources legitimately contain a literal `%` (`%date%`, `%filename()`).

### Macro matching

Macros are matched by `macro-id`, falling back to document order only when `body.storage` carries no `macro-id` at all. A placeholder whose `macro-id` is unknown to this page belongs to a transcluded page (an `include` macro expands another page's view HTML inline), so it resolves to the marker rather than to an unrelated diagram.

### Refactors carried along

- `_storage_plantuml_macros` generalised into `_storage_macros_by_name(name)` with a name-keyed cache; the existing `plantuml` path is unchanged.
- The parameter-extraction loop duplicated between the panel-icon code and the new code extracted into `_macro_params()`.

## Test Plan

- `tests/unit/test_plantumlcloud_conversion.py` adds 24 tests using synthetic diagram sources: happy path, compressed and uncompressed payloads, line-wrapped base64, literal `%` preservation, `macro-id` selection, positional fallback and cursor semantics, foreign/transcluded `macro-id`, truncated and oversized payloads, nested parameters, and a case with both macro flavours on one page guarding the shared cache.
- `uv run pytest`: **466 passed** (442 before this change).
- `uv run ruff check` and `uv run ruff format --check`: clean.
- `uv build --no-sources`: builds.
- Verified end to end against a real Cloud page holding 5 `plantumlcloud` diagrams: all 5 export as `plantuml` fences with no "source not found" markers.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
