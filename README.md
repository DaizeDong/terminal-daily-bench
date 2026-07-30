# terminal-daily-bench

**Leaderboard: https://daizedong.github.io/terminal-daily-bench/**

A **living** coding-agent benchmark: tasks are mined from real merged GitHub pull
requests **every day**, and every model is scored by **execution proof only** — a
re-laid, protected test suite the model never sees. There is **no LLM judge**, so
`false_accept = 0` by construction.

> This is the **public evaluation bundle**. The daily task-construction pipeline
> and the acceptance gate that mints the task set are **not** part of this repo —
> you *consume* the benchmark and *submit* results; you don't need (or get) the
> machinery that builds it.

## Why it's different

- **Contamination-resistant by design.** Tasks are fresh each day from just-merged
  PRs, so a model can't have trained on the fix. Provenance (repo, PR#, SHAs,
  license) ships with every task.
- **Execution-only scoring.** Your model produces a patch; harbor re-lays the
  trusted `tests/` from the task package and runs them under a network cut. The
  reward is the test outcome — never a model's opinion. `false_accept = 0`.
- **Multi-language.** Tasks span 8 languages (python · rust · go · js · ts · java ·
  ruby · c++), each with its own execution adapter.
- **Multi-angle quality.** Beyond a solve-rate scalar, the leaderboard reports a
  multi-angle quality card (discrimination, difficulty coverage, IRT information,
  KR-20 reliability) so you can see *how* a set separates models.

## Requirements (read before you try to score anything)

Scoring is **not** self-contained: `tdb run` and `tdb oracle` shell out to
[**harbor**](https://github.com/harbor-framework/harbor), the container-native agent/
task execution framework, as

```
harbor run -p <task-copy> -a oracle -e singularity --ek singularity_...=... -o <jobs>
```

and read the reward back out of harbor's `result.json`
(`terminal_daily_bench/eval.py::run_harbor_oracle`). So you need:

| | what |
|---|---|
| **Python** | ≥ 3.10 (the scoring core is pure stdlib; no runtime deps) |
| **harbor** | `harbor` on `PATH` — upstream `harbor-framework/harbor` **0.13.1** **plus our patches to the singularity backend** (see below) |
| **apptainer/singularity** | required — the singularity backend runs each task's SIF image (we develop on apptainer 1.4.5) |
| **model endpoint** | `OPENAI_BASE_URL` + `OPENAI_API_KEY`, for `tdb run` only (`tdb oracle` and `tdb quality` call no model) |

**Honest status of the harbor dependency.** The harbor build we score against is a
**private, locally patched fork**, not a released package. Our patches add the
Docker-less `--ek singularity_image_cache_dir / singularity_overlay_size_mb /
singularity_overlay_dir / singularity_health_timeout_sec / singularity_mksquashfs_mem`
knobs that `eval.py` passes; **stock upstream harbor 0.13.1 does not accept them**, so
installing harbor from PyPI/GitHub today is *not* sufficient to reproduce our numbers.
**That fork is not public yet — vendoring or publishing it (ideally upstreaming the
singularity patches) is tracked as the next release step.** We are not promising a date.

Until then: **a third party cannot run `tdb run` / `tdb oracle` end-to-end.** What does
work off this bundle with no harbor at all: `tdb quality` (multi-angle quality card from
result records), `tdb publish` (leaderboard data), the task packages themselves, and
`tdb doctor`.

Check your own host first — it prints one OK/MISSING line per requirement and exits
non-zero if a required piece is absent:

```bash
PYTHONPATH=. python -m terminal_daily_bench.cli doctor tasks/archive/<task-id>
# or, once installed:  tdb doctor tasks/archive/<task-id>
```

## Quick start

```bash
pip install -e .                      # or: uv tool install terminal-daily-bench
export OPENAI_BASE_URL=...            # any OpenAI-compatible endpoint
export OPENAI_API_KEY=...

tdb doctor tasks/archive/<task-id>          # preflight: python/harbor/apptainer/env/task
tdb run <MODEL> tasks/archive/<task-id>     # score a model on a task (execution gate)
tdb oracle tasks/archive/<task-id>          # baseline: the gold solution -> reward 1.0
tdb quality results.jsonl                   # multi-angle quality card + readiness verdict
tdb publish <results-dir>[:scaffold],...    # results -> docs/leaderboard_data.json (the site's data)
```

Publishing a day is one loop: `tdb publish ...` regenerates `docs/leaderboard_data.json`,
you commit and push it, and GitHub Pages redeploys the leaderboard automatically —
the page renders straight from that JSON.

Each run writes one result record:

```json
{ "model": "...", "task": "td-...", "scaffold": "single_shot_patch",
  "reward": 1.0, "solved": true, "patch_applied": true,
  "false_accept_check": { "gate": "harbor_protected_tests",
    "protected_tests_relaid_by_harbor": true, "model_is_judge": false,
    "model_patch_touched_tests": false, "false_accept": 0 } }
```

## Layout

```
terminal_daily_bench/   package: harbor_score · eval · scoring · quality (MSQ) · cli · adapters/
tasks/                  SCHEMA · publish_tasks · archive/<full> · live/<scored server-side>
web/                    dashboard · submit_result · aggregate
docker/                 harbor: protected-test re-lay + runtime egress cut
scripts/                release_check.sh · model_eval.sh
docs/ · tests/ · pyproject.toml · registry.json · .importlinter (moat contract)
```

## Task-release policy

- **Live tasks** (this week): you get the task, the environment, and the *failing*
  test IDs — but the gold patch and the protected test bodies are **withheld** and
  scoring is done **server-side** on submission (blocks memorization + test-editing).
- **Archived tasks** (≥ 2 weeks old): released **in full**, including the solution,
  for reproducibility.

## Submit your results

Run the day's set with your model/scaffold and submit; every submission is
**re-scored by the same execution gate on ingest** — a claimed number is never
trusted, only the patch is replayed. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Integrity

`false_accept = 0` is a property of **execution scoring**, not of secrecy — this
public bundle can score patches without the private construction pipeline. Protected
tests are re-laid from the trusted package after your patch; a patch that edits
`tests/` only changes a discarded workspace. Runtime egress is cut (`--network=none`).

## License

Framework code: MIT (see [LICENSE](LICENSE)). Each task package carries its upstream
repository's license in `PROVENANCE.json`; tasks are derived from permissively-licensed
repositories only.
