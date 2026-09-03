# feat: default Whisper model to large-v3

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## What

Changes the default `--model` from `medium.en` to **`large-v3`**.

## Why

`large-v3` catches more fillers and produces tighter word boundaries, which directly improves the intra-word and overlong detectors (they reason about word duration). Making it the default gives better detection quality out of the box. Users who want faster, lower-accuracy runs can still pass `--model medium.en` or `--model small.en`.

## Changes

- Defaults updated in `cli.py`, `asr.py`, `validate.py`
- Test assertions updated (`test_cli.py`)
- README table + intro, `docs/usage.md`, `docs/transcription.md`, `docs/troubleshooting.md`
- CHANGELOG `[Unreleased]` entry

## Testing

`168 passed` — full suite green.

🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
