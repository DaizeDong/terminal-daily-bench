# Dashboard telemetry emitter + refined epoch/switch event schema

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

Adds a Dashboard event emitter for real-time training telemetry and refines the epoch/switch event schema, plus a shared graph palette so the local `save_graphs` PNGs read as the same product as the dashboard charts.

## Changes

- **Event emitter** (`dashboard_utils/event_emitter.py`): posts `run_start`, `epoch`, `switch`, `dendrite_added`, `run_end`, and `log` events to the local Dashboard; silently degrades when `requests` is unavailable or the Dashboard is not running.
- **Epoch/switch schema**: events now carry `epoch_index` plus a monotonic `true_epoch` counter, a `phase`, a `scores` dict (validation/running + every `add_extra_score` verbatim), `param_count`, and `pb_scores` / `pb_scores_current` (best vs current dendrite PBScores). `run_end` sends [redacted-repo]'s own stored best values so the dashboard marker matches the patience metric.
- **Shared `_PAI_PALETTE`** in `tracker_[redacted-repo].py`: `save_graphs` PNGs use fixed product colours; switch lines are coloured by the phase being entered rather than alternating r/b.
- **`fixed_input_sizes`** PAIConfig var (cache tuple computations when input shapes are fixed).
- Fix `dashboard_utils` import casing (`Dashboard_Utils` -> `dashboard_utils`), bump version to 3.2.6.
- Move `api-dashboard-events.md` under `dashboard_utils/docs/`, add `pai-emitter-and-graph-brief.md` and `test_event_emitter.py`.

## Testing

- `dashboard_utils/test_event_emitter.py`

🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
