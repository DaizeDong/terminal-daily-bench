# fix(voice): anchor SiliconFlow subtitle timeline end to full audio duration

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Problem

`siliconflow_tts` built its subtitle offsets with a hand-rolled loop:

    sentence_duration = int(sentence_chars * char_duration)

Accumulated integer truncation across multiple sentences means the last
subtitle always ends a few 100-nanosecond units before the actual audio
end. Users see a subtitle gap at the tail of every SiliconFlow-narrated
video.

## Fix

Replaced the ad-hoc loop with `populate_legacy_submaker_with_full_text`,
the shared helper that all other providers (`gemini_tts`, `mimo_tts`,
`minimax_tts`) already use. It explicitly anchors the last subtitle entry
to the real `audio_duration_100ns`, eliminating the truncation gap.

Also removed a redundant local `from moviepy import AudioFileClip` import
(already imported at module level) and wrapped `audio_clip.close()` in a
`finally` block so the handle is always released.

## Tests

Added a unit test that mocks the HTTP response and `AudioFileClip`,
calls `siliconflow_tts` with a multi-sentence script, and asserts that
`offsets[-1][1] == int(audio_duration_seconds * 10_000_000)`.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
