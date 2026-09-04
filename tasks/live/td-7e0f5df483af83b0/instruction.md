# feat: add LAPI machine heartbeat metadata

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Keeps the import machine showing as active in `cscli machines list` by sending LAPI machine heartbeats, instead of letting it go stale (CrowdSec flags heartbeats older than 2 minutes).

- **Daemon mode:** a background thread sends a heartbeat every `CROWDSEC_HEARTBEAT_INTERVAL` seconds (default `60`, matching CrowdSec's own client heartbeat), independent of the import interval, so the machine stays fresh between imports.
- **Single run:** sends one heartbeat after LAPI authentication succeeds.
- Adds an OS-aware `User-Agent` for LAPI requests, preserving existing blocklist-fetch headers.
- New `CROWDSEC_HEARTBEAT_INTERVAL` env var / `--heartbeat-interval` flag (`0` disables).
- Refactors LAPI client construction into a `create_lapi_client_from_config()` helper (reused by the heartbeat loop).
- Docs (`.env.example`, README, config-reference) and tests updated.

### Example

The import machine shows a recent `Last Heartbeat` and reports OS metadata:

```
$ cscli machines list
────────────────────────────────────────────────────────────────────────────────────────────────────────────
 Name              IP Address    Last Update           Status  Version  OS         Auth Type  Last Heartbeat
────────────────────────────────────────────────────────────────────────────────────────────────────────────
 blocklist-import  192.168.1.10  2026-07-10T06:52:18Z  ✔️      3.7.1    debian/13  password   43s
────────────────────────────────────────────────────────────────────────────────────────────────────────────
```

Rebased on latest `main`; 242 tests pass.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
