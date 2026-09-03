# fix: complete registration reliability repair plan

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

Implements the complete 12-item non-privacy reliability/correctness repair plan audited against baseline `[redacted-sha]`.

### Registration correctness
- Make uncertain outcome classification stage-driven instead of proxy-error-driven.
- Route auto/direct/single/pool through the same stage-aware batch engine.
- Move real browser stage markers to side-effect boundaries: email only after mailbox/input preparation plus a side-effect-free email readiness probe; verification code after a side-effect-free OTP readiness probe and before input events that can auto-submit; profile only after Cloudflare/submit readiness and immediately before the commit-capable click call.
- Stop broadly swallowing SSO-wait exceptions: retry only explicitly transient browser-context failures with a bounded consecutive-error policy; rethrow proxy/retry/unknown failures and preserve the last recoverable cause on timeout.
- Make generic POST non-replayable by default; allow direct replay only for explicitly read-only POST operations.

### Parallel consistency / observability
- Preserve and aggregate `uncertain_count` across workers.
- Surface `uncertain` in WebUI status.
- Add process-shared, provider-scoped domain rotation and inject it into each isolated mail module.

### Provider/config/runtime correctness
- Make Cloudflare `query-key` behavior consistent across main mail flow, compatibility client, and debug CLI.
- Split proxy preflight `reachable` from `usable`; blocked/4xx/5xx targets no longer make top-level preflight `ok` true.
- Add bounded sing-box startup retries with per-attempt cleanup for the free-port/startup race window.
- Reject unknown manual config keys consistently.

## Validation

GitHub Actions repair bots used exact-match guarded patches and committed source changes only after the full test suite passed.

Final strict audit result:
- `169 passed`
- `1 warning` (existing embedded-JS regex `SyntaxWarning` at `registration_browser.py:466`)
- Targeted regression coverage includes uncertain aggregation, isolated-mail shared domain allocation, query-key semantics, non-replayable POST, strict config keys, preflight usability, WebUI uncertain display, unified batch engine, SSO consecutive-error reset/exception whitelist, strict email/verification/profile commit boundaries, and sing-box startup retry/cleanup.

Multiple post-green source audits intentionally looked for integration gaps beyond test success. They found and fixed isolated `mail_service` allocator injection, intermittent SSO errors incorrectly accumulating as consecutive errors, remaining coarse verification/profile boundaries and unknown-exception behavior, and the last coarse email commit boundary. Each accepted correction was followed by a complete green test run; failed candidate patches were blocked before commit.

## Scope

Privacy/security findings explicitly excluded by the requested plan are intentionally untouched. All temporary repair/audit scripts and workflows were removed from the final branch diff before this PR was finalized for review.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
