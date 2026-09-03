# Surface peak process-RSS across the whole run, labeled (0.11.0)

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Prompted by a dev.to reader's production war story (OOM around turn 8–9; nobody had written down *which* memory number the test sampled; model reloaded fresh in tests but kept alive in prod).

[redacted-repo] had the same trap: the leaderboard showed only **resident model size**, and its peak-RSS was (a) sampled during a single short probe and (b) buried in the JSON.

**Changes**
- **Sample RSS across the entire per-model run** (load + speed + every quality task), not just the speed probe — baseline captured before load, so the peak reflects sustained use.
- **Surface a labeled `Peak` column** next to `Memory` (resident) everywhere: Rich leaderboard, plain + TUI renderers, and the Markdown/HTML reports, with notes clarifying resident vs peak. No more 'which number is this?'.

**Live:** llama3.2 → Memory 2.4 GB (resident) / Peak 573 MB (process-RSS growth); the gap is the Apple-Silicon/Metal caveat (weights in unified memory), which the docs call out. Generations are single-turn, so Peak isn't a multi-turn-session watermark — also documented.

**162 tests** (was 160). Bumps to **0.11.0**. Nice to be able to reply to the commenter with a shipped change.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
