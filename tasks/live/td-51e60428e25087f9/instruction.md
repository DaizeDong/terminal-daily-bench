# fix(groq): include usage in streamed chat completions

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

- request Groq's terminal usage chunk on streamed Chat Completions with `stream_options.include_usage`
- leave unary requests unchanged
- cover both request shapes with a focused unit test

## Why

Groq streams only include complete token usage when the request opts into the terminal usage frame. Without it, Celeste cannot populate complete usage data for streamed responses.

The override stays in Groq's provider client rather than the shared Chat Completions protocol, since support for this option is provider-specific.

## Validation

- `make ci` — Ruff, formatting, mypy, Bandit, coverage, and **585 tests passed**
- focused request/stream tests — **14 passed**
- live `qwen/qwen3.8-27b` stream with `thinking_budget="none"` returned `OK`, typed **17 input / 2 output tokens**, and retained the original usage payload in `metadata.raw_response`

Official contract: [Groq Chat Completions API reference]([redacted-url])

Follow-up to [redacted-ref]; no model-catalog or shared-protocol changes are included.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
