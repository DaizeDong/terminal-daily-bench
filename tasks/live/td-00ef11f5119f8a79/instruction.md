# fix(proxy): preserve agent-control outputs during slimming (takeover of [redacted-ref])

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

Takeover of [redacted-ref] (author @Komzpa, unresponsive 48h+ after the final review-blocker spec). All four of @Komzpa's original commits are preserved unchanged on this branch for attribution; this PR adds one maintainer commit on top implementing the remaining blocker, rebased onto current `main`.

Historical `response.create` slimming could replace the result of a namespaced collaboration call with an omission notice, losing the state returned by `wait_agent` or another hosted agent-control action. The base change (Komzpa) preserves `function_call_output` / `custom_tool_call_output` items whose `call_id` matches a historical `function_call` / `custom_tool_call` in the `collaboration` or `multi_agent_v1` namespace, deriving protected keys from the historical prefix of the original request input before `to_payload()` strips replay namespaces, protocol-qualified as `(output_type, call_id)`, across the service/bridge and direct WebSocket paths.

## Remaining blocker implemented (same-protocol duplicate call IDs)

Per the review spec in [redacted-url] (2026-08-26): with the previous set-based lookup, a historical namespaced `function_call` sharing a `call_id` with an ordinary `function_call` protected **both** `function_call_output` items, so a 33 KiB+ shell-style output escaped slimming and could keep the request above `_UPSTREAM_RESPONSE_CREATE_MAX_BYTES`, converting a previously-working lossy request into a hard upstream rejection.

The fix pairs outputs to calls with the same nearest-preceding-unmatched matcher as compact's `_compact_matching_tool_call_index` (the occurrence-pairing approach the review referenced):

- `_agent_control_tool_output_occurrences` (single-site in core `proxy.py`, imported by the service path) walks the historical prefix once: calls push a namespaced flag onto a per-`(protocol, call_id)` stack, each output pops its closest earlier unmatched call, and the resulting flags are indexed by **output occurrence**. An orphan output with no preceding unmatched call (real regime: session-anchor trimming in `websocket/mixin.py` or client partial resends drop the call from replay) pairs with nothing, consumes no call, and stays slimmable — a purely positional nth-output/nth-call counter would let the orphan steal the namespaced flag, preserving a 33 KiB shell output while slimming the actual agent-control result.
- Both `_slim_historical_response_input_item` implementations (core WebSocket path and service/bridge path, shared through the service facade) count output occurrences per `(protocol, call_id)` during the slim walk and preserve the nth output only when its paired call is namespaced.
- Threaded through all callers: `_stream_responses_with_session` -> `_prepare_websocket_response_create_payload`, `_prepare_response_bridge_request_state` (HTTP + WebSocket bridge), and `_response_create_text_with_size_guard`.
- OpenSpec delta updated: occurrence-pairing requirement sentence + "Same-protocol reused call IDs pair by occurrence" scenario, plus tasks/design entries. `openspec validate preserve-agent-control-output-slimming --strict` passes.

## Regression tests (parameterized over both paths)

- `test_slim_response_create_pairs_same_protocol_reused_call_id_by_occurrence` — namespaced `function_call` + ordinary `function_call` sharing one `call_id`; asserts the namespaced pair's 33 KiB output is preserved byte-identical while the ordinary output gets the omission notice. Parameterized over both slimmer paths (`service-bridge`, `core-websocket`) and both orderings (`namespaced-first`, `namespaced-second`).
- `test_slim_response_create_orphan_output_does_not_consume_namespaced_pairing` — orphan `function_call_output` (call trimmed from replay) followed by a namespaced call + output reusing the same `call_id`; asserts the orphan is slimmed and the namespaced pair's output is preserved. Parameterized over both slimmer paths; fails (`2 failed`) under a positional occurrence counter.
- `test_prepare_response_bridge_pairs_same_protocol_reused_call_id_by_occurrence` — same shape end-to-end through `_prepare_response_bridge_request_state`, parameterized over HTTP and WebSocket bridge transports, proving occurrence alignment survives wire namespace stripping.

All 8 new parameterized cases fail on the pre-fix code and pass with this change.

## Test plan

```text
$ uv run pytest tests/unit/test_proxy_utils.py -q
1150 passed

$ uv run ruff check app/core/clients/proxy.py app/modules/proxy/_service/response_create.py \
    app/modules/proxy/_service/streaming/helpers.py app/modules/proxy/_service/http_bridge/request_submit.py \
    tests/unit/test_proxy_utils.py
All checks passed!

$ uv run ruff format --check <same files>
5 files already formatted

$ make architecture-check
proxy architecture checks passed

$ uv run ty check
All checks passed!

$ openspec validate preserve-agent-control-output-slimming --strict
Change 'preserve-agent-control-output-slimming' is valid
```

## Type of change

- [x] `fix:` — bug fix (no behavior change beyond the bug)

Linked issue: none

## OpenSpec

- [x] This PR includes / updates an OpenSpec change
- [x] This PR touches a codex-faithful path and preserves upstream-equivalent behavior

Change directory: `openspec/changes/preserve-agent-control-output-slimming/`

Supersedes [redacted-ref].

🤖 Generated with [Claude Code]([redacted-url])


<!-- This is an auto-generated comment: release notes by coderabbit.ai -->

## Summary by CodeRabbit

* **Bug Fixes**
  * Historical outputs from supported agent-control calls are now preserved when response payloads are reduced.
  * Unrelated or oversized tool outputs continue to be shortened appropriately.
  * Improved handling for repeated call IDs, multiple output types, and both HTTP and WebSocket response paths.
  * Namespaced collaboration and multi-agent outputs are correctly matched before transmission.

* **Tests**
  * Added coverage for payload slimming, output matching, namespace handling, and bridge transport scenarios.

<!-- end of auto-generated comment: release notes by coderabbit.ai -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
