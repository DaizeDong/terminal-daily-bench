# Add slm.evaluate() — a standalone eval harness (SDK + CLI)

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## What & why

[redacted-repo] ships the full **capture → judge → train → own** loop, but there was **no way to score a model on a task**. The only "eval" today is train-time `eval_loss` (next-token loss on held-out data) — not task quality. The README roadmap calls task-level evals an unbuilt "eval gate," and the product thesis ("run the shadow until it does the job *as well* as the frontier, then switch") is unprovable without a quality score.

This adds the smallest meaningful slice of that: `slm.evaluate(model, dataset, metric=...)` and a `[redacted-repo] eval` CLI command. Purely additive — no behavior changes.

## Changes

- **`[redacted-repo]/eval.py`** (new) — `evaluate(model, data, *, metric="contains", judge=None, system=None, sample=None, ...)` returning an `EvalResult` (aggregate `score`, per-row `scores`/`examples`, plus `.sparkline()`, `.worst(k)`, `.to_dict()`).
  - Metrics: `contains` (default — expected answer appears in output), `exact` (normalized equality), `judge` (LLM-as-judge), or a custom `(output, expected, prompt) -> float` callable.
  - **Reuses existing scorers** rather than reimplementing them: `apo._contains_score`, `apo._judge_one`, and `apo._cols` column detection. Handles chat / instruction / preference rows and dataset-path inputs.
- **`[redacted-repo]/__init__.py`** — export `evaluate`, `EvalResult`.
- **`[redacted-repo]/cli.py`** — `[redacted-repo] eval <model> <dataset> [--metric contains|exact|judge] [--judge <id>] [--sample N] ...]`, prints a headline score + a worst-examples table.
- **`examples/evaluate.py`** (new) — end-to-end demo.

## Usage

```python
res = slm.evaluate(model, "qa.jsonl")            # contains-match (default)
res = slm.evaluate(model, ds, metric="exact")     # exact-match
res = slm.evaluate(model, ds, judge=judge)        # LLM-as-judge
res = slm.evaluate(model, ds, metric=my_score_fn) # custom scorer
print(res.score, res.sparkline())
```

```bash
[redacted-repo] eval mlx-community/Qwen2.5-0.5B-Instruct-4bit data.jsonl --metric contains
```

## Verification

- `python -m compileall [redacted-repo]` clean; `import [redacted-repo] as slm; slm.evaluate` resolves.
- No-GPU stub tests pass for all metrics (contains/exact/custom/judge), chat + preference formats, dataset-path input, the `judge`-implies-metric default, and the error cases (judge-without-model, missing-prompt-column).
- CLI `[redacted-repo] eval --help` registers and renders; `eval` appears in the top-level Models panel.
- Not run in this environment (needs a backend + model weights): the live `examples/evaluate.py` mlx run and a real CLI run against a downloaded model. The logic they exercise is covered by the stub tests.

## Out of scope

No `/v1/evaluate` server endpoint, no studio UI, no train-time auto-eval hook, no token-F1 metric — those can follow once this SDK surface lands.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
