# fix: split diarized transcripts at speaker turns

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

## Summary

- split diarized transcript lines at every real speaker change, without requiring punctuation
- assign each ASR token by maximum temporal overlap while preserving token objects, text, and timestamps
- keep diarization lag as an ordered suffix buffer, including retrograde ASR timestamps
- attach each validated translation exactly once after speaker splitting, with deterministic boundary and gap behavior
- preserve explicit silence as speaker `-2`
- make Sortformer's final prediction frame cover the complete audio chunk
- document the alignment, buffering, translation, and tie-breaking contracts

## Validation

- `177 passed, 13 skipped` on the current combined main test suite
- `75 passed` across speaker, backend regression, and translation tests
- Ruff and `uv lock --check` pass
- real Whisper pipeline passes
- real 20 second AMI smoke with NeMo 3.0 and `nvidia/diar_streaming_sortformer_4spk-v2`: 3 speakers, speaker turns propagated, no residual diarization buffer
- real Python 3.13 Sortformer inference confirms a 1.00 second chunk now ends at 1.00 seconds

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
