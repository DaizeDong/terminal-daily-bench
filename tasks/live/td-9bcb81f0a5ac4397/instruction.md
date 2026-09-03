# Release v1.3.2: forward dataset timestamps, add walk-forward evaluation

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Two related changes, both found while benchmarking Whole-History Rating for a blog post.

---

## Bug: dataset training silently discarded every timestamp

`train_arena_with_dataset` unpacked each row's timestamp into `_` and used it **only for sorting**:

```python
for a, b, outcome, _, attributes in batch:
    ...
    arena.matchup(a, b, attributes=attributes)      # no match_time
```

Every time-aware rating system trained through the dataset helpers — which is the path `evaluate_competitor` and `benchmark_competitors` take — therefore saw a dataset in which every game happened at the same instant.

Whole-History Rating is the extreme case. Its whole model is one latent rating per playing day linked by a Wiener-process prior; with no dates, all 7,400 games collapse onto a single day and WHR degenerates into a worse Bradley-Terry. It doesn't error. It just quietly becomes a different, worse model.

Measured on eight seasons of college football, walk-forward:

| system | before | after | delta |
|---|---|---|---|
| **WHR** | 0.6595 | 0.7053 | **+0.0458** |
| Glicko-2 | 0.7040 | 0.7153 | +0.0113 |
| Glicko | 0.6977 | 0.7073 | +0.0096 |
| DWZ | 0.7005 | 0.7075 | +0.0070 |
| Elo (control, no time model) | 0.6921 | 0.6923 | +0.0002 |

Elo is the control and moves by 0.0002, which is a period-boundary artifact rather than a real change. Everything that models time improves in proportion to how much time it models. WHR goes from last of twelve to competitive.

Three regression tests: `match_time` is forwarded for wins, losses and draws; a row without a timestamp still trains; and end-to-end, three games on three distinct dates produce three days in WHR's fitted curve rather than one.

---

## Feature: `[redacted-repo].evaluation`

I have now hand-rolled the same walk-forward loop four times for four different posts, which is a good sign it belongs in the library.

`evaluate_competitor` trains on one split and predicts a held-out split with **frozen** ratings. That measures how gracefully ratings survive going stale, which is a real question but rarely the one being asked, and it systematically favours systems that forget over systems that fit all of history.

```python
from [redacted-repo] import group_by_period, walk_forward, tune

periods = group_by_period(rows)                 # ISO week by default; pass your own key
report = walk_forward(EloCompetitor, periods, warmup=23)
report.accuracy, report.log_loss, report.brier
```

`walk_forward` predicts every bout in a period before learning any of it, so a result cannot inform a prediction made the same afternoon. It reports **log loss and Brier alongside accuracy**, skips competitors it has not seen rather than inventing them, and excludes and counts draws.

`tune` grid-searches parameters and **defaults to log loss, deliberately**:

```python
tune(WholeHistoryRatingCompetitor, {"w2": [10, 30, 100, 300]}, periods, warmup=23)
```

Accuracy is a rank statistic — it only asks which side of 0.5 you landed on — so any parameter that changes confidence without changing order is invisible to it. Pythagorean's exponent is exactly such a parameter: sweeping it from 1.0 to 10.0 gives *identical* accuracy to four decimals while log loss varies by a factor of two. There is a test pinning that, because it is the reason for the default.

Verified against the hand-rolled harness: Elo 0.6923 vs 0.6921 and Massey 0.7058 vs 0.7062, the 9-bout difference being January games that fall in an ISO-2015 week. The library's period-boundary cut is the more correct of the two.

13 new tests, including no-lookahead-within-a-period and parameter restoration. 525 passed, 6 skipped. Lint clean.

---

Note: WHR is meaningfully slower now, because it is finally doing the per-day fitting it was written to do.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
