# [codex] Add agent installer support

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- Extend the one-command installer with Codex, generic MCP JSON, add-mcp, and all-client registration targets.
- Add a portable agent usage guide covering Codex, Claude, Cursor, Cline, Continue, Zed, tool selection, citations, gating, API keys, and proxy handling.
- Update README and usage docs with one-line commands for Codex and other agent workflows.
- Review fix: make the add-mcp path target all supported agents with `--all -g -y`.

## Validation

- `uv run pytest -q tests/test_install_script.py tests/test_smoke.py::test_imports` -> 8 passed
- `uv tool run ruff check .` -> All checks passed
- `bash -n scripts/install.sh`
- `bash scripts/install.sh --dry-run --client add-mcp` -> prints `--name search --all -g -y`

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
