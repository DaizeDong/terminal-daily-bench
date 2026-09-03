# fix: order durable state publication

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Roadmap [redacted-ref] of 11 — closes **F04**. See [redacted-ref]. Lands before [redacted-ref] on purpose: F01's ownership checks attach to the session publish point this consolidates.

## Writes could land out of order

Payloads are built under a store lock and written *outside* it, so two mutations could reach the disk in either order — and `os.replace` is last-write-wins. The older writer could win, losing the newer mutation, which then reappeared missing after a restart.

Each store now has its own publisher. A version is reserved while the payload is built, under the store's lock; a write that is no longer the newest is dropped rather than applied.

**The counter and the write mutex are deliberately separate.** `reserve()` is called while a store lock is held, so it must never wait on disk I/O — that's the constraint keeping no state lock held across a write. `test_queue_lock_is_not_held_while_writing` fails by deadlock if that's ever violated.

Four independent publishers, so a busy queue can't suppress a settings write.

## Session fields had no lock, and wrote per field

Each setter mutated a global then persisted the **whole composite payload**. A caller changing three fields wrote three times, and the first two were snapshots of a state that never conceptually existed — `now_playing` set while `session_state` still said `idle`. A restart landing between them restored one of those.

`update_session` applies the fields as one mutation under one lock and persists once. The individual setters delegate to it, so callers outside `playback_service` need no change.

The transition inventory shows the effect directly:

```
- | `NOW_PLAYING`     | playback_service.py (11) ...
+ | `NOW_PLAYING`     | playback_service.py (6)  ...
- | `SESSION_STATE`   | playback_service.py (10) ...
+ | `SESSION_STATE`   | playback_service.py (3)  ...
```

## Disk failure was invisible

`_atomic_write_json` swallowed every failure into a log line, so a full or read-only disk produced a **successful API response** and state that silently reverted on restart.

It returns its outcome now, `persist_*` propagate it, and `persistence_health()` records failures. `/status` carries a `persistence` key **only while writes are failing**, so the payload grows only when something is wrong — additive and safe for companions.

**Deliberately not done:** turning a write failure into a 5xx. The failure is observable to callers and in `/status`, but making every mutation fail on a full disk is a behavior change that doesn't belong inside a concurrency fix. Flagging it rather than smuggling it in.

## Two existing tests changed

`test_clear_resumable_session_route_stops_and_clears_state` and `test_clear_now_playing_returns_to_idle_without_preserving_current` asserted that three specific setters were called — the mechanism this PR replaces, not the behavior. They now assert the session's resulting state *and* that exactly one write happened, which is both what the route promises and a stronger check. Both still fail against the reverted code.

## Testing

| Reverted | Fails |
|---|---|
| version check dropped | 2 ordering tests |
| failure swallowed again | 3 health / `/status` tests |
| per-field setters restored | 2 composite-write tests |

The ordering test reverses completion order deterministically — reserve two versions, publish the newer first, then the older — rather than racing threads and hoping.

Gates: **757 Python tests** (+14), 11 JS tests, ruff clean, `git diff --check` clean. `TRANSITION_INVENTORY.md` regenerated with `--write`.

## Device verification

On the combined branch, both devices:

| Check | LR | Pi |
|---|---|---|
| `state.persistence_health()['ok']` in the running process | `True` | `True` |
| `/status` omits the `persistence` key while writes are landing | pass | pass |

The key is absent unless something is wrong, so a healthy device's payload is unchanged — confirmed on both.

**Still outstanding**: change a setting, restart the container immediately, and confirm the change survived; then the same with a queue mutation.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
