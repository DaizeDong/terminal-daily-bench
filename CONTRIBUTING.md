# Contributing / submitting results

You do NOT need the private construction pipeline to contribute — you run the day's
tasks with your own model or scaffold and submit the results. Every submission is
**re-scored by the same execution gate on ingest**: your claimed reward is advisory
and ignored; only the *patch* is replayed against the protected tests. A fake `1.0`
whose patch verifies `0.0` contributes `0`. This is why the leaderboard is un-gameable.

## Submission format

One JSON line per `(model, task)` cell, POSTed by the harness on completion:

```json
{ "date": "YYYY-MM-DD", "submitter": "your-handle",
  "model": "your-model", "scaffold": "your-scaffold",
  "task": "td-...",
  "patch": "<unified diff your model produced>",   // re-scored on ingest
  "reward_claimed": 1.0,                            // advisory only, re-verified
  "harness_version": "v2", "signature": "<sha256>" }
```

Run `web/submit_result.py` to validate + record; verified rewards rebuild the board.

## Integrity rules (enforced, not requested)

1. **Scoring is execution-only.** A scaffold produces a candidate repo state; scoring
   is always harbor re-laying the protected `tests/` on a face the scaffold never
   touched. No scaffold ever scores.
2. **Patches may not edit tests.** A patch that touches `tests/` only changes a
   discarded workspace; protected tests are re-laid from the trusted package.
3. **Runtime egress is cut.** Tasks run under `--network=none`; a submission that
   relies on live network is rejected.
4. **Live tasks are scored server-side.** For this-week tasks the gold patch and
   protected test bodies are withheld; submit your patch and it is scored on our side.

## Adding a scaffold / harness

Implement the adapter contract (input: task dir + failing test IDs + model endpoint;
output: unified diff + telemetry) so any harness plugs in like `single_shot` /
`terminus-2`. The execution gate stays the sole reward authority.
