# fix: close pbar and file handle on exception in download() ([redacted-ref])

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Problem

[redacted-ref].

Three resources are not released when an exception occurs during download:

| Resource | Location | Leak scenario |
|---|---|---|
| `pbar` (tqdm progress bar) | `download.py` | Any exception while iterating chunks |
| `f` (`.part` file handle) | `download.py` | Same — on Windows: locks the file |
| `sess` (HTTP session) | `download_folder.py` | Exception in `_download_and_parse_google_drive_link` |

The Windows impact for the file handle is observable: a subsequent `download(..., resume=False)` to the same path fails because the process still holds the `.part` file open.

## Root Cause

### `download.py` — `pbar` and `f`

```python
# Both pbar and f are only cleaned up on the happy path:
try:
    ...  # exception here leaves pbar and f open
    if not quiet:
        pbar.close()  # only on happy path
    if tmp_file:
        f.close()     # only on happy path
        shutil.move(tmp_file, output)
finally:
    sess.close()      # only sess is guarded
```

### `download_folder.py` — `sess`

```python
sess, _ = _get_session(...)  # creates session
# no try/finally
gdrive_file = _download_and_parse_google_drive_link(sess=sess, ...)
# if this raises, sess is never closed
```

## Fix

**`download.py`** — initialize `pbar = None` before the `try` block so the `finally` can safely reference it, then add cleanup for both `pbar` and `f`:

```diff
+pbar = None
 try:
     ...
 finally:
+    if pbar is not None:
+        pbar.close()                     # tqdm.close() is idempotent
+    if tmp_file is not None and not f.closed:
+        f.close()                        # only if we own f (not caller BinaryIO)
     sess.close()
```

**`download_folder.py`** — wrap the session-using call in `try/finally`:

```diff
 sess, _ = _get_session(...)
+try:
     gdrive_file = _download_and_parse_google_drive_link(sess=sess, ...)
+finally:
+    sess.close()
```

## Constraints Observed

- `f` is closed **only when `tmp_file is not None`** — when `output` is a caller-provided `BinaryIO`, `f = output` and closing it would be wrong.
- `not f.closed` prevents a double-close on the happy path where `f.close()` already ran inside the `try` body.
- `pbar.close()` is idempotent in tqdm; calling it twice (happy path + finally) is safe.
- The partial `.part` file is left in place (no `shutil.move` on the exception path), so resume keeps working.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
