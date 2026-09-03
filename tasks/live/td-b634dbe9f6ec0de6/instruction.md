# fix: contain upload identifiers

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Roadmap [redacted-ref] of 11 — closes **F13**. See [redacted-ref] for the audit.

## The escape

`upload_ref_from_url` decoded percent-escapes *after* splitting the URL path, so an encoded separator survived inside a single component:

```python
>>> upload_ref_from_url("[redacted-url])
('../../data', 'x.mp4')
>>> metadata_path("../../data")
'/data/uploads/../../data/meta.json'
```

Only the *filename* was ever `basename`'d. On a device `/data` is the parent of `/data/uploads`, so that path reaches the directory holding `settings.json`, `history.json`, and `peers.json`.

## The fix

`upload_dir` becomes the containment boundary for the whole store — metadata, session, media, and deletion paths all derive from it — and enforces the generated id format.

`new_upload_id` has produced `u_` + 20 hex characters **since the first commit** (`[redacted-sha]`), so that's the entire format that has ever existed on disk. Enforcing it orphans nothing. A `commonpath` check backs it up so widening the format later can't quietly reopen this.

### The part that needed care

It returns `""` rather than raising — every caller already treats a missing upload as expired (410), and a raise would turn a hostile URL into a 500.

But that required handling at each *derived* path, not just the boundary: **`os.path.join("", "meta.json")` is a relative path.** Propagating the `""` naively would have read `./meta.json` out of the working directory — trading one wrong file for another. There's a test pinning exactly that.

`delete_upload` also refuses an unvalidated id. It's reached today only with server-generated ids and ids read back from `meta.json`, so this is defence in depth rather than a live path — but the operation is `shutil.rmtree` and the guard costs nothing.

## Testing

**Revert proof:** removing the validation fails **20 tests**, including the real-filesystem escape and the rmtree guard.

28 tests added:

- Id format across 12 near-misses (one char short, one long, wrong case, non-hex, separator smuggled in, `None`), and 25 generated ids round-tripping.
- Derived paths returning `""` rather than a relative path.
- Five encoded-traversal URL shapes including `%2f` lowercase and `%2e%2e`.
- `test_traversal_cannot_read_a_file_outside_the_root` — the audited escape against a **real filesystem**, with a matching `meta.json` actually placed outside the root, since the finding only bites when a file is there.
- `delete_upload` leaving a victim directory intact, and still removing a genuine upload.
- Route-level: traversal rejected, real upload still served with its bytes.

Gates: **771 Python tests** (+28), 11 JS tests, ruff clean, `git diff --check` clean.

## Device verification

On the combined branch:

| Check | LR | Pi |
|---|---|---|
| `GET /media/uploads/..%2F..%2Fdata/x.mp4` → 404, no filesystem access outside the root | pass | pass |
| `is_valid_upload_id('../../etc')` is `False` in the running process | pass | pass |

**Still outstanding**: upload a file and play it, and confirm an existing pre-upgrade upload still plays from history. The id format is unchanged since the first commit so this should be a no-op, but it is worth confirming against real `meta.json` files rather than trusting the git archaeology.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
