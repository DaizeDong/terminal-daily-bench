# feat: split card around clarify tool interactions

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Problem

When the model calls Hermes's `clarify` tool, a poll is rendered inside the chat
while the agent worker thread blocks on the user response. The streaming card
keeps accumulating the pre-clarify prose, and once the user answers, the
remaining output is appended to the same card. There is no visual separation
between the prompt and the continuation, and the card grows unboundedly.

## Solution

Inject a CLARIFY hook (the 16th) around `agent.clarify_callback` and add a
`CLARIFY_PAUSED` session state that freezes card flushes while the clarify poll
is visible. When the tool completes, seal the old card and create a fresh
streaming card that carries all post-clarify output.

Card switching is also made cancellation-safe: the session is switched to the
new card before the old one is sealed, so a timeout cancel can never leave the
session pointing at a closed card. Sealing passes the old card's ID and
monotonic sequence explicitly, since CardKit rejects out-of-order updates.

## Changes

- Add `CLARIFY` to the injectable hook list and wrap `agent.clarify_callback`
  in `_run_agent` (enter/exit notifications to the controller).
- Add `SessionState.CLARIFY_PAUSED`; pause `_schedule_flush` while a clarify
  prompt is showing and resume on tool completion.
- Implement `_do_clarify_split`: flush pending content, create the new card,
  switch the session, then seal the old card (create → switch → seal order).
- Seal the old card with explicit `card_id` and `sequence` captured before the
  switch, using a local counter so the new card restarts at sequence 1.
- Reset `split_disabled` in a `finally` block covering cancel/exception paths.
- Add controller tests covering split lifecycle, no-card skip, create-failure
  fallback, seal-failure behavior, and enter/exit pause semantics.

## Compatibility

CLARIFY injection targets `agent.clarify_callback = _clarify_callback_sync`
(verified at Hermes 0.20.0 line 5098); the anchor is unchanged since 0.14.0,
the declared minimum.

## Testing

- 492 tests passed (10 new clarify cases)
- Ruff clean
- mypy clean across 22 source files
- Live gateway: 3 consecutive clarify splits succeeded; old card sealed without
  errors, new card streamed normally

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
