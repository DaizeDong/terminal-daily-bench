# Enable ffmpeg-bins2 manifest: full-feature 8.1.2 for macOS/Linux (Windows/musl fall back to legacy)

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Enables the new full-feature FFmpeg 8.1.2 build (built via `[redacted-repo]/forge`, published to `[redacted-repo]/ffmpeg-bins2`) for the platforms that build cleanly, while keeping every existing install working.

## What this does
- Points `DEFAULT_MANIFEST_URL` at the published [ffmpeg-bins2 catalog]([redacted-url]).
- **macOS x64/arm64** and **glibc-Linux x64/arm64** now resolve to the new **GPL+nonfree, full-codec** 8.1.2 build (x264, x265, fdk-aac, vpx, aom, dav1d, svt-av1, mp3lame, opus, vorbis, openh264, openjpeg, webp, …), downloaded from CDN-backed GitHub Release assets and **sha256-verified**.
- **Windows and musl are intentionally absent** from the catalog (their forge builds are blocked on a systemic MSVC pkg-config issue and forge's C-only musl toolchain, tracked in [redacted-ref]). Those clients — and any manifest fetch/parse failure — fall back to the legacy `ffmpeg_bins` URLs, so **nothing regresses**.

## Verified
- Resolution tested against the live manifest: macOS→darwin zips, glibc-Linux→linux zips; musl/Windows correctly resolve to `None` (→ legacy fallback).
- All 4 release assets serve HTTP 200.
- `flake8`/`mypy` clean, `pytest tests/test_manifest.py` green.
- **This PR's CI is the real end-to-end test**: the macOS/Linux workflows download the new binaries via the manifest and run the small-encode test (`test_encode.py`) on them.

Part of [redacted-ref].

🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
