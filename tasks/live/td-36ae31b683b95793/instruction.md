# Fix subtitle preview orientation state

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- Normalize subtitle preview orientation session state before rendering `st.pills`.
- Migrate legacy display labels like `Portrait Safe Area` back to canonical values.
- Add regression tests for canonical, legacy, and invalid preview orientation values.

## Root Cause
Streamlit validates `st.pills` defaults against the raw option values. A stale display label stored in session state could be passed as the default even though the actual options are `portrait` and `landscape`, causing `StreamlitAPIException`.

## Validation
- `uv run pytest webui/components/test_subtitle_settings_unittest.py -q`
- `uv run pytest tests/test_generate_script_docu_unittest.py -q`

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
