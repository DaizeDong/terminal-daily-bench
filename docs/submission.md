# Submitting to terminal-daily-bench

This page documents how to run the benchmark, submit results, and extend it with a
new scaffold/agent. Everything here maps to code in this bundle — no external
services or hidden APIs are required to score a patch.

The one invariant behind all of it: **a scaffold produces a candidate patch; the
execution gate is the sole reward authority.** A claimed reward is never trusted —
only the patch is replayed against protected tests. This is what makes
`false_accept = 0` a structural property rather than a promise.

---

## 1. Run a model on a task

The `tdb` CLI (`terminal_daily_bench/cli.py`) is the entry point.

```bash
pip install -e .                          # installs the `tdb` console script

export OPENAI_BASE_URL=https://api.openai.com/v1   # any OpenAI-compatible endpoint
export OPENAI_API_KEY=sk-...                        # bearer key, read from env, never stored

# Score a model on one task (single-shot patch scaffold + execution gate)
tdb run gpt-4o tasks/archive/td-fc90ea8b76d5f6b6

# Baseline: replay the task's own gold patch — proves the gate returns 1.0
tdb oracle tasks/archive/td-fc90ea8b76d5f6b6

# Multi-angle quality card over a results file (needs >=2 models)
tdb quality results.jsonl
```

`OPENAI_BASE_URL` defaults to `https://api.openai.com/v1` and can point at OpenAI,
OpenRouter, vLLM, LiteLLM, or a local server. The special model id `oracle` runs the
task's real `solution/oracle.patch` and needs no endpoint or key.

Scoring requires an **apptainer/singularity** host: harbor applies the patch inside
the task container, then re-lays the protected `tests/` and runs them under a network
cut. Override the singularity scratch paths with `TDB_SIF_CACHE`, `TDB_OVERLAY_DIR`,
and the work root with `TDB_WORK` if the defaults don't fit your host.

### The result record

Each run writes one JSON record (via `terminal_daily_bench/eval.py`) to `--out`
(default under `$TDB_WORK/results/`). Its shape:

```json
{
  "model": "gpt-4o",
  "task": "td-fc90ea8b76d5f6b6",
  "scaffold": "single_shot_patch",
  "reward": 1.0,
  "solved": true,
  "patch_applied": true,
  "error": null,
  "runtime_sec": 214.3,
  "false_accept_check": {
    "gate": "harbor_protected_tests",
    "reward_source": "result.json via harbor_score.read_harbor_reward",
    "protected_tests_relaid_by_harbor": true,
    "model_is_judge": false,
    "model_patch_touched_tests": false,
    "false_accept": 0
  }
}
```

`solved` is `reward >= 0.999`. Any failure — no diff produced, patch doesn't apply,
trial error, unparseable result — yields `reward 0.0` / `solved false` with the cause
in `error`. A crash never produces a positive score (BAD-safe by construction).

---

## 2. How scoring works — re-scored on ingest

The reward is read from harbor's structured `result.json` by
`harbor_score._read_harbor_reward` — the **same** reader the private admission gate
uses. The model is the *subject* under test; it is never the *judge*.

Why a patch can't cheat the score:

- The protected `tests/` are **re-laid by harbor from the trusted task package**
  *after* the patch is applied. A patch that edits `tests/` only changes an
  agent-side workspace that is discarded before scoring.
- Runtime egress is cut (`--network=none` / the offline `--ek` switch injected by
  `harbor_score._maybe_inject_offline_eks`), so a "fix" cannot phone home.
- The reward is byte-for-byte execution truth from `result.json`, not any string the
  model emitted.

### Submission ingest re-scores, too

When you submit results to the leaderboard, the same discipline applies at ingest.
In `web/submit_result.py`:

- `reward_claimed` is **advisory only** — it is validated against nothing.
- On record, the entry is stored as `verify_status="pending"` with
  `verified_reward=null`. The board trusts **only** `verified_reward`.
- A node worker replays the submitted `patch` through the execution gate and calls
  `apply_verified(store, sub_id, verified_reward)`, which flips the entry to
  `verify_status="verified"`.
- `rebuild_leaderboard(store, out)` folds only **verified** rows into a solved/attempt
  rate; a pending submission is listed but contributes `0` to any rate.

A fake `1.0` whose patch verifies `0.0` therefore contributes `0`. The claimed number
is never trusted; only its patch is replayed.

---

## 3. Submitting results

### Submission schema (JSONL, one line per `(model, task)` cell)

Required fields are enforced by `submit_result.validate` (the `REQUIRED` tuple):
`date`, `submitter`, `model`, `scaffold`, `task`, `patch`.

```json
{
  "date": "2026-07-22",
  "submitter": "your-handle",
  "model": "your-model",
  "scaffold": "your-scaffold",
  "task": "td-fc90ea8b76d5f6b6",
  "patch": "diff --git a/... b/...\n--- a/...\n+++ b/...\n@@ ...",
  "reward_claimed": 1.0,
  "harness_version": "v2",
  "signature": "<sha256>"
}
```

