# Task format

Every terminal-daily-bench task is a self-contained, **harbor-native** package: one
directory per task under `tasks/{archive|live}/<task-id>/`. A task id looks like
`td-fc90ea8b76d5f6b6`. This page documents the on-disk schema, the difference
between the *archive* and *live* releases, how scoring re-lays the protected tests,
and the 2-week archive window.

Everything below reflects the code in this bundle
(`terminal_daily_bench/`, `tasks/publish_tasks.py`, `web/submit_result.py`); no APIs
are invented.

## Package layout

```
tasks/archive/<task-id>/
  task.toml           environment.docker_image · environment.allow_internet · timeouts
  instruction.md      the natural-language task shown to the model (de-identified)
  tests/              test.sh (runner) · test_outputs.py (protected assertions) · test_patch.diff
  environment/        Dockerfile (build recipe: base image + repo @ base_sha + deps)
  solution/           solve.sh (git apply driver) · oracle.patch (the gold fix)
  PROVENANCE.json     source_repo · source_ref · source_license_spdx
  record.json         machine metadata (task_id, repo, pr_number, SHAs, f2p selectors)
```

The canonical short schema also lives in [`tasks/SCHEMA.md`](../tasks/SCHEMA.md).

### `task.toml`

Harbor's task descriptor. The fields the eval framework actually reads live under
`[environment]` (`terminal_daily_bench/eval.py::load_task`):

```toml
schema_version = "1.1"

[task]
name = "terminal-daily/td-fc90ea8b76d5f6b6"
description = "Validate format string keys in logger.add() for early error feedback"
keywords = ["C5", "C4"]                 # capability labels

[metadata]
source_repo = "Delgan/loguru"
pr_number = 1451
base_sha  = "2abeb0fa6d7be4b0455c6e0b580b1e9dab19005e"
merge_sha = "b782e56fcf07fecf9545ff6ee2350baacb0968ce"
oracle_patch_sha256 = "1e843ef7617ac857dfb2139ac3e2f2a6a328b4fc5e1848f8fd021b9f3b0fdda8"
difficulty = "medium"
network_profile = "build-online/run-offline"

[environment]
docker_image  = "environment/Dockerfile"   # portable ref: build from the task Dockerfile
allow_internet = false                      # run-offline -> egress cut at scoring time
cpus = 1
memory_mb = 4096
storage_mb = 16384
```

- **`environment.docker_image`** is rewritten to the portable value
  `"environment/Dockerfile"` on publish (see `publish_tasks.py::_sanitize_task_toml`).
  The host-specific absolute `.sif` path is never shipped; you build the image from
  the task's own `environment/Dockerfile`.
- **`environment.allow_internet`** drives the runtime network cut. When `false`, the
  singularity backend gets the no-network `--ek` switch injected automatically
  (`harbor_score.py::maybe_inject_offline_eks`), physically cutting egress during
  scoring.

### `instruction.md`

The natural-language problem statement shown to the model. Upstream provenance
(origin remote, project name, commit ids) is stripped ("de-identified") so the task
is solved from the working tree and description alone.

### `tests/`

The protected verification suite. It is re-laid from the trusted package **after** a
model's patch is applied, so a patch can never tamper with the judge.

- **`test.sh`** — the runner. It installs `pytest` + project test extras, applies
  anti-tamper hardening (removes stray `conftest.py`/`sitecustomize.py`, unsets
  `PYTHONPATH`, pins `PATH`), runs `pytest -q -rA /tests/test_outputs.py`, and writes
  the reward (`1` on all-pass, else `0`) to `/logs/verifier/reward.txt`.
- **`test_outputs.py`** — the protected assertions. It carries the `FAIL_TO_PASS` /
  `PASS_TO_PASS` selectors, lands the PR's `test_patch.diff` onto the tree
  (`_ensure_tests_applied`), then runs the fail-to-pass tests. **Archive only** — the
  body is withheld for live tasks.
- **`test_patch.diff`** — the PR's test diff, applied at verify time so the test
  signal is never baked into the environment image.

### `environment/Dockerfile`

The build recipe (parity/audit artifact). Layered: a language/system base image, the
repo cloned at `REPO_BASE_SHA` with its `.git` re-initialized to a single `baseline`
commit, then search-based dependency resolution (`pip install -e .` / `pip install .`
/ `-r requirements.txt` — first shape that builds wins; it hard-fails if none do).

