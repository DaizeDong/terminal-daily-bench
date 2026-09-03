# Add audit logging and fix type annotations

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary
- Add append-only audit log module with SHA256-hashed queries, JSON Lines format, session ID tracking
- Refactor provider interface: run() wraps execute() with automatic audit logging
- Fix type annotation warnings across all providers with type: ignore[assignment] casts

## Files changed (10 files, +229 -28)
- eagleosint/audit.py — new audit log module
- eagleosint/plugin.py — run() method + audit integration
- providers: bitly, github, godorker, mailfinder, network, phoneinfo, userrecon — type casts
- tests/test_audit.py — 9 tests

## Test plan
- [x] All 123 tests pass
- [x] Audit log append-only, SHA256 deterministic
- [x] Provider wrappers correctly cast result types

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
