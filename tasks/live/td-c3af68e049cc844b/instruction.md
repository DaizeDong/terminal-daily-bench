# fix(update): re-exec runs the new binary after self-update (endless update-prompt loop)

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
The interactive self-update looped forever: it downloaded and installed the new release, re-exec'd, and then prompted "A new version of [redacted-repo] is available: 1.4.1 → 1.5.3" again — never actually running the new version.

Root cause (verified against PyInstaller 6.21 bootloader source and reproduced with real onefile binaries): the PyInstaller bootloader marks its process tree via env vars — `_PYI_ARCHIVE_FILE`, `_PYI_APPLICATION_HOME_DIR` (the `/tmp/_MEIxxxx` extraction dir), `_PYI_PARENT_PROCESS_LEVEL` (`_MEIPASS2` on older bootloaders). `os.execv(sys.executable, sys.argv)` inherited them, so the freshly installed binary's bootloader saw "same archive as parent", classified itself as a spawned subprocess, skipped extraction, and reused the **old version's** `_PYI_APPLICATION_HOME_DIR` — old bundled libs, data files, and `[redacted-repo]-agent` dist-info metadata. `get_version()` (importlib.metadata) therefore still returned 1.4.1, the update prompt fired again, and the cycle repeated indefinitely.

Repro (Linux, PyInstaller 6.21.0, onefile v1.4.1 binary that self-replaces with a v1.5.3 build and re-execs):

```
=== BEFORE (os.execv) ===                       === AFTER (sanitized env) ===
version: 1.4.1 (meipass=/tmp/_MEIbIq0uj)        version: 1.4.1 (meipass=/tmp/_MEIgckcQe)
Update? y ... Updated [redacted-repo] to 1.5.3            Update? y ... Updated [redacted-repo] to 1.5.3
version: 1.4.1 (meipass=/tmp/_MEIbIq0uj)  ←loop version: 1.5.3 (meipass=/tmp/_MEIQHZ7wF)
Update? y ... Updated [redacted-repo] to 1.5.3            up to date — scan continues
version: 1.4.1 (meipass=/tmp/_MEIbIq0uj)  ←loop
```

macOS uses the same bootloader code path as Linux here, so the fix applies identically. Windows is unaffected: main() never re-execs there (it exits after updating).

Fix: replace the bare `os.execv` in `main()` with `restart_after_update()`, which builds a sanitized env:

```python
def restart_env():
    env = {k: v for k, v in os.environ.items()
           if k != "_MEIPASS2" and not k.startswith("_PYI_")}
    # restore LD_LIBRARY_PATH / DYLD_* from the *_ORIG copies the bootloader saved
    ...

def restart_after_update():
    os.execve(sys.executable, sys.argv, restart_env())
```

With the `_PYI_*` vars stripped, the new bootloader performs a full environment reset and fresh extraction, so the re-exec genuinely runs the new release. Library-path vars the bootloader overrode are restored from their `*_ORIG` copies (or dropped if there was no original), matching PyInstaller's documented convention.


Link to Devin session: [redacted-url]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
