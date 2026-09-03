# Fix stored XSS in HTML report; add geocoding privacy controls & positional CLI

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

This branch hardens the HTML report and adds privacy/UX controls that came out of a security review of the export and analysis paths.

### 1. Security — stored XSS in the HTML report (fix)
File metadata (`Author`, `Title`, `Creator`, …) is attacker-controlled and was written into the HTML report **unescaped**. A crafted document could run JavaScript in the analyst's browser when the report is opened. Proven with an `<img onerror>` / `<script>` payload, now fixed: all values and field names are HTML-escaped, and the Address / Map Link anchors are rebuilt with escaped text and percent-encoded URLs. Regression tests added for both display modes.

### [redacted-ref]. Geocoding privacy
- `--no-geocode`: disable reverse geocoding (no coordinates sent to any third party; raw GPS still shown).
- `--nominatim-url`: query a self-hosted Nominatim server instead of the public one.
- Enforce Nominatim's **1 req/s** usage policy; drop the unused reverse lookup in singular mode (no wasted request, no coordinate leak).

### 3. CLI ergonomics
- Positional `TARGET` auto-detection: a path → analysis, an `http(s)` URL → scraping. `-d` / `-s -u` still work; incompatible combinations are rejected so the existing safeguards are preserved.
- Defaults: `--download-dir` → `./loot/` (created if missing), `--depth` → `1`.

### Behaviour changes to note
- `--depth` default **0 → 1** (matches the README's long-standing advice).
- Scraping with neither `--scan` nor `--download-dir` now downloads to `./loot/` instead of erroring.
- `--download-dir` is created if missing.

### Testing
- 57 unit tests pass locally (50 existing + 7 new).
- `py_compile` clean; functional end-to-end checks (HTML export escaping, positional dir/file/URL, safeguards) verified manually.

Docs (README + TODO) updated accordingly.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
