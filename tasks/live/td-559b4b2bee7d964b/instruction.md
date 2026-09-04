# Custom HTTP headers for proxy and faucet API requests - Duplicate

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Description

### Summary

This change lets users attach extra HTTP headers to **proxy** traffic ([redacted-repo] API / `ProxyNetworkProvider`) and to **faucet** native-auth API calls. That supports authenticated or gated gateways (for example API keys) without changing proxy URLs.

### What changed

- **`--proxy-headers KEY=VALUE [KEY=VALUE ...]`**: Added wherever `add_proxy_arg()` is used. Values are parsed in `parse_proxy_headers()`; each token must contain `=` or the CLI raises a clear error.
- **Global application**: Before the subcommand runs, `cli.py` calls `config.set_proxy_headers(...)`. `get_config_for_network_providers()` passes those headers to the SDK via `NetworkProviderConfig(requests_options={"headers": ...})`, so SDK proxy clients pick them up consistently.
- **`mxpy faucet request`**: New **`--api-headers`** with the same `KEY=VALUE` form, forwarded to `NativeAuthClientConfig(extra_request_headers=...)`.
- **Environment model**: `env.mxpy.json` defaults and `MxpyEnv` include a **`proxy_headers`** field (documented as space-separated `KEY=VALUE` pairs in `get_proxy_headers()`).
- **`utils.parse_headers_list()`**: Shared parsing for `KEY=VALUE` lists.
- **`cli_get`**: Uses shared `add_proxy_arg()` so `get` subcommands get `--proxy-headers` like the rest of the CLI.
- **`cli_tokens`**: `TokenManagementController` now builds `ProxyNetworkProvider` with `get_config_for_network_providers()` so token flows respect the same header configuration.
- **Tests**: `test_proxy_extra_headers` asserts custom headers are passed through on `ProxyNetworkProvider` GETs (mocked `requests.Session.get`).
- **Docs**: `CLI.md` updated with the new flags across affected commands.

### Usage examples

```bash
mxpy get network-config \
  --proxy [redacted-url] \
  --proxy-headers "Api-Key=secret"
```

```bash
mxpy faucet request \
  --chain D \
  --api [redacted-url] \
  --api-headers "Api-Key=secret"
```

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
