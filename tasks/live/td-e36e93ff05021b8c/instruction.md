# Fix FileNotFoundError in bot_auth when session file doesn't exist

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

`bot_auth()` crashes with `FileNotFoundError` when the bot directory exists from a previous run but contains no `.session` file (e.g., prior run failed before Telethon created it). The `shutil.copyfile` call was unconditional.

- **Fix**: Guard the `shutil.copyfile` with `os.path.exists()` check

```python
old_session = f'{new_path}/{base_path}.session'
if os.path.exists(old_session):
    shutil.copyfile(old_session, f'{base_path}/{base_path}.session')
```

- **Tests**: Added `test_bot_auth_session.py` covering both the missing-session and existing-session cases

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
