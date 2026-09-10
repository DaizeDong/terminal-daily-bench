# feat: add native Zotero Local API resolution

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- add a private, read-only Zotero Local API v3 client using only the Python standard library
- resolve DOI, arXiv, title, and exact item-key inputs against the local personal library before web providers
- safely reuse local PDF attachments and expose `auto`, `off`, and `required` lookup policies through the resolver and pipeline
- report Local API readiness in the existing environment diagnostics and document the built-in workflow in English and Chinese

## Resolution behavior

- `auto` (default): prefer a unique local match; fall back to existing providers for title, DOI, and arXiv misses
- `off`: make no Local API request and preserve the previous resolution path
- `required`: require a unique Zotero match, while trusted JSON artifacts and explicit local PDFs remain authoritative
- ambiguous local identities and unverifiable explicit Zotero keys fail closed
- missing or ambiguous attachments do not invalidate uniquely confirmed parent metadata
- group-library select links are rejected explicitly rather than being queried against the wrong library

## Safety

- fixed loopback-only endpoint with proxies and redirects disabled
- read-only `GET` requests, no API key, no SQLite access, and bounded response sizes
- strict local `file://` validation rejects remote UNC paths, ports, queries, fragments, invalid UTF-8, and encoded NULs
- attachment keys remain distinct from parent bibliographic item keys

## Testing

- `python -m pytest -q` — **756 passed, 1 skipped**
- Ruff passed for all changed Python implementation and focused test files
- `git diff --check origin/develop...HEAD`

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
