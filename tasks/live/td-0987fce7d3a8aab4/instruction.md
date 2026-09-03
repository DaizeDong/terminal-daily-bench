# fix(proxy): defer keyed pre-created retry health writes until settlement

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

The HTTP bridge's pre-created retry branches (`wait_for_model_capacity`, owner-pinned quota, and the generic retryable arm in `_process_parsed_http_bridge_upstream_event`) awaited `_handle_stream_error` directly, mutating load-balancer account health (`mark_rate_limit` / `mark_quota_exceeded` / `record_error`) while the request's API-key reservation was still unsettled. Each arm then set `account_health_error_handled=True`, which suppresses the finalizer's settlement-gated health write — so the unordered write was the *only* write, and a successful retry penalized the account without any settlement at all. This bypasses the settlement-ordering invariant the keyed SSE retry path already enforces via `_handle_or_defer_keyed_stream_health` and `defer_account_health_writes`.

Now keyed requests queue the classified write on the request state (`deferred_keyed_stream_health`) and drain it after the reservation settles (`_finalize_websocket_request_state`) or its fallback release commits (`_release_websocket_request_state_reservation`); when neither confirms, the penalty stays unapplied. Unkeyed requests keep the immediate write. Backoff and stream-health lanes are independent after settlement (a failed backoff write cannot orphan the deferred health write), each drain attempt runs as an owned shielded task so caller cancellation cannot abandon a half-applied penalty for a later drain to replay, and a health write that fails after a committed settlement is logged and dropped so it cannot abort the remaining terminal finalization or leak an unowned retry entry.

## Type of change

- [x] `fix:` — bug fix (no behavior change beyond the bug)

Linked issue: none (discovery finding `CLB-[redacted-sha]-01`)

## OpenSpec

- [x] This PR includes / updates an OpenSpec change

Change directory: `openspec/changes/defer-bridge-precreated-health-until-settlement/` (modified capability: `api-keys`; `openspec validate defer-bridge-precreated-health-until-settlement --type change --strict` passes). Extends the existing "Stream reservation settlement is detached from the response path" requirement to the bridge's pre-created retry arms, independent post-settlement drain lanes, and failed-write isolation.

## Changes

- `upstream_events.py`: the three pre-created retry arms route through a new `_handle_or_defer_precreated_stream_health` — keyed: queue + suppress duplicate terminal write; unkeyed: unchanged immediate write
- `support.py`: `_DeferredKeyedStreamHealthPenalty` + `_WebSocketRequestState.deferred_keyed_stream_health`
- `api_key_usage.py`: `_drain_deferred_keyed_stream_health` (owned shielded attempt per entry, consumed exactly once; an attempt that fails after committed settlement is logged and dropped) + drain after fallback release, in a `finally` lane independent of the backoff drain
- `websocket/mixin.py`: drain after committed settlement in the finalizer, same independent-lane shape as the SSE retry path's settle-then-flush
- `openspec/changes/defer-bridge-precreated-health-until-settlement/`: delta spec for the `api-keys` settlement-ordering requirement
- 7 unit regressions: keyed capacity + keyed usage-limit branches through the real event processor (red pre-fix: `_handle_stream_error` awaited while the reservation was open), settle-then-health order on release, unconfirmed release leaves health unapplied and retained, backoff-failure lane independence, cancellation consumes the entry exactly once, failed write dropped without aborting the drain

## Test plan

```
uv run pytest tests/unit/test_proxy_http_bridge.py -q
# 678 passed, 1 failed: test_stream_via_http_bridge_fails_closed_before_file_affinity_when_previous_response_owner_misses
# — pre-existing on clean upstream/main ([redacted-sha]) in this environment, unrelated to this diff

uv run pytest tests/unit/test_proxy_utils.py -k "settle or settlement or deferred_backoff or account_health" -q   # 48 passed
uv run pytest tests/unit/test_api_keys_service.py -q                                                              # 86 passed

uv run ty check          # All checks passed!
uv run ruff check app/ tests/unit/test_proxy_http_bridge.py
uv run ruff format --check app/modules/proxy/_service/ tests/unit/test_proxy_http_bridge.py
python scripts/check_proxy_architecture.py   # proxy architecture checks passed
openspec validate defer-bridge-precreated-health-until-settlement --type change --strict
```

Intentionally unrun locally: full `local-ci`, integration suite (covered by required CI).

## Related work

- [redacted-ref], [redacted-ref], [redacted-ref] (merged) enforce the same settle-before-health invariant on the websocket finalizer, compact failover, and keyed SSE mid-loop paths; [redacted-ref] was superseded by [redacted-ref]. This PR closes the remaining gap in the HTTP-bridge pre-created retry arms.
- [redacted-ref] (open) is adjacent but a different invariant (account-neutral classification of model-scoped rejections); no overlap in touched lines.

## Checklist

- [x] Title is in Conventional Commits format (`<type>(<scope>)?: <subject>`).
- [x] Added or updated tests covering the change.
- [x] Ran the relevant focused local subset above.
- [x] CHANGELOG is **not** edited by hand (release-please handles it).

<!-- This is an auto-generated comment: release notes by coderabbit.ai -->
## Summary by CodeRabbit

- **Bug Fixes**
  - Improved account-health handling during WebSocket and HTTP bridge requests.
  - Ensured usage-limit, model-capacity, and retry-related health updates wait for API-key reservation settlement.
  - Prevented health updates from being lost when reservation release or backoff persistence fails.
  - Improved cancellation handling so pending health updates complete reliably and are processed only once.
  - Preserved immediate health updates for requests without API-key reservations.
<!-- end of auto-generated comment: release notes by coderabbit.ai -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
