# fix: probe /categoryscheme on providers passed as a URL

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Problem

Pointing the CLI at an endpoint that is not in `portals.json` works for everything — dataflow list, schema, constraints, download — except `tree`:

```
$ [redacted-repo] tree --provider [redacted-url] --depth 1
Error: Active provider does not expose /categoryscheme.
```

The endpoint does expose it. `categories_supported` is a capability *declared* by the 15 listed providers; a custom URL provider never carries the key, and the falsy default was read as a denial. The message asserted something that had never been checked.

## Fix

- The gate fires only when a listed provider declares `categories_supported: false`. An undeclared provider is probed live, and an `httpx.HTTPStatusError` is translated into `CategoriesNotSupported` naming the URL and the status code.
- Second cause on the same path: `catalog_agency` fell back to `agency_id` — empty for a custom URL — producing `categoryscheme//ALL/latest` → 404. A single `_catalog_agency()` helper falls back to the `ALL` wildcard for both structure calls.
- The cross-agency `df_id` prefixing still compares the *configured* `catalog_agency`, so the wildcard fallback cannot change behaviour for any listed provider. The change is generic: no per-provider branch.

## Verified live

| command | before | after |
| --- | --- | --- |
| `tree --provider [redacted-url] --depth 1` | refused | 9 schemes (`ECO` 50 dataflows, `INT_ECO` 53, `BANK_FIN` 25, …) |
| `tree --provider worldbank` | refused | refused, with the list of providers that have a tree |
| `tree --provider [redacted-url] | refused | `HTTP 403` reported with the URL tried |

`category_context()` — used opportunistically by `search` and `embed` — is cache-only, so no discovery path can now trigger the 1-2 minute tree build.

## Gate

ruff clean, mypy strict clean on 15 files, 379 tests green (3 new in `tests/test_categories.py`). `skills/sdmx-explorer/` updated (SKILL.md + `references/thematic-tree.md`) along with the `tree` help text and `LOG.md`.

🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
