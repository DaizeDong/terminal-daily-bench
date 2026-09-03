# Refresh MiniMax provider preset to MiniMax-M3 with regional endpoints

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Reason: Refresh the stale MiniMax provider preset to the current model and add the China regional endpoint.

The MiniMax setup preset only exposed the global endpoint `[redacted-url] with `MiniMax-M2.7`. This updates the preset so the current model and both regional endpoints are selectable without manual edits.

Changes:
- Update the MiniMax preset default `model_id` from `MiniMax-M2.7` to `MiniMax-M3`.
- Add a `regions` map to the MiniMax preset covering the global (`[redacted-url]) and China (`[redacted-url]) OpenAI-compatible endpoints.
- In the setup wizard, providers that declare `regions` now prompt for a region (`global_en` / `cn_zh`) and default the API base URL to the matching regional endpoint; providers without `regions` are unaffected.
- Persist the selected region as `llm.region` in the generated config and expose it as `[redacted-repo]Config.llm_region`.

Checks:
- `ruff check .` passes.
- `ruff format --check .` passes.
- `pytest tests/test_setup_wizard.py` (3 passed), including new coverage for the MiniMax preset defaulting to `MiniMax-M3` / `global_en` and selecting the China endpoint when `cn_zh` is chosen.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
