# fix(mcp): restore search backend compatibility

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- reconnect the backward-compatible `scripts.mcp_server` search state to the package handler after the server split
- make the DeepSeek adapter request `detail=full`, preserving the path needed by its search -> get_lesson smoke flow
- update fallback tests that assert path/domain to explicitly request the documented full detail level

## Root cause

The MCP server split in [redacted-sha] moved search execution behind a private package-level cache while leaving `HAS_SAG`, `HAS_BM25`, and `sag_search` exposed by the compatibility wrapper. Callers and tests could still patch those exported values, but the handler no longer observed them. The same split enabled compact progressive disclosure, while the DeepSeek adapter still assumed every default search result contained a lesson path.

This caused the full audit on [redacted-ref] to fail in `test_mcp_fallback.py` and `test_mcp_deepseek_adapter.py` even though that PR does not touch Python search code.

## Validation

- red baseline: 3/9 targeted tests failed locally; GitHub audit reported 7 failures under Python 3.10/BM25
- `PYTHONPATH=. pytest -q tests/test_mcp_deepseek_adapter.py tests/test_mcp_fallback.py` — 9 passed
- `PYTHONPATH=. pytest -q tests/test_mcp_server.py tests/test_mcp_auth_contract.py` — 27 passed
- full local audit selection — 756 passed, 8 skipped; one macOS-only proxy assertion remains because urllib reads the host system proxy outside environment variables (the Ubuntu audit environment does not have that proxy)
- `git diff --check`

Unblocks [redacted-ref].

Node ID: hjqcan/goodmemory-maintainer

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
