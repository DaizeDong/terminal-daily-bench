# [codex] improve upstream timeout handling

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

This change improves how the gateway handles upstream timeouts for both discovery and tool execution.

Before this patch, upstream discovery and tool calls were both using the same 30 second client timeout, which was too short for slower tool executions. The change introduces shared timeout constants, keeps discovery on the shorter 30 second budget, and extends tool calls to a 300 second request timeout so long-running upstream tools can complete.

While making that change, the review surfaced a regression in upstream error classification. The new exception-chain walker correctly followed wrapped timeout causes, but it also allowed nested DNS errors from exception context to outrank the closer timeout that actually caused the failure. In practice that meant a wrapped timeout could be recorded and returned as `UPSTREAM_DNS_FAILURE`, which would mislead both operators and users looking at `gateway_error_code` or persisted upstream runtime status.

The fix keeps the chain traversal, but classifies exceptions in chain order from the raised exception outward. That preserves the previous top-level behavior while still recognizing wrapped timeouts, including the `McpError` request-timeout form raised by the MCP client. A regression test now covers the case where a timeout is re-raised while handling a DNS failure, and the classification stays `UPSTREAM_TIMEOUT` as intended.

Validation was done with the focused upstream unit suite:

- `uv run pytest tests/unit/test_upstream.py tests/unit/test_upstream_admin.py`

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