### `solution/` (archive only)

- **`solve.sh`** — the git-apply driver. It `git apply --check`s `oracle.patch`,
  applies it (`--3way`, falling back to plain apply), treats an already-applied tree
  as an idempotent no-op, and **fails loudly** if the patch is genuinely inapplicable
  (never pretends success on an unpatched tree). If the patch touches native/build
  inputs it rebuilds the extension offline.
- **`oracle.patch`** — the gold fix from the merged PR. Its sha256 is recorded in
  `task.toml`/`record.json` (`oracle_patch_sha256`).

During scoring the model's own diff is written to this same
`solution/oracle.patch` path in a **run copy** of the task, so `solve.sh` applies the
model's patch exactly as it would the gold one.

### `PROVENANCE.json`

Upstream attribution shipped with every task (archive and live):

```json
{
  "source_repo": "Delgan/loguru",
  "source_ref": "b782e56fcf07fecf9545ff6ee2350baacb0968ce",
  "source_license_spdx": ""
}
```

Tasks are derived only from permissively-licensed repositories.

### `record.json` (archive only)

Portable machine metadata. Host-specific / internal build fields (`image_ref`,
`image_build`, `generator`, `repro`, `netns_available`, `needs_network`) are stripped
on publish (`publish_tasks.py::_sanitize_record`). What remains:

```json
{
  "task_id": "td-fc90ea8b76d5f6b6",
  "repo": "Delgan/loguru",
  "pr_number": 1451,
  "base_sha": "2abeb0fa6d7be4b0455c6e0b580b1e9dab19005e",
  "merge_sha": "b782e56fcf07fecf9545ff6ee2350baacb0968ce",
  "oracle_patch_sha256": "1e843ef7617ac857dfb2139ac3e2f2a6a328b4fc5e1848f8fd021b9f3b0fdda8",
  "test_files": ["tests/test_add_option_format.py"],
  "fail_to_pass": ["tests/test_add_option_format.py::test_invalid_format_key_...", "..."],
  "pass_to_pass": [],
  "capability_labels": ["C5", "C4"]
}
```

## Archive vs. live

The release policy is applied by `tasks/publish_tasks.py::publish`. The cutoff is
2 weeks (`ARCHIVE_WEEKS = 2`); a task is *archive* when
`(today - merge_date).days >= 14`, otherwise *live*.

| | shipped in **archive** | shipped in **live** |
|---|---|---|
| `task.toml` | yes (sanitized) | yes (sanitized) |
| `instruction.md` | yes | yes |
| `PROVENANCE.json` | yes | yes |
| `environment/` | yes | yes |
| `tests/test.sh` | yes | yes |
| `tests/test_outputs.py` (protected body) | **yes** | **withheld** |
| `tests/test_patch.diff` | yes | withheld |
| `solution/` (`solve.sh`, `oracle.patch`) | **yes** | **withheld** |
| `record.json` | yes (sanitized) | replaced by `FAILING_TESTS.json` |

**Live tasks** give you the task, the environment, and the runner — but the gold
patch and the protected test bodies are held back, and scoring happens
**server-side** on submission. Instead of `record.json`, a live task ships
`FAILING_TESTS.json` exposing only the failing-test IDs (drawn from the F2P selectors
via `publish_tasks.py::_failing_test_ids`):

```json
{
  "failing_test_ids": ["tests/test_add_option_format.py::test_invalid_format_key_..."],
  "note": "protected assertions + gold solution withheld; submit a patch, scored server-side"
}
```

Withholding the gold patch and protected test bodies on live tasks blocks
memorization and test-editing; releasing archived tasks in full supports
reproducibility.

## How scoring re-lays the protected tests

Scoring is **execution-only** — there is no LLM judge, so `false_accept = 0` holds by
construction. The flow (`terminal_daily_bench/eval.py`,
`terminal_daily_bench/harbor_score.py`):

1. The task package is copied to a **run copy** (`.tdb_work/runs/...`); the model
   never touches the trusted original.
2. For a model run, the model is shown the instruction plus the source file(s) the
   reference solution touches and asked for a single unified diff. That diff is
   extracted (`eval.py::extract_diff`) and written into the run copy at
   `solution/oracle.patch`.
3. Harbor runs its built-in `oracle` agent
   (`harbor run -p <run_task> -a oracle -e singularity ...`,
   `eval.py::run_harbor_oracle`). `solution/solve.sh` applies the (now
   model-authored) patch via `git apply` inside the task's container.
