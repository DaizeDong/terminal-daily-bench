# MANIFEST -- what ships, what is deliberately withheld

## Shipped (this public bundle)
- `eval/` — the gate-free execution scorer (`harbor_score.py`) + `model_eval.{py,sh}`.
- `web/` — dashboard, community `submit_result.py` (re-scores on ingest), aggregate.
- `tasks/` — task-package SCHEMA + archived (full) tasks + live (server-side-scored) tasks.
- `.importlinter` — the moat contract; `README`, `CONTRIBUTING`, `LICENSE`.

## Deliberately NOT shipped (the moat)
- The **task-construction pipeline** (`td_pipeline/`: mining, selection, env
  generation, difficulty synthesis, repo universe) — how the daily set is chosen/built.
- The **RC-VH acceptance gate** (`rcvh/`: cascade, gate, auditor, certificate, the
  mutant/sentinel soundness probes) — how a task is certified before it enters the set.
- Any secret — model-endpoint credentials, billing configuration, API keys, private
  hostnames — MUST NEVER appear here (enforced by the release secret-scan). The
  public `model_eval` calls a generic OpenAI-compatible endpoint you configure by env.

## Why the cut is safe
`false_accept = 0` is a property of **execution scoring**, not secrecy. The shipped
`eval/` bundle imports ONLY `harbor_score` (3 pure helpers) + harbor + stdlib — proven
by `.importlinter` (`eval.* ↛ td_pipeline, rcvh`). Consumers can score and submit;
they cannot reproduce the construction/certification of tasks that pass our gate.

## Scope of this bundle (honest)
- **Functional scaffold shipped:** `single_shot` (one-shot patch). The **multi-turn /
  live-terminal agent** (terminus / Claude Code / Aider / OpenHands ...) is provided as
  the **`HarnessAdapter` contract + a stub** — wire your agent CLI to reproduce the
  "agent" column (docs/submission.md). We ship the contract, not a bundled agent.
- **Sample tasks:** 1 per split (archive/live) as a template; full dated daily suites are
  served from the site (live suites scored server-side).
- **`web/leaderboard_data.json`** is reference data from the full evaluation, not a
  bundle-reproduced artifact.
