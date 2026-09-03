# Independent reviewer, multi-model debate, and best-of-N tournament

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Problem

Reviewing and judging are currently performed by the same model that produced the artifact. Stage 18 asks the author model to review the paper it just wrote, and the Stage 20 quality gate asks it whether its own paper is good enough to pass. LLMs show a well-documented preference for their own output, so this makes both stages weaker than they look: a self-review rarely produces the kind of objection that would actually block a run.

## What this adds

Three opt-in mechanisms that decouple generation from judgement. **All three default to off** — with no config changes, every stage behaves exactly as it does today.

### 1. Independent reviewer

`llm.reviewer_model` builds a reviewer client that never falls back to the author model. Set only the model to reuse the main provider with a different model, or add `reviewer_provider` / `reviewer_base_url` / `reviewer_api_key(_env)` for a fully separate provider (e.g. generator = GPT, reviewer = Claude).

Used by Stage 18 (peer review) and Stage 20 (quality gate); both fall back to the generator when it is unset.

Stage 18 also writes `review_provenance.json` — `author_model`, `judge_model`, `independent_reviewer` — plus an HTML comment header in `reviews.md`, so a finished run can be audited for reviewer independence after the fact rather than taken on trust.

### 2. Multi-model debate (`pipeline/debate.py`)

Roles argue with distinct models, rebut each other for `debate_rounds`, then an independent judge ranks the positions and a synthesizer writes the final text from that ranking.

Separating ranking from synthesis is the part that matters. When a single model both scores the positions and writes the summary, the output collapses into vague consensus — the disagreements that make a debate useful get averaged away. Letting the judge only rank (which keeps the anti-self-preference property) and having the stronger model write from that ranking preserves them.

The panel reuses models you already configure: `primary_model` + `reviewer_model` + `fallback_models`, deduplicated, each cloned into its own single-model client. Records `debate_record.json`.

### 3. Best-of-N tournament (`pipeline/tournament.py`)

Generates N candidates from diverse stances, an independent judge scores and ranks them, and the single winner proceeds — the pipeline stays linear, with one canonical artifact per stage.

Blank generations are dropped before judging rather than scored. This is a guard worth having: a judge handed an empty candidate will happily invent a rationale and a score for it, and an empty artifact can then win. Records `tournament_record.json`.

Stage 8 routes tournament → debate → the existing single-model multi-perspective path. That last path is untouched and remains the default.

## Notes for review

- Both engines depend only on the standard library — no new dependencies.
- Stage 18 deliberately does **not** use the debate synthesizer split. Reviewer independence is the entire point of that stage; a synthesizer would put the author model back in the loop.
- Two sub-prompts are added (`tournament_rank`, `debate_rebuttal`). `hypothesis_synthesize` already existed and is reused.
- These paths multiply LLM calls when enabled, which is why they are opt-in. `tournament_candidates < 2` disables the tournament.
- `config.researchclaw.example.yaml` is not touched in this PR; happy to document the knobs there if you'd prefer them advertised.

## Testing

```
2900 passed, 0 failed, 56 skipped
```

Baseline on `main` at the time of branching (`[redacted-sha]`) was `2863 passed, 1 failed` — the failure is a pre-existing timing-sensitive test, `test_hitl_advanced.py::TestFileWait::test_poll_with_delayed_response`, which passed on this run. The delta is the 36 new tests.

New coverage: debate engine (role retry, split synthesis path, judge/synthesizer wiring), tournament engine (empty-candidate drop, candidate-count effective value, ranking parse), and reviewer construction (fallback to generator, independent provider resolution, Stage 18 provenance).

🤖 Generated with [Claude Code]([redacted-url])

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
