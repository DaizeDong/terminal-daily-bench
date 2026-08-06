# terminal-daily-bench

**Leaderboard: https://daizedong.github.io/terminal-daily-bench/**

A **living** coding-agent benchmark: tasks are mined from real merged GitHub pull
requests **every day**, and every model is scored by **execution proof only** — a
re-laid, protected test suite the model never sees. There is **no LLM judge**, and
no scored acceptance bypasses protected-test replay. Semantic verifier error is a
separate empirical quantity; this bundle does not claim it is zero.

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
  reward is the test outcome — never a model's opinion. This proves replay
  integrity, not perfect semantic coverage of every verifier.
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
| **Python** | ≥ 3.11 (the scoring core is pure stdlib; no runtime deps) |
| **harbor** | `harbor` on `PATH` — upstream `harbor-framework/harbor` **0.13.1** **plus our patches to the singularity backend** (see below) |
| **apptainer/singularity** | required — the singularity backend runs each task's SIF image (we develop on apptainer 1.4.5) |
| **model endpoint** | `OPENAI_BASE_URL` + `OPENAI_API_KEY` for `single_shot`/Codex; the standard Anthropic environment variables for Claude Code. Values are inherited, never written to argv/results. |

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
pip install -e .                      # participant CLI / local scoring
pip install -e '.[replay]'            # replay operators: Ed25519 receipt support
export OPENAI_BASE_URL=...            # any OpenAI-compatible endpoint
export OPENAI_API_KEY=...

tdb doctor tasks/archive/<task-id>          # preflight: python/harbor/apptainer/env/task
tdb run <MODEL> tasks/archive/<task-id>     # score a model on a task (execution gate)
tdb run <MODEL> tasks/archive/<task-id> --harness codex       # real Codex CLI
tdb run <MODEL> tasks/archive/<task-id> --harness claude-code # real Claude Code
tdb oracle tasks/archive/<task-id>          # baseline: the gold solution -> reward 1.0
tdb quality results.jsonl                   # multi-angle quality card + readiness verdict
tdb publish <results-dir>[:scaffold],...    # results -> docs/leaderboard_data.json (the site's data)
```

## Real vendor harnesses

`tdb run` now routes through an adapter registry. The default `single_shot`
adapter still produces one diff and sends that diff to the oracle-apply gate.
`codex` and `claude-code` instead use Harbor's real installed-agent adapters:
Harbor installs the CLI in the task environment, lets it explore and edit the
repository over multiple turns, then re-lays the trusted tests and verifies the
result. The adapter configures the agent; it never computes or interprets reward.

```bash
# Inspect the complete command/configuration without a credential, model call,
# container launch, or score claim.
tdb run gpt-5 tasks/archive/<task-id> --harness codex --dry-run

# Direct provider or compatible proxy. Use the exact model identifier accepted
# by that endpoint; the CLI does not silently substitute a model.
tdb run gpt-5 tasks/archive/<task-id> --harness codex
tdb run claude-sonnet-4-6 tasks/archive/<task-id> --harness claude-code

# Custom endpoints are explicit and must not contain embedded credentials.
tdb run gpt-5 tasks/archive/<task-id> --harness codex \
  --harness-base-url http://127.0.0.1:8080/v1
```

Credentials cross the Harbor boundary as an environment template such as
`${OPENAI_API_KEY}`. The real value exists only in the child environment: it is
absent from process argv, `harbor_cmd.txt`, result JSON, and dry-run output.
Secret-looking `--agent-kwarg` names are rejected; use environment variables for
authentication.

The singularity fork used by this bundle does not provide Harbor's newer dynamic
agent/verifier network switching. An installed CLI needs network access both to
install itself and to call its model, so the runner changes `allow_internet` to
`true` only in its disposable task copy and records that change in the result.
Pass `--keep-task-network-policy` to opt out (for example, with an already
installed CLI and a reachable in-sandbox endpoint). The source task is never
edited, and protected tests are still re-laid after the agent exits.

Publishing a day is one loop: `tdb publish ...` regenerates `docs/leaderboard_data.json`,
you commit and push it, and GitHub Pages redeploys the leaderboard automatically —
the page renders straight from that JSON.

Each run writes one result record:

```json
{ "model": "...", "task": "td-...", "scaffold": "single_shot_patch",
  "reward": 1.0, "solved": true, "patch_applied": true,
  "false_accept_check": { "gate": "harbor_protected_tests",
    "protected_tests_relaid_by_harbor": true, "model_is_judge": false,
    "model_patch_touched_tests": false,
    "scope": "protected_test_replay_integrity",
    "claim_acceptance_without_replay": false,
    "semantic_false_accept": null,
    "false_accept": 0 } }
