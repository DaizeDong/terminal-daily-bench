# Add Novita AI as LLM provider

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- Adds `novita` to `_PROVIDER_PRESETS` in `setup_wizard.py` with the OpenAI-compatible endpoint (`[redacted-url]) and default model `moonshotai/kimi-k2.5`
- Adds `novita` to the provider selection menu in the setup wizard
- Adds two tests: preset value validation and end-to-end fresh-setup flow

## Details

Novita AI exposes an OpenAI-compatible API, so it routes through the existing OpenAI forwarding path in `api_server.py` with no additional changes required. Users configure it the same way as any other OpenAI-compatible provider: set `NOVITA_API_KEY` (or enter it during `[redacted-repo] setup`) and the endpoint is pre-filled automatically.

## Test plan

- [ ] `pytest tests/test_setup_wizard.py::test_novita_preset_defaults` passes
- [ ] `pytest tests/test_setup_wizard.py::test_novita_provider_fresh_setup` passes
- [ ] `[redacted-repo] setup` shows `novita` in the provider selection list

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
