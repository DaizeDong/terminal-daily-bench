# (feat) add Discord cache category to junk cleaner

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## What does this PR do?

This PR addresses the issue regarding Discord's large Chromium-style cache accumulation. It adds a new dedicated junk category `discord-cache` that identifies and targets safe-to-clear cache directories for Discord and its alternative release channels (PTB and Canary), while strictly preserving user session and login data. 
[redacted-ref] 

## Safety checklist

[redacted-repo] deletes files, so every PR keeps these promises:

- [x] `pytest` is green, including `tests/test_safety.py`
- [x] No new direct deletions (`os.remove`, `shutil.rmtree`, `Path.unlink`); everything goes through `safety.trash()`
- [x] New destructive paths default to dry-run and ask before applying
- [x] New core functions have a matching test

## Notes for the reviewer

- **Scope:** The `discord-cache` category safely covers standard Discord, Discord PTB, and Discord Canary by looking at their respective directories in `%APPDATA%`.
- **Targeted directories:** It only targets `Cache`, `Code Cache`, and `GPUCache` subdirectories. 
- **Safety Carve-out:** Vital user session data (such as `Local Storage`) is strictly left untouched to ensure users are never logged out of their accounts after a cleanup.
- **Testing:** A comprehensive sandbox test has been added to `tests/test_junk.py` to validate flavor discovery and ensure session folders are never included in the roots.
-  **Manual Test:** I installed and tested this implementation locally with my own Discord client; the script successfully detected and staged the cache directories for deletion during the dry-run, and my account session remained perfectly active and unaffected afterwards.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
