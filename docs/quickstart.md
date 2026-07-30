# Quickstart

**terminal-daily-bench** is a living, execution-graded coding-agent benchmark.
A model produces a patch; harbor re-lays a protected test suite the model never
sees and runs it under a network cut. The reward is the test outcome — never a
model's opinion — so `false_accept = 0` by construction.

This page walks you from install to a scored result and a quality card.

## Requirements

Scoring is **not** self-contained. `tdb run` and `tdb oracle` **shell out to
[harbor](https://github.com/harbor-framework/harbor)** — the container-native
agent/task execution framework that applies the patch, re-lays the protected
tests and produces the reward — as

```
harbor run -p <task-copy> -a oracle -e singularity --ek singularity_...=... -o <jobs>
```

and read the reward out of harbor's `result.json`
(`terminal_daily_bench/eval.py::run_harbor_oracle`). Concretely you need:

- **Python ≥ 3.10** — the scoring core is pure stdlib; there are no runtime
  dependencies.
- **`harbor` on `PATH`** — upstream `harbor-framework/harbor` **0.13.1** *plus our
  patches to its singularity backend* (next bullet). This is the only hard
  external dependency of the execution gate.
- **An apptainer/singularity host** — the singularity backend executes each task's
  SIF image (we develop against apptainer 1.4.5). No Docker required.
- **`OPENAI_BASE_URL` + `OPENAI_API_KEY`** — only for `tdb run` with a real model.
  `tdb oracle` calls no model; `tdb quality` needs neither harbor nor a model.

### Honest status of the harbor dependency

The harbor build we score against is a **private, locally patched fork**, not a
released artifact. Our patches add the Docker-less singularity knobs that
`eval.py` passes on every run — `singularity_image_cache_dir`,
`singularity_overlay_size_mb`, `singularity_overlay_dir`,
`singularity_health_timeout_sec`, `singularity_mksquashfs_mem` — and **stock
upstream harbor 0.13.1 does not accept them**. Installing harbor from
PyPI/GitHub today is therefore *not* sufficient to reproduce our numbers.

**That fork is not public yet. Vendoring or publishing it — ideally upstreaming
the singularity patches — is tracked as the next release step.** We are not
promising a date, and we would rather say this here than let you discover it
from a stack trace.

Practical consequence: **a third party cannot currently run `tdb run` /
`tdb oracle` end-to-end.** What *does* work from this bundle with no harbor at
all: `tdb doctor`, `tdb quality`, `tdb publish`, and reading/inspecting the task
packages.

## Step 0: run `tdb doctor` FIRST

Before anything else, ask the bundle whether this host can score at all. It
prints one **OK/MISSING** line per requirement — python version, `harbor` (and
its `--version`), apptainer/singularity, `OPENAI_BASE_URL`/`OPENAI_API_KEY`, and
whether a given task dir is well-formed — and **exits non-zero** if anything
required is missing:

```bash
tdb doctor tasks/archive/td-fc90ea8b76d5f6b6
# from a checkout without installing:
PYTHONPATH=. python -m terminal_daily_bench.cli doctor tasks/archive/td-fc90ea8b76d5f6b6
```

On a host without the (not-yet-public) harbor fork you will see
`MISSING  harbor on PATH` and a non-zero exit — that is the truthful answer, not
a bug. Add `--oracle-only` if you only intend to run the oracle baseline and the
quality card, so a missing `OPENAI_API_KEY` is not counted as a failure.

## Install

From a checkout of the release bundle:

```bash
pip install -e .
```

Or with uv:

```bash
uv tool install terminal-daily-bench
```

Either way you get the `tdb` console script (declared as
`terminal_daily_bench.cli:main` in `pyproject.toml`). Verify:

```bash
tdb --version          # -> terminal-daily-bench 0.1.0
```

## Configure the model endpoint

The model call goes to a **generic OpenAI-compatible** endpoint, configured by
environment variables so the bundle is not tied to any vendor. Point it at
OpenAI, OpenRouter, vLLM, LiteLLM, or a local server:

```bash
export OPENAI_BASE_URL=https://api.openai.com/v1   # any OpenAI-compatible endpoint
export OPENAI_API_KEY=sk-...                        # bearer key, read from env, never stored
```

- `OPENAI_BASE_URL` defaults to `https://api.openai.com/v1` if unset. Requests go
  to `<base>/chat/completions`.
- If the upstream rejects `max_tokens` (some reasoning models), the client
  automatically retries with `max_completion_tokens`.

## Build the task image first

A published task does **not** ship a prebuilt image. Its `task.toml` carries the
portable reference

```toml
[environment]
docker_image = "environment/Dockerfile"   # build from the task Dockerfile
```

because the producer's host-specific `.sif` path is stripped on publish
(`tasks/publish_tasks.py`). Nothing can execute that string as-is, so build the
task's own `environment/Dockerfile` once, then point `docker_image` at the result:

```bash
IMG=$(scripts/build_task_image.sh tasks/archive/td-fc90ea8b76d5f6b6)
sed -i "s|^docker_image .*|docker_image = \"$IMG\"|" \
    tasks/archive/td-fc90ea8b76d5f6b6/task.toml
```

The script prints **only** the image path on stdout (logs go to stderr), so it
composes. It picks a builder automatically — apptainer/singularity if present
(translating the Dockerfile into an apptainer definition), otherwise docker — and
fails with an explicit message if neither is installed. Images are cached in
`$TDB_SIF_CACHE` (default `./.tdb_work/sif_cache`) keyed by task id + Dockerfile
hash, so a second run is a no-op; `--force` rebuilds. Full option list:
`scripts/build_task_image.sh --help`, details in
[`task-format.md`](task-format.md#building-the-task-image).

> The **build** stage needs internet (base image, `git clone`, dependency
> install). The **scored run** is the offline one — `allow_internet = false` cuts
> egress at scoring time only.

## Score a model on a task

```bash
tdb run <MODEL> tasks/archive/td-fc90ea8b76d5f6b6
```

`<MODEL>` is any model id your endpoint accepts (e.g. `gpt-4o-mini`). The
`single_shot_patch` scaffold shows the model the task instruction plus the
source file(s) the reference solution touches, and asks for a `git apply`-ready
unified diff. That diff is applied inside the task container, harbor re-lays the
protected `tests/`, and the reward is written to `result.json`.

By default the result record is written under `./.tdb_work/results/` (override the
work root with `TDB_WORK`). Choose an explicit path with `--out`:

```bash
tdb run gpt-4o-mini tasks/archive/td-fc90ea8b76d5f6b6 --out results/gpt4o-mini.json
```

The record is also printed to stdout.

## Run the oracle baseline

The `oracle` model id runs the task's real `solution/oracle.patch` — no model is
called. It is the gate's own baseline and proves the execution gate returns
**reward 1.0** on a correct patch:

```bash
tdb oracle tasks/archive/td-fc90ea8b76d5f6b6
```

Use this to confirm your apptainer/singularity host is wired up correctly before
spending model calls: if `oracle` does not yield `reward = 1.0`, the environment,
not the model, is the problem.

> Only **archived** tasks (≥ 2 weeks old) ship with `solution/`. **Live** tasks
> withhold the gold patch and the protected test bodies and are scored
> server-side. See [`tasks/SCHEMA.md`](../tasks/SCHEMA.md).

## The result record

Each run writes one JSON record. A solved run looks like:

```json
{
  "model": "gpt-4o-mini",
  "task": "td-fc90ea8b76d5f6b6",
  "task_dir": "/abs/path/tasks/archive/td-fc90ea8b76d5f6b6",
  "scaffold": "single_shot_patch",
  "reward": 1.0,
  "solved": true,
  "patch_applied": true,
  "error": null,
  "model_endpoint": "https://api.openai.com/v1/chat/completions",
  "runtime_sec": 142.7,
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

Field notes:

- `scaffold` is `single_shot_patch` for a model run, `oracle_baseline` for
  `tdb oracle`.
- `reward` is the protected-test outcome; `solved` is `reward >= 0.999`.
- `patch_applied` is `true` once a reward is parsed, `false` if the patch failed
  to apply, `null` if the gate never reached the apply step.
- Runs are BAD-safe: any failure (no diff, patch does not apply, hung trial,
  unparseable result) yields `reward = 0.0` / `solved = false` with the cause in
  `error` — never a positive score on a crash.

### The `false_accept_check` block

This block records *why* the score cannot be gamed by the model:

- `gate: "harbor_protected_tests"` — scoring is the harbor execution gate and
  nothing else.
- `reward_source` — the reward is read from `result.json` with the same reader
  the admission gate uses (`harbor_score.read_harbor_reward`), i.e. byte-for-byte
  execution truth.
- `protected_tests_relaid_by_harbor: true` — the trusted `tests/` are re-laid from
  the task package *after* the patch, so a patch that edits tests only changes a
  discarded workspace.
- `model_is_judge: false` — the model is the subject under test, never the judge.
- `model_patch_touched_tests` — flags whether the model's diff touched any
  `test`-named path (informational; it cannot affect the score).
- `false_accept: 0` — a property of execution scoring, held by construction.

## Aggregate a quality card

Collect one or more result records into a single file (JSON Lines, one record per
line, or a JSON array) and read the multi-angle quality card:

```bash
cat results/*.json | jq -c . > results.jsonl
tdb quality results.jsonl
```

`tdb quality` builds a (task × model) solved matrix and needs **≥ 1 task and ≥ 2
models** (records with `model: "oracle"` are excluded from the matrix). Example
output:

```
tasks=40 models=6
  D(discrimination)=0.517  C(coverage)=0.750  M(monotonicity)=0.912
  IRT test-information=8.431  KR-20 reliability=0.78
  D 95% CI=[0.402, 0.631]
  readiness: NOT-ready (bottleneck=discrimination, need ~64 tasks)
```

The final line of stdout is the full card as JSON (`msq`, `irt`, `reliability`,
`readiness`) for machine consumption. The metrics come from
`terminal_daily_bench.quality` — discrimination (`D`), difficulty coverage (`C`),
monotonicity (`M`), 2PL IRT test-information, KR-20 reliability, a bootstrap CI on
`D`, and a readiness verdict with the bottleneck axis and a recommended task count.

## Submitting results

Every submission is **re-scored by the same execution gate on ingest** — a claimed
number is never trusted, only the patch is replayed. See
[`../CONTRIBUTING.md`](../CONTRIBUTING.md).
