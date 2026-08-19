# Fix legacy plot routing and figure sizing

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- thread the legacy Gradio/Streamlit Figure Size setting into generation inputs and provider image-size payloads for Gemini/OpenRouter
- keep OpenAI gpt-image on its existing fixed-size API path and document that limitation
- normalize plot-mode JSON text before agent processing, including the multi-series schemas reported in [redacted-ref]
- resolve plot result keys correctly in the legacy UIs so plot outputs are displayed/exported instead of stale diagram keys

[redacted-ref].
[redacted-ref].

## Validation
- PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python -m unittest tests.test_legacy_generation_options tests.test_legacy_plot_agents tests.test_legacy_ui_result_keys tests.test_plot_execution
- PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python -m pytest -q -p no:cacheprovider tests
- git diff origin/main --check

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
