# live view: show the instruction and rubric on running pages

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

Live `--serve` snapshots currently build every sample with `instruction=None` and no `scene_metadata`, so running pages show neither the instruction nor the rubric dropdown ([redacted-ref]) until the completed log replaces the snapshot. Plan 0072 called the gap out and scoped it out of the renderer change; this PR closes it at the sink.

Design in `plans/0074-live-scene-metadata.md`: a duck-typed `bind_scenes(scenes)` hook offered by eval's sink fan-out exactly like `bind_spaces`/`bind_frames_dir` (third-party sinks unaffected), `LiveLogSink` stores instruction plus JSON-safe scene metadata per scene id at bind time and fills both fields in every snapshot, and the JSON-safety loop moves to a shared `log.py` helper. The renderer is untouched: it is already state-agnostic for both fields. One fresh-context critique round recorded in the plan header. Implementation follows on this branch.

🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
