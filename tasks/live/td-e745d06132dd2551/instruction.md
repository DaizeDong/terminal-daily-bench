# fix(guard): reseal Core native manifest after PyInstaller signing

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- After PyInstaller packages the attested native runtime into the Desktop Core sidecar, rewrite the CArchive native manifest so `runtime_sha256` and `runtime_size` match the packaged bytes.
- Keep `--add-data` packaging. PyInstaller compresses DATA entries and can re-sign Mach-O payloads, which changes digest after the pre-package identity refresh.
- Preserve neighboring archive entries and the bootloader prefix. Write the updated manifest uncompressed. Reject TOC entries that overlap the archive payload, and fail closed if extracted native bytes do not match the TOC size.

## Testing
- `python3 -m pytest -q tests/test_seal_pyinstaller_native_manifest.py tests/test_verify_pyinstaller_native_runtime.py tests/test_desktop_core_alpha_feed_macos_signing.py tests/test_desktop_core_alpha_feed_security.py --tb=short`
- `python3 scripts/ci/code_quality_audit.py --root . --baseline ci/code-quality-baseline.json`


<!-- This is an auto-generated comment: release notes by coderabbit.ai -->

## Summary by CodeRabbit

* **New Features**
  * Added native manifest sealing for standalone Core builds.
  * Improved support for compressed and uncompressed application archives while preserving bundled components.

* **Bug Fixes**
  * Ensured manifest sealing occurs before macOS signing and runtime verification.
  * Improved handling of incomplete, unreadable, or structurally invalid archive and runtime data.

* **Tests**
  * Added coverage for manifest updates, compression handling, archive preservation, validation, and build-step ordering.

<!-- end of auto-generated comment: release notes by coderabbit.ai -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
