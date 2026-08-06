# Submitting to terminal-daily-bench

This page documents how to run the benchmark, submit results, and extend it with a
new scaffold/agent. Everything here maps to code in this bundle — no external
services or hidden APIs are required to score a patch.

The one invariant behind all of it: **a scaffold produces a candidate; the execution
gate is the sole reward authority.** A claimed reward is never trusted. Protected-test
replay prevents claim bypass; semantic verifier false-accept is a separate empirical
quantity and is not inferred to be zero.

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
    "scope": "protected_test_replay_integrity",
    "claim_acceptance_without_replay": false,
    "semantic_false_accept": null,
    "false_accept": 0
  }
}
```

`solved` is `reward >= 0.999`. Any failure — no diff produced, patch doesn't apply,
trial error, unparseable result — yields `reward 0.0` / `solved false` with the cause
in `error`. A crash never produces a positive score (BAD-safe by construction).

---

## 2. How scoring works — deterministic execution gate

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

### Recording is not replay

When you submit results, `web/submit_result.py` records the patch for later review:

- `reward_claimed` is **advisory only** — it is validated against nothing.
- On record, the entry is stored as `verify_status="pending"` with
  `verified_reward=null` and no `false_accept` value.
- The public bundle **does not run a replay worker**. Pending rows remain in a
  separate audit view and are excluded from the verified ranking.
- An operator may publish a completed gate receipt after replaying the submitted
  `patch`. Only receipt-backed rows appear in `community_verified`; unreviewed rows
  remain in `community_pending`.

A fake `1.0` therefore cannot enter a ranking. If an operator later replays that
patch, only the execution-gate receipt can determine its verified reward.

---

## 3. Submitting results

### Submission schema (JSONL, one line per `(model, task)` cell)

Required fields are enforced by `submit_result.validate` (the `REQUIRED` tuple):
`date`, `submitter`, `model`, `model_build`, `scaffold`, `harness_version`, `task`,
`patch`.

```json
{
  "date": "2026-07-22",
  "submitter": "your-handle",
  "model": "your-model",
  "model_build": "your-model@immutable-build-id",
  "scaffold": "your-scaffold",
  "harness_version": "your-scaffold@immutable-version",
  "task": "td-fc90ea8b76d5f6b6",
  "patch": "diff --git a/... b/...\n--- a/...\n+++ b/...\n@@ ...",
  "reward_claimed": 1.0
}
```

Validation rules:

- All eight required fields must be present, typed and bounded.
- `patch` must be a non-empty unified-diff string no larger than 2 MiB.
- Binary patches, test edits, path traversal and Git-metadata edits are rejected.
- `task` must match the Terminal Daily id grammar and `date` must be ISO format.
- `reward_claimed` is accepted but never trusted. Receipt signatures are produced
  by the official replay worker; a submitter must not provide one.
- The surrounding deployment auth layer supplies `authenticated_submitter`
  separately. A client-provided value with that name is rejected.

### CLI

`web/submit_result.py` reads a submission JSON from **stdin**:

```bash
# 1. Validate structure (exit 0 = valid, 1 = errors)
python web/submit_result.py validate < submission.json

# 2. Record as pending (appends to <store>/<date>.jsonl)
python web/submit_result.py record --store community_submissions \
  --authenticated-submitter github:YOUR_LOGIN < submission.json

# 3. After an operator replay receipt exists, rebuild the two public views
python web/submit_result.py rebuild --store community_submissions \
  --manifest /read-only/suite-manifest.json \
  --trusted-keys /read-only/replay-authorities.json \
  --out web/leaderboard_data.json