4. Harbor then **re-lays `tests/` from the trusted package** and runs them under a
   network cut, on a face the agent never touched. A patch that edits `tests/` only
   changes the discarded run-copy workspace — the protected tests come from the
   trusted package, not the patch.
5. The reward is read from harbor's `result.json` by
   `harbor_score.read_harbor_reward` (the same reader the private admission gate
   uses). `reward >= 0.999` -> `solved: true`.

The no-network switch is injected for offline tasks by
`harbor_score.maybe_inject_offline_eks` (singularity-gated, task-driven,
idempotent), and the subprocess env is scrubbed of host conda/venv pollution by
`harbor_score.clean_subprocess_env`.

Each run writes one result record:

```json
{ "model": "...", "task": "td-fc90ea8b76d5f6b6", "scaffold": "single_shot_patch",
  "reward": 1.0, "solved": true, "patch_applied": true,
  "false_accept_check": { "gate": "harbor_protected_tests",
    "reward_source": "result.json via harbor_score.read_harbor_reward",
    "protected_tests_relaid_by_harbor": true, "model_is_judge": false,
    "model_patch_touched_tests": false, "false_accept": 0 } }
```

Scoring is BAD-safe: no patch, a patch that fails to apply, a hung trial, or an
unparseable result all yield `reward 0.0` / `solved: false` with the cause recorded —
never a positive score on a crash.

## Runnable examples

Score a model, or run the oracle baseline, on an **archive** task (needs an
apptainer/singularity host; the model call uses any OpenAI-compatible endpoint):

```bash
pip install -e .
export OPENAI_BASE_URL=...          # OpenAI / OpenRouter / vLLM / LiteLLM / local
export OPENAI_API_KEY=...

# baseline: the task's own oracle.patch -> reward 1.0 (no model call, archive only)
tdb oracle tasks/archive/td-fc90ea8b76d5f6b6

# score a model with the single_shot_patch scaffold
tdb run <MODEL> tasks/archive/td-fc90ea8b76d5f6b6

# multi-angle quality card (needs >=1 task and >=2 models in the results file)
tdb quality results.jsonl
```

`tdb run` / `tdb oracle` write a result JSON under `$TDB_WORK` (default `./.tdb_work`)
or to an explicit `--out PATH`. Under the hood these call `terminal_daily_bench.eval`,
which also accepts `--max-tokens`, `--call-timeout`, and `--harbor-timeout`.

Inspect a **live** task (no gold patch, no protected test bodies):

```bash
cat tasks/live/td-fc90ea8b76d5f6b6/instruction.md
cat tasks/live/td-fc90ea8b76d5f6b6/FAILING_TESTS.json     # only the failing-test IDs
```

Publish a source task package under the release policy (idempotent; picks archive vs.
live from the dates):

```bash
# publish_tasks.py <src_task_dir> <merge_date> <today> <out_root>
python tasks/publish_tasks.py ./src/td-fc90ea8b76d5f6b6 2026-03-25 2026-07-22 ./tasks
# -> {"task": "td-...", "mode": "archive", "shipped_solution": true, "dest": "tasks/archive/td-..."}
```

Submit a result for a live task (re-scored on ingest — the claimed reward is
advisory, only the patch is replayed; see [CONTRIBUTING.md](../CONTRIBUTING.md)):

```bash
# validate the submission JSON, then record it as pending re-verification
python web/submit_result.py validate < submission.json
python web/submit_result.py record   < submission.json --store community_submissions
```

A submission is one JSON object per `(model, task)` cell; required fields are
`date`, `submitter`, `model`, `scaffold`, `task` (must start with `td-`), and `patch`
(the unified diff). `reward_claimed` is advisory only.

## Plugging in your own scaffold

The built-in scaffold is `single_shot_patch` (one localized shot at a diff). A
multi-turn agent plugs in via the adapter contract
(`terminal_daily_bench/adapters/base.py::HarnessAdapter`):

```
input  = (task dir, failing test ids, model id/endpoint)
output = AdapterResult(patch: str, telemetry: dict, error: str | None)
```

An adapter's `produce_patch(...)` must **not** read or write the protected tests or
the gold solution, and must **not** compute a reward. The execution gate stays the
sole reward authority — which is what keeps `false_accept = 0` as more harnesses are
added.
