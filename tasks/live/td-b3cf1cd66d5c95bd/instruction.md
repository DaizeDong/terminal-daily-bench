# fix: consolidate small correctness fixes

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

Consolidates a reviewed set of small correctness and documentation fixes onto current `main`:

- preserve retry/cache inputs and normalize edge-case message content
- make missing tool calls retryable for OpenAI-compatible and Mistral handlers
- return all Anthropic parallel tool errors and disable parallel calls for forced single-tool requests
- harden streaming JSON, partial models, citations, and lazy handler registration
- avoid mutating cached schemas and caller-owned Gemini configuration
- fix Bedrock default model forwarding, OpenAI audio formats, empty batch objects, and CLI file access
- redact additional credential aliases and declare the runtime `regex` dependency explicitly
- refresh Cerebras and Google/Vertex documentation

## Consolidated PRs and issues

Canonical patchsets incorporated and intentionally superseded by this [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref]

Duplicate or narrower alternatives superseded by the consolidated implementation:

[redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref]

Issues fixed:

[redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref]

## Validation

- `uv run pytest <all 22 changed test modules> -q`: 688 passed, 2 skipped
- targeted regression reruns: 34 passed
- `uv run ruff format --check [redacted-repo] tests`: passed
- `uv run ruff check [redacted-repo] tests`: passed
- scoped `uv run ty check` for every changed production and test module: passed
- `uv lock --check`: passed
- commit hooks: Ruff lint/format, lock check, dependency installation, requirements export, and ty all passed
- broader `pytest tests/ -k 'not llm and not openai' -q`: 3050 passed, 229 skipped; 48 unrelated failures remain in pre-existing docs snippets and live provider calls using unavailable/retired models
- repository-wide `ty check --config-file ty-tests.toml` remains baseline-red with 265 unrelated diagnostics in notebooks, optional examples, and scripts

## Skipped items

- [redacted-ref] and [redacted-ref]: token-usage accumulation remains semantically unresolved by [redacted-ref]; merging a partial fix would make the API harder to correct later
- [redacted-ref]: broad 38-package dependency bump
- [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref]: provider additions requiring dedicated ownership and integration validation
- [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref]: architectural changes and mode/client contract work
- [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref] [redacted-ref]: nontrivial security, streaming, batch, or Bedrock behavior changes
- example/resource PRs remain open for separate product/editorial review

No release, tag, PyPI publication, deployment, or social post is included.

<!-- CURSOR_SUMMARY -->
---

> [!NOTE]
> **Medium Risk**
> Touches core v2 retry, caching, streaming parsers, and multiple provider handlers; changes are targeted correctness fixes with broad test coverage but wide blast radius across integrations.
> 
> **Overview**
> This PR bundles many small **runtime and integration fixes** across v2, plus doc and dependency updates.
> 
> **Retries, caching, and messages:** Retry paths now get isolated copies of `messages` / `contents` / `chat_history` so reask mutations do not break cache keys or caller-owned lists. Message dumping keeps legacy `function_call` when content is empty; merging treats `None` content as empty.
> 
> **Tool-call parsing and reasks:** OpenAI-compatible and Mistral handlers raise retryable `ResponseParsingError` when there are no tool calls, and reask flows fall back to user corrections instead of iterating `None`. Anthropic forced single-tool requests set `disable_parallel_tool_use`, and parallel-tool reasks emit a `tool_result` for every `tool_use` id.
> 
> **Streaming / DSL / registry:** JSON stream extraction validates balanced spans and keeps scanning past non-JSON brace blocks. Partial streaming uses per-context recursion guards, builds partial instances for incomplete nested/list items, and final-validates from raw JSON so explicit `null` is preserved. Citation fuzzy matching escapes regex metacharacters; lazy mode-handler registration is locked against concurrent first access. OpenAI tool schemas are copied before adding `strict` so the LRU cache is not poisoned; Gemini `generation_config` is copied before in-place mapping.
> 
> **Other runtime:** Batch parsing accepts `{}` for models with defaults. CLI file listing uses SDK attribute access. Bedrock auto-client forwards default `model`. OpenAI audio maps WAV/MP3 only. Debug logging redacts more credential key aliases. `regex` is a direct dependency.
> 
> **Docs:** Cerebras examples use `gpt-oss-120b`; Google docs clarify provider prefixes; Vertex `from_genai()` example passes `model` outside the client constructor. **CHANGELOG** [Unreleased] entries document the above.
> 
> <sup>Reviewed by [Cursor Bugbot]([redacted-url]) for commit [redacted-sha]. Configure [here]([redacted-url]).</sup>
<!-- /CURSOR_SUMMARY -->

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
