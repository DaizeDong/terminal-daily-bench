# fix(debug): ssh sessions exit 1 on images with a /bin/false passwd shell (Spark)

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Problem

SSH-into-task against a Spark task connects and authenticates, but every session exits 1 with no output — even `ssh flyte-debug true` — and PTY logins close immediately.

`apache/spark-py`'s `entrypoint.sh` synthesizes a passwd entry for the anonymous uid with a no-login shell:

```
185:x:185:0:anonymous uid:/opt/spark:/bin/false
```

`SshServer._handle_session` seeds `SHELL` from `pwd.getpwuid(...)`, so every session exec'd `/bin/false -c <cmd>`.

## Fix

`_is_login_shell()` rejects `false` / `nologin` / `true` (and non-executable paths); the passwd shell is only used when it passes, otherwise fall back to `bash`, then `sh`.

## Verification

- Reproduced on dogfood-1 (real Spark driver pod `<run>-a0-0-driver`): before the fix `ssh flyte-debug 'echo CONNECTED; id'` → exit 1, nothing printed. With the fixed wheel baked into the image: prints `CONNECTED`, `uid=185(185)`, `SHELL=/usr/bin/bash`, lands in the code dir; `ssh -tt` PTY session works.
- Unit test for `_is_login_shell` in `tests/flyte/test_ssh_debug.py`; file passes, ruff clean.
- `examples/plugins/spark_ssh_debug.py` is the repro used (takes an optional config path).

Context: Slack ticket [redacted-ref] — the customer's reported `kex_exchange_identification: banner line contains invalid characters` did not reproduce on our side (dogfood + demo, runtime 2.5.18 and 2.6.x); this is the next failure they would have hit.

🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