```

## Layout

```
terminal_daily_bench/   package: harbor_score · eval · scoring · quality (MSQ) · cli · adapters/
tasks/                  SCHEMA · publish_tasks · archive/<full> · live/<withheld, pending replay>
web/                    dashboard · submit_result · aggregate
docker/                 harbor: protected-test re-lay + runtime egress cut
scripts/                release_check.sh · model_eval.sh
docs/ · tests/ · pyproject.toml · registry.json · .importlinter (moat contract)
```

## Task-release policy

- **Live tasks** (this week): you get the task, environment, and *failing* test IDs;
  gold and protected test bodies are withheld. A submission is unranked until an
  official operator replays its patch against the private trusted package.
- **Archived tasks** (≥ 2 weeks old): released **in full**, including the solution,
  for reproducibility.

## Submit your results

Run the day's set with your model/scaffold and submit. Ingest stores a pending,
content-addressed patch; it is not a score. Only a later Ed25519-signed official replay
receipt bound to a frozen suite/runner/Harbor/image policy can become
community-replay-verified, and ranking requires complete frozen-roster coverage.
Community replay rows remain separate from project-controlled official evaluations.
The repository ships enforcement and fake boundary tests, not proof that a production
worker/canary has run. See [CONTRIBUTING.md](CONTRIBUTING.md).

For an official deployment, ingest/promoter and signer must use distinct UIDs (or
equivalent identities): the signer alone can read the private key, while the promoter
gets read-only manifest and pinned-public-key mounts. Shared ownership plus `0600` /
`0444` is not isolation. The worker records ownership/mode facts and rejects private
keys co-located with mutable store/work/source trees, but deployment ACLs and service
identity separation still require an operator audit.

Replay operators must install `pip install -e '.[replay]'`. Receipt signing and
verification use Python `cryptography`'s in-process Ed25519 implementation; neither
operation resolves a program through `PATH` or invokes an external OpenSSL process.
The frozen execution policy must pin the container runtime's canonical absolute path,
binary SHA-256, exact version, and kind. The worker must own neither the runtime nor
its parent and must be unable to write either; the binary and parent directory must
not be group- or world-writable.

For each attempt, the worker copies the policy-pinned SIF bytes into its private
attempt directory, makes that copy read-only, and verifies its SHA-256 before Harbor
and again at the Harbor-to-canary boundary. Runtime facts are validated before Harbor
and again in the canary preflight; those snapshots must match before a receipt is
returned.

The authority bindings now fail closed in code. The frozen policy and receipt bind
the canonical `harbor_binary_path`, launcher digest/version, canonical
`harbor_package_root`, SHA-256 of the complete Harbor package and network-patch tree,
and immutable runtime-control facts. The worker recomputes and compares those facts
before and after replay. The authoritative `result.json` boundary rejects symlinks
and hardlinks, pins the root/run/result chain with `O_NOFOLLOW` file descriptors,
enforces inode/device/link-count stability and a 16 MiB limit, and uses the bytes from
that one open snapshot for reward validation and the receipt digest.

Fake runner and Fake Harbor tests prove code boundaries only; they are not evidence
of a production replay, network isolation, or authority separation. Production replay
remains a blocker until a real Harbor replay plus reachable-control/blocked-isolated
canary succeeds and an operator audits distinct signer/promoter UIDs, a signer-only
private-key mount, and read-only manifest/public-key mounts. That production audit
must also confirm the fail-closed Harbor-tree and single-snapshot result controls with
the real installed package and replay artifacts.

## Integrity

The compatibility field `false_accept = 0` is narrowly scoped to **replay
integrity**: a scored acceptance cannot bypass the protected execution gate. It is
not a measurement of semantic verifier false accepts, which remains `null` until an
exploit corpus is evaluated. Protected tests are re-laid from the trusted package
after your patch; a patch that edits `tests/` only changes a discarded workspace.
Oracle/single-shot runs honor a task's
offline policy (`--network=none`). Installed vendor CLIs require model/setup access;
on the current singularity fork their disposable run copy is online, and the result
records that policy explicitly (see “Real vendor harnesses”).

## License

Framework code: MIT (see [LICENSE](LICENSE)). Each task package carries its upstream
repository's license in `PROVENANCE.json`; tasks are derived from permissively-licensed
repositories only.
