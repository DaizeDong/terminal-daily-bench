# Protocol-aware campaigns

`tdb campaign` runs a resumable sparse matrix without changing the scoring
authority. Each eligible cell invokes the existing single-cell evaluator once,
produces its own one-trial Harbor aggregate, and must pass the same aggregate and
post-Harbor SIF checks as `tdb run`.

The planner joins model and agent profiles only when they share an explicit API
protocol. It records incompatible combinations in the manifest but never starts
them.

## Definition

Campaign definitions are JSON with schema `tdb-campaign/v1`. Models may be listed
directly or imported from a digest-pinned, credential-free model catalog.

```json
{
  "schema_version": "tdb-campaign/v1",
  "campaign_id": "gateway-2026-08-06",
  "model_catalog": {
    "path": "./model-catalog.json",
    "sha256": "<sha256-of-file-or-canonical-model-array>",
    "provider": "gateway",
    "base_url": "https://gateway.example/v1",
    "base_url_by_protocol": {
      "anthropic-messages": "https://gateway.example"
    },
    "estimated_cost_usd": 0.50,
    "anthropic_messages_allowlist": ["explicitly-probed-claude-model"]
  },
  "agents": [
    {"id": "patch", "harness": "single_shot"},
    {"id": "codex", "harness": "codex"},
    {"id": "claude", "harness": "claude-code"},
    {
      "id": "terminus-chat",
      "harness": "terminus-2",
      "protocols": ["openai-chat-completions"],
      "agent_kwargs": {"max_turns": "50"}
    }
  ],
  "tasks": [
    {
      "id": "td-example",
      "path": "./tasks/archive/td-example",
      "task_sif": "/absolute/path/td-example.sif",
      "task_sif_sha256": "<64-hex-digest>"
    }
  ],
  "seeds": [null],
  "execution": {
    "max_workers": 4,
    "max_cells": 1000,
    "budget_usd": 100.0,
    "provider_concurrency": {"gateway": 2},
    "call_timeout": 180,
    "harbor_timeout": 1800,
    "max_tokens": 4096
  }
}
```

The catalog importer accepts either a raw OpenAI-style `/v1/models` object with a
`data` array or a `terminal-daily-gateway-model-catalog-v1` wrapper with a
`models` array. The frozen wrapper must bind its canonical `models_sha256`, HTTP
status/counts, and declare that no credential value or routing data was persisted.
The importer recognizes only strict boolean `capabilities.chat` and
`capabilities.responses` markers. Anthropic
Messages compatibility is never inferred from a model name: it requires an
explicit `anthropic_messages_allowlist` entry. Unknown catalog metadata is not
copied to the campaign manifest.

Direct model profiles use this shape:

```json
{
  "id": "gateway-gpt-build-17",
  "provider": "gateway",
  "model": "openai/gpt-build-17",
  "build": "immutable-build-17",
  "protocols": ["openai-chat-completions", "openai-responses"],
  "base_url": "https://gateway.example/v1",
  "base_url_by_protocol": {
    "anthropic-messages": "https://gateway.example"
  },
  "model_by_harness": {"codex": "gpt-build-17"},
  "estimated_cost_usd": 0.50
}
```

Supported built-in protocol contracts are:

- `single_shot`: `openai-chat-completions`
- `codex`: `openai-responses`
- `claude-code`: `anthropic-messages`
- `terminus-2`: `openai-chat-completions` or `openai-responses`; its model name
  must be LiteLLM provider-prefixed

The legacy `terminus` adapter remains an unwired stub and has no eligible
protocol.

## Plan, run, and resume

Freeze and inspect a credential-free plan first:

```bash
tdb campaign campaign.json --state .tdb_campaign/run-001 --dry-run
```

Execute it after operator preflight:

```bash
tdb campaign campaign.json --state .tdb_campaign/run-001 --resume
```

Successful cells are immutable and always skipped on resume. Failed or blocked
eligible cells require an explicit retry:

```bash
tdb campaign campaign.json --state .tdb_campaign/run-001 \
  --resume --retry-failed --retry-blocked
```

`--max-workers`, `--max-cells`, and `--budget-usd` can tighten the limits frozen
in the definition. A budget is reservation-based: every attempt consumes the
model profile's `estimated_cost_usd`, including failed and interrupted attempts.
If a budget is active and a profile has no estimate, that cell is blocked rather
than guessed free.

The state directory is mode `0700` and contains:

- `manifest.json`: immutable profile, capability, task-tree, SIF, and cell-ID
  bindings; endpoint URLs appear only as SHA-256 fingerprints
- `checkpoint.json`: atomic attempt history and `SUCCESS`, `FAILED`, `NOT_RUN`,
  or `BLOCKED` state
- `attempts/`: one evaluator result per attempt, bound by digest in the checkpoint
- `results.jsonl`: only clean `SUCCESS` rows, with model/agent profile and cell IDs

An incompatible model-agent pair is recorded as
`SKIPPED_INCOMPATIBLE_PROTOCOL`. A clean reward of zero is a successful,
authoritative unsolved cell (`CLEAN_SCORED_UNSOLVED`); setup, agent, timeout,
Harbor, aggregate-authority, and SIF failures never become score-zero rows.

Credentials do not belong in a campaign or catalog. The evaluator continues to
select them from the adapter's environment at cell execution time, and manifests
record only accepted environment-variable names.
