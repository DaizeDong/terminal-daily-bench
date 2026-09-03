# fix(guard): bundle native runtime in Desktop Core sidecars

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- Desktop Core sidecars now include the attested, version-matched `[redacted-repo]-runtime` and its sealed manifest so auto command review can complete.
- Cursor hooks treat daemon `native_pre_tool_unavailable` / `native_post_tool_unavailable` as an incomplete review and retry through the attested CLI, which still requires the bundled runtime.

## Testing
- `ruff check scripts/release/stage_native_runtime_for_desktop_core.py scripts/release/verify_pyinstaller_native_runtime.py tests/test_stage_native_runtime_for_desktop_core.py tests/test_verify_pyinstaller_native_runtime.py tests/test_desktop_core_alpha_feed_security.py tests/test_desktop_core_alpha_feed_macos_signing.py tests/test_cursor_hooks.py src/codex_plugin_scanner/guard/adapters/cursor_hook_script_template_head.py`
- `pytest tests/test_stage_native_runtime_for_desktop_core.py tests/test_verify_pyinstaller_native_runtime.py tests/test_desktop_core_alpha_feed_security.py tests/test_desktop_core_alpha_feed_macos_signing.py tests/test_cursor_hooks.py -k test_cursor_hook_script_source_includes_daemon_fast_path --tb=short`


<!-- This is an auto-generated comment: release notes by coderabbit.ai -->

## Summary by CodeRabbit

* **New Features**
  * Desktop Core builds now bundle a validated, signed native runtime and verify it after packaging.
  * Added safeguards to validate runtime integrity, identity, permissions, and archive contents.

* **Bug Fixes**
  * App hooks now fall back correctly when the native pre- or post-tool runtime is unavailable.

* **Documentation**
  * Added troubleshooting guidance for app hook failures and fail-closed shell review behavior.

* **Tests**
  * Added coverage for runtime staging, signing, packaging, verification, and hook fallback behavior.

<!-- end of auto-generated comment: release notes by coderabbit.ai -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
