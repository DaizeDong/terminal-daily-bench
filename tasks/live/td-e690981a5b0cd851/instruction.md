# fix: route insert-runner thread safety through a client capability

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref]. The fixed-rate insert runner decided per-thread client handling by checking `db.name` against a hardcoded list (`PgVector`, `Doris`, `SeekDB`, `VolcMySQL`), so clients that declare `thread_safe = False` but aren't on that list — `OceanBase`, `VectorChord`, `Adbpg`, `LanceDB` — fell through to the default path and shared one non-thread-safe connection across insert workers. `OceanBase` was never in the list at all.

I moved the decision onto the existing `thread_safe` capability. The runner now branches on `db.thread_safe` and asks the client for a per-thread copy via a new `VectorDB.copy_for_thread()`. The default deep-copies the instance, which already works for the psycopg-family clients and for `LanceDB` (it has a custom `__deepcopy__`); the `mysql.connector`-backed clients override it to shallow-copy and drop their open socket so `init()` reconnects inside the worker. Behavior for the databases that were already special-cased is unchanged — the capability just also covers the ones the name list missed, and adding a new non-thread-safe client no longer means remembering to edit the runner.

Added a unit test that drives `send_insert_task` with a fake client and checks that thread-safe clients insert through the shared object while non-thread-safe ones go through a copy plus `init()`.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
