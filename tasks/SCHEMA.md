# Task-package schema (harbor-native)

One directory per task, `tasks/{archive|live}/<task-id>/`:

```
task.toml          environment.docker_image (the SIF) · environment.allow_internet
instruction.md     the natural-language task shown to the model
tests/             test.sh (runner) · test_outputs.py (protected assertions*)
environment/       Dockerfile / build recipe
solution/          solve.sh · oracle.patch   (* ARCHIVE ONLY -- withheld for live)
PROVENANCE.json    repo · pr_number · base_sha · merge_sha · upstream license
record.json        machine metadata (task_id, source candidate, f2p selectors)
```

`*` **Live tasks** ship WITHOUT `solution/` and without the protected
`tests/test_outputs.py` body (only the failing-test IDs are exposed); they are scored
server-side. **Archived tasks** (≥ 2 weeks old) ship in full for reproducibility.

## Scoring contract
A model's patch is written to a run copy, applied via `solution/solve.sh` (git apply),
then harbor RE-LAYS `tests/` from the trusted package and runs them under a network
cut. Reward = the protected-test outcome (read by
`terminal_daily_bench.harbor_score.read_harbor_reward`). The model is the subject,
never the judge; this prevents claim bypass but does not prove semantic verifier FA=0.
