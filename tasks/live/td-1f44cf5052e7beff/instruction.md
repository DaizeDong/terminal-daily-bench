# [fpie] Add video stream blending interface

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

Adds a frame/video/stream interface on top of the existing Poisson image editing processors. The new `fpie.video` module exposes `BlendOptions`, `blend_frame`, `blend_frames`, and `blend_video`, while `fpie-video` provides a CLI that reads targets through OpenCV/FFmpeg-compatible video sources and writes blended output videos.

This also bumps the package version to `0.3.3` and makes MPI initialization lazy so normal imports and non-MPI tests do not initialize MPI eagerly.

Key review points:
- `fpie/video.py`: adds reusable frame and video blending APIs that reuse the existing `EquProcessor`/`GridProcessor`.
- `fpie/video_cli.py`: adds the `fpie-video` command for video files, stream URLs, and camera indices.
- `fpie/process.py`: defers MPI initialization until the MPI backend is explicitly selected.
- `tests/test_smoke.py`: covers the new frame API, video writer path, and video CLI backend check.

## Test Plan
### Automated
- `python -m unittest discover -s tests`: passed, 7 tests run with 1 OpenMP skip.
- `python -m ruff check fpie tests`: passed.
- `git diff --check`: passed.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
