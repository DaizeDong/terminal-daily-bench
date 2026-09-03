# Add Databricks AI Gateway as an agent provider

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

Adds `AGENT_PROVIDER=databricks`, routing every agent through a Databricks workspace's AI Gateway alongside the existing Anthropic and Bedrock paths.

Unlike Bedrock, PI has no native Databricks provider. So Baloo generates a `models.json` registering one at `~/.baloo/pi-databricks/` and points the subprocess at it with `PI_CODING_AGENT_DIR`.

```bash
AGENT_PROVIDER=databricks
AGENT_MODEL=sonnet
DATABRICKS_HOST=[redacted-url]
DATABRICKS_TOKEN=dapi...
```

## Three load-bearing details

Each was confirmed against a live workspace, and each is non-obvious enough to be worth stating:

- **`authHeader: true`** — the gateway requires `Authorization: Bearer` and 401s on the `x-api-key` header PI's built-in `anthropic` provider sends. `ANTHROPIC_BASE_URL` is *not* a shortcut: PI passes the built-in provider's own baseUrl explicitly, so requests still reach api.anthropic.com.
- **`compat.supportsEagerToolInputStreaming: false`** — the gateway's Anthropic translator rejects per-tool `eager_input_streaming` on the streaming+tools path every review uses. Without the flag, requests **hang** rather than fail, surfacing as an `agent_error` with no detail — exactly the shape [redacted-ref] stopped from auto-approving.
- **Unity Catalog model IDs** (`system.ai.claude-*`) — the flat `databricks-claude-*` names now return `501 NOT_IMPLEMENTED: Use Unity Catalog model services (v3)`, with or without the coding-agent-mode header.

## Security

The token is never written to disk: `models.json` references `DATABRICKS_TOKEN` by *name* and PI resolves it per request. The generated dir is bind-mounted read-only into the bwrap sandbox and lives outside `/tmp`, which the sandbox shadows with a tmpfs. `DATABRICKS_TOKEN` and `PI_CODING_AGENT_DIR` join the sandbox env allowlist; Baloo's GitHub/DB secrets are still scrubbed.

A security review of the branch found no HIGH/MEDIUM issues. It specifically cleared the one that mattered — `DATABRICKS_HOST` is **not** in `MUTABLE_KEYS`, so a dashboard admin cannot redirect the gateway base URL and capture the bearer token.

## Deliberate gaps

- **Cost reports `$0`.** Databricks bills DBUs at a per-contract rate, so there is no correct USD-per-token constant to hardcode, and a confidently wrong dashboard figure is worse than an absent one. Token counts are unaffected. Documented with the one-line path to changing it.
- **Static tier catalog, no discovery.** Listing models needs a `unity-catalog`-scoped token while inference only needs the gateway scope — discovery would demand broader credentials than running reviews does.
- **Premium pins `opus-4-6`.** On the test workspace `opus-4-7` and `opus-5` return `rate limit of 0` (not provisioned).

## Test

944 pass (916 baseline + 28 new), ruff and black clean.

Beyond unit tests, the real `get_agent_options()` → `PIAgentBase` RPC path was run against a live workspace using the generated config. That caught a bug the unit tests missed: the JSON-retry path spawns its own subprocess and did not inherit `PI_CODING_AGENT_DIR`, so it died with `Unknown provider "databricks"` while the main review succeeded — easy to miss. Both spawn sites now go through one `_with_provider_env()` helper, with a regression test naming that failure.

## Not in scope

The pi upgrade. `@mariozechner/pi-coding-agent` is deprecated and frozen at 0.73.1 (this repo's pin is its final release); development continues as `@earendil-works/pi-coding-agent` at 0.84.3. Baloo's RPC path works unchanged there, but the AST-tools extension is unverified, and the `models.json` env-var syntax changes (`"DATABRICKS_TOKEN"` → `"$DATABRICKS_TOKEN"`, failing as a 401 rather than a config error). Kept separate so a regression there is unambiguously the upgrade's fault.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