Validation rules:

- All six required fields must be present and non-empty.
- `patch` must be a unified-diff **string**.
- `task` must start with `td-`.
- `reward_claimed` (and any extra fields like `harness_version` / `signature`) are
  accepted but never trusted — they carry through as advisory metadata.

### CLI

`web/submit_result.py` reads a submission JSON from **stdin**:

```bash
# 1. Validate structure (exit 0 = valid, 1 = errors)
python web/submit_result.py validate < submission.json

# 2. Record as pending (appends to <store>/<date>.jsonl)
python web/submit_result.py record --store community_submissions < submission.json

# 3. (server-side, after re-scoring) fold verified rows into the board
python web/submit_result.py rebuild --store community_submissions --out web/leaderboard_data.json
```

`record` computes a content-addressed `id` (sha256 over the required fields, first 16
hex chars) for dedup and tamper-evidence, then writes an entry with
`verify_status="pending"`. The store defaults to `community_submissions/`.

For **live** (this-week) tasks the gold patch and protected test bodies are withheld
and scoring happens server-side: submit your patch and it is scored on our side.
**Archived** tasks (≥ 2 weeks old) ship in full for local reproduction.

---

## 4. Adding a scaffold / agent — the `HarnessAdapter` contract

Any coding-agent harness plugs in by implementing the contract in
`terminal_daily_bench/adapters/base.py`. The contract is deliberately narrow:

```
input  = (task dir, failing test ids, model id/endpoint)
output = (unified diff, telemetry)
```

An adapter **only produces a candidate patch — it must not score.** Keeping scoring
out of the adapter is what preserves `false_accept = 0` as harnesses are added.

### The interface

```python
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class AdapterResult:
    patch: str                                               # unified diff the harness produced
    telemetry: Dict[str, Any] = field(default_factory=dict)  # tokens, cost_usd, turns, wall_s
    error: Optional[str] = None

class HarnessAdapter(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def produce_patch(self, task_dir: str, failing_test_ids: List[str],
                      model: str, **kwargs: Any) -> AdapterResult:
        ...
```

Rules `produce_patch` must obey (from the base-class docstring):

- **MUST NOT** read or write the protected tests or the gold solution.
- **MUST NOT** compute a reward — scoring is done afterward by the execution gate.
- A harness failure should be returned as an `AdapterResult` with `error` set and an
  empty `patch` (a 0-reward attempt), **not** raised as a crash.

### Reference implementation

`terminal_daily_bench/adapters/single_shot.py` (`SingleShotAdapter`, `name =
"single_shot"`) is a complete, working example. It:

1. loads the task (`eval.load_task`),
2. finds the file(s) the reference solution touches (`eval.solution_target_files`),
3. reads those files out of the SIF image for context (`eval.extract_repo_files`),
4. builds a strict prompt (`eval.build_prompt`) asking for one unified diff,
5. calls the model (`eval.call_model`) and extracts the diff (`eval.extract_diff`),
6. returns an `AdapterResult` with `touches_tests` telemetry — no scoring.

`terminal_daily_bench/adapters/terminus.py` (`TerminusAdapter`, `name = "terminus"`)
is a stub documenting where to wire a multi-turn agent (terminus-2 / Claude Code /
Aider / OpenHands / SWE-agent). Any harness that accepts a custom OpenAI base URL can
drive an arbitrary model unchanged; implement its `produce_patch` to run your agent
CLI and return the resulting diff.

### Registering it

Adapters are discovered through the registry in
`terminal_daily_bench/adapters/__init__.py`:

```python
REGISTRY = {a.name: a for a in (SingleShotAdapter, TerminusAdapter)}
```

Add your adapter class to that tuple (and to `__all__`) with a unique `name`. Set the
`scaffold` field of your submission records to that `name` so the leaderboard groups
runs by `(submitter, model, scaffold)`.

---

## 5. Task package layout (reference)

Each task lives in `tasks/{archive|live}/<task-id>/` (see `tasks/SCHEMA.md`):

| Path | Purpose |
| --- | --- |
| `task.toml` | `environment.docker_image` (the SIF) · `environment.allow_internet` |
| `instruction.md` | the natural-language task shown to the model |
| `tests/` | `test.sh` runner · `test_outputs.py` protected assertions (archive only) |
| `environment/` | Dockerfile / build recipe |
| `solution/` | `solve.sh` · `oracle.patch` (archive only — withheld for live) |
| `PROVENANCE.json` | repo · pr_number · base/merge SHAs · upstream license |
| `record.json` | `task_id`, source PR metadata, `fail_to_pass` selectors |

The `fail_to_pass` selectors in `record.json` are the failing test IDs you pass as
`failing_test_ids` to an adapter. Live tasks ship the failing-test IDs but withhold
the `solution/` directory and the protected `test_outputs.py` body.