```

`record` computes a full SHA-256 content id over the patch, authenticated submitter,
model build, harness version and task, stores the patch as a private content-addressed
blob, and atomically writes `verify_status="pending"`. Only one attempt is accepted per
authenticated `(suite, submitter, model build, harness version, task)` cell. An official
operator freezes suite/task/verifier, runner, Harbor and image digests with
`web/replay_worker.py freeze`, runs the queue on a compute node, and persists a signed
v2 receipt before promotion is possible. The promoter verifies the Ed25519 signature
with a pinned public key and re-validates the receipt on every leaderboard rebuild.

A replay receipt is still insufficient for a community ranking until every task in
the same frozen roster has one valid receipt. Partial coverage, duplicate cells,
cross-date rows, invalid/expired leases and self-reported-only identities stay in
`community_pending`. Community replay-verified rows are explicitly separate from
project-controlled official evaluations.

### Operator-only replay authority

Install the replay-only receipt dependency on the operator image:

```bash
pip install -e '.[replay]'
```

Receipt signing and verification use Python `cryptography`'s in-process Ed25519
primitives. `web/receipt_auth.py` does not search `PATH` and does not invoke an
external OpenSSL process. A missing or invalid replay extra fails closed before a
receipt can be signed or accepted.

The operator must prepare three read-only inputs before `run`:

- a v2 frozen suite manifest created with `freeze --execution-policy ...`;
- an Ed25519 private key readable only by the worker (`0600`), never by ingest or
  the Harbor child;
- a public-key registry (`terminal-daily-receipt-authorities/v1`) pinning the
  `key_id`, Ed25519 public PEM and its DER SHA-256.

The execution-policy JSON pins the exact replay runner digest, Harbor executable
digest/version, backend, `network_policy="no-network"`, `canary_required=true`, the
receipt `key_id` + public-key SHA-256, and one runtime-image SHA-256 per task. It must
also pin `container_runtime_path` as a canonical absolute path, the runtime binary's
SHA-256, its exact `--version` output, and its kind (`apptainer` or `singularity`).
The worker must not own the runtime binary or its parent directory, must be unable to
write either (including through ACLs or supplementary groups), and rejects group- or
world-writable modes on both.

Before each Harbor execution, the worker copies the expected SIF into the
worker-private attempt directory as a read-only file and compares its SHA-256 with
the frozen task policy. It hashes the copy immediately before Harbor and again at the
Harbor-to-canary boundary. It validates the pinned runtime before Harbor and again in
the canary preflight, then requires the canary-preflight snapshot to match the
pre-Harbor snapshot before returning a receipt. Any image drift or runtime snapshot
mismatch fails closed.

The Harbor authority binding now fails closed in code. Policy and receipts bind the
canonical `harbor_binary_path`, launcher SHA-256/version, canonical
`harbor_package_root`, SHA-256 of the complete installed Harbor package and
network-patch tree, and immutable runtime-control facts. The worker recomputes and
compares those facts before and after replay, so an unchanged launcher cannot mask
changed imported modules or backend patches.

The authoritative Harbor result boundary opens the sole contained `result.json`
through a root/run/result `O_NOFOLLOW` file-descriptor chain, rejects symlinks and
hardlinks (`st_nlink != 1`), checks inode/device/link-count stability, and limits the
snapshot to 16 MiB. Reward schema validation and receipt hashing consume the same
already-open snapshot bytes; the attacker-influenced pathname is never reopened.

`freeze` validates the authority pin against `--trusted-keys`. `run` additionally
requires `TDB_EGRESS_CANARY_HOST` and `TDB_EGRESS_CANARY_PORT`: the same pinned image
must reach that endpoint in the control run and fail from an Apptainer
`--net --network none` run. Missing runtime image bytes, a missing canary endpoint,
an unreachable control, or an unproven isolated failure is an infrastructure error,
never a zero reward or verified receipt.

This repository contains enforcement code, fake-runner tests, and Fake Harbor tests.
They prove only code and command boundaries; they are **not** evidence of a production
replay, real network isolation, or a correctly separated receipt authority. The bundle
does **not** contain a production private key, production policy, or deployment audit.

The signer and public ingest/promoter must also be different OS UIDs (or equivalent
service identities). The private key is a signer-only read-only secret mount; the
manifest and public-key registry are read-only mounts for the promoter. File modes
such as `0600`/`0444` do **not** create isolation when every process has the same
owner, because that owner can replace or chmod the files. At startup the worker
rejects signing keys under its submission store, work directory, trusted task tree,
or source checkout and records UID/mode facts in the signed receipt. Those facts aid
an external deployment audit; they are not a substitute for distinct identities,
ACLs/read-only mounts, and an actual canary run. A same-UID deployment remains a
production blocker.

Accordingly, `replay_worker.py run` stops at `receipt_ready`; that state remains in
the unranked pending view and keeps `verified_reward = null`. The separate promoter
identity runs `submit_result.py promote --store ... --id ... --manifest ...
--trusted-keys ...`. Promotion re-verifies every receipt binding and rejects root or
the signer UID before changing the row to `verified`.

More generally, production replay remains a blocker until the official compute worker
completes a real Harbor replay, demonstrates both a reachable control canary and a
blocked isolated canary, and passes an operator audit of distinct signer/promoter UIDs,
the signer-only private-key mount, and read-only manifest/public-key mounts. No
community row should be described as replay-verified before all of those conditions,
and before the full Harbor package/tree and single-snapshot result controls have been
exercised and audited with the real installed package and replay artifacts.

For **live** tasks the gold patch and protected bodies are withheld. Submission alone
does not score them; an official operator replay is required.
**Archived** tasks (≥ 2 weeks old) ship in full for local reproduction.

---

## 4. Adding a scaffold / agent — the `HarnessAdapter` contract

Any coding-agent harness plugs in by implementing the contract in
`terminal_daily_bench/adapters/base.py`. The contract is deliberately narrow:

```
input  = (task dir, failing test ids, model id/endpoint)
output = (unified diff, telemetry)
```

An adapter **only produces a candidate — it must not score.** Keeping scoring out of
the adapter preserves the protected-replay boundary as harnesses are added.

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

Harbor-native `claude-code` and `codex` adapters are also registered. They return a
declarative `HarborRunSpec`; Harbor owns the multi-turn CLI loop and workspace edits,
while the Terminal Daily runner remains the only reward reader. Their command boundary
is tested locally, but real provider/container cells still require the runtime described
in README.

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
