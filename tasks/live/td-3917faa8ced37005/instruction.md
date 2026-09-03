# fix(download): stop counting the final write buffer twice in bytes_acc

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref].

## The defect

`download_file` appends every chunk to `bytes_acc` as it arrives
(`moon_download.py:593`), and the tail flush then re-appended the joined
leftover buffer — bytes that were already counted:

```python
if buf:
    data = b"".join(buf)
    ...
    bytes_acc.append((time.monotonic(), len(data)))   # removed
```

The mid-loop flush at `moon_download.py:596-604` already did the right thing by
leaving the deque alone. With `WRITE_BUF` at 16 MiB, any transfer smaller than
that never reaches the mid-loop flush, so its entire size was recorded twice; a
larger transfer over-counted by whatever remained in the final partial buffer.

## Reproduced on `[redacted-sha]`

Using the repository's own fake-session pattern from `test_on_event.py`:

| transfer | on disk | recorded in `bytes_acc` |
| --- | ---: | ---: |
| 5 MiB | 5,242,880 | 10,485,760 |
| 20 MiB | 20,971,520 | 25,165,824 |

Which matches the figures in the issue.

## The change

One line removed. The write itself, `last_write_bytes` and
`write_persisted_before` all stay; only the duplicate accounting entry goes.

`downloaded`, `rec.done_bytes`, `rec.live_mbs`, `speed_win` and `pub_win` are
untouched — they were already correct, because they are accumulated per chunk
and never from the flush.

## Tests

`tests/test_bytes_acc_accounting.py`, following the fakes in `test_on_event.py`
and `test_resume_200.py`. The cases that probe a buffer boundary derive their
sizes from `WRITE_BUF` and `RECV_CHUNK` so they keep their meaning if those
change; the rest use plain megabyte transfers. Accounting expectations come
from the chunks the fake session actually handed over.

On this branch: 9 passed. On unmodified `main`: 6 fail and 3 pass.

The six that fail are the ones that see the duplicate entry — the two
whole-transfer cases, the three parametrised small transfers, and
`test_one_entry_per_received_chunk`, which catches it as an extra entry rather
than as an inflated total. A representative failure is
`assert [redacted-sha] == [redacted-sha]`: an 8 MiB transfer recorded as 16 MiB, with the
deque showing four real chunk entries followed by one 8 MiB tail entry.

The three that pass on `main` do so by design, and they are what keeps the fix
honest rather than just proving the symptom:

- `test_exact_multiple_of_write_buffer_leaves_no_tail` — an exact multiple of
  `WRITE_BUF` leaves `buf` empty, so the tail flush never runs. It pins the
  per-chunk append: a change that moved accounting to the flush sites instead
  would break this case and not the others.
- `test_entry_timestamps_stay_within_the_transfer` — a bound rather than a
  per-chunk claim: it rejects an entry stamped outside the call. Both front-ends
  window this deque at three seconds for the live speed reading, so an entry
  arriving at the wrong time is wrong even when the total is right.
- `test_aborted_transfer_records_only_what_it_received` — a run cut short must
  record what it actually got and nothing more, from either append site. The
  fake records whether the fatal control was already set as it handed each
  chunk over, so the expected entries are the chunks delivered while it was
  clear — an observation rather than an assumption about how far the loop runs
  past the signal.

`ruff check .` is clean and every tracked module byte-compiles.

`tests/test_elapsed_clock.py::test_elapsed_resets_on_new_run` fails on this
machine both before and after this change — it is about the engine's elapsed
clock, not byte accounting, and I have left it alone.

## Not in scope

The ETA expression at `moon_engine.py:714` reads this deque and inherits the
inflation, but that is [redacted-ref]'s scope and has an open pull request, so this change
stays out of it.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
