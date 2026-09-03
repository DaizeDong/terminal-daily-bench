# fix: preserve user-provided enable_thinking for Qwen models

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

When users explicitly set `enable_thinking` via `extra_body` in `OpenAIChatModel`, the value was being forcibly overwritten to `False` for Qwen/pai-judge models in non-streaming mode.

This PR adds a guard to only set the default when the user hasn't already configured it:

```python
# Before: always overwrites
kwargs["extra_body"]["enable_thinking"] = False

# After: respects user configuration
if "enable_thinking" not in kwargs["extra_body"]:
    kwargs["extra_body"]["enable_thinking"] = False
```

## Changes
- **[redacted-repo]/models/openai_chat_model.py**: Added conditional check before setting `enable_thinking` default
- **tests/models/test_openai_chat_model.py**: Added 2 unit tests:
  - `test_qwen_enable_thinking_user_value_preserved`: verifies user-provided values are kept
  - `test_qwen_enable_thinking_default_when_not_provided`: verifies default False still applies

## Motivation
Related to issue [[redacted-ref]]([redacted-url]) where users reported unexpected WARNING/DEBUG output when configuring Qwen models. The root cause was that user-provided `extra_body` settings were being silently overwritten.

---
Powered by Hermes Agent | Building open source daily 🚀

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
