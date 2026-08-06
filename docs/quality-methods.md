# Selection-Quality methods (MSQ)

Most benchmarks report a single number per model — a solve-rate scalar — and stop
there. That tells you *who* scored higher; it never tells you whether the **task
set itself** can separate models at all. A set where every model fails every task,
or passes every task, produces a leaderboard that is pure noise, yet its solve-rate
column looks perfectly normal.

`terminal_daily_bench.quality` is the instrument for that missing axis: **Multi-angle
Selection-Quality (MSQ)**. It reads a graded `(task × model)` response matrix and
reports, on orthogonal axes, *how well a task set discriminates models* — plus the
psychometric reliability of the set, honest bootstrap uncertainty on every axis, the
task counts needed to reach research-grade precision, and a daily GO/NO-GO readiness
verdict. This is the axis TB (Terminal-Bench) does not measure.

Everything below is a **pure function over plain lists**: it never reads or changes a
reward decision. It therefore cannot alter replay integrity, and it also cannot measure
semantic verifier false-accept. All randomized routines are seeded and deterministic.

---

## The matrix convention

Every function operates on one object:

```
matrix   rows = tasks, cols = models
         matrix[t][j] = the graded outcome of model j on task t (int, 0 = fail)
```

A model **solved** a task iff its grade `>= solved_threshold` (default `1`), so a
binary `0/1` matrix and a graded `0..K` matrix both work with the same code. The CLI
builds this matrix for you from a results file; see [surfacing it](#how-tdb-quality-surfaces-it).

---

## The measurement axes

Each axis is a value in `[0, 1]` (higher = better) and is reported **separately** — the
composite never hides an axis that has collapsed.

### D — discriminative yield · `discriminative_yield`

The fraction of tasks that **split the field**: `0 < #solvers < n_models`. A task
everyone solves, or no one solves, carries zero discrimination.

```
D = |{ tasks with 0 < solvers < n_models }| / n_tasks
```

Returns `None` with fewer than 2 models (splitting is undefined with one column). This
is the single most important axis, and it carries the default composite weight of 0.5.

### C — difficulty coverage · `difficulty_coverage`

The **normalized entropy** of the per-task solve-rate bucket occupancy. Each task's
solve-rate lands in one of `n_buckets` equal-width bins over `[0, 1]`; the entropy of
that occupancy, divided by `log(n_buckets)`, is `1` when tasks spread evenly across
difficulties and `0` when they all cluster in one bucket.

```
C = ( -Σ p_b · log p_b ) / log(n_buckets)      p_b = fraction of tasks in bucket b
```

Measures whether the set spans easy → hard rather than clustering at one difficulty.

### M — monotonicity · `monotonicity`

The fraction of tasks with **no strong ability inversion**. For each task, over all
model pairs `(i, j)` where model `i` is clearly abler than `j`
(`ability_i > ability_j + ability_eps`, default `eps = 0.05`), a *strong inversion* is
`solved_j and not solved_i` — a weaker model passing a task the abler one misses. That
is a noise/mislabel/gameability signal. A task is monotonic iff it has zero such
inversions.

```
M = |{ monotonic tasks }| / n_tasks
```

Ability defaults to each model's overall solve-rate. With no ability separation to
violate, M is vacuously `1.0`.

### A — angle coverage · `angle_coverage`

Coding-agent capability is not one skill. From the ordinal gate-states `0..4`,
`capability_profile` decomposes ability into four **conditional** rates, each isolating
one capability by conditioning on having reached the previous stage:

| angle | meaning | conditions on state ≥ |
|---|---|---|
| `build_rate` | can produce a building env — `P(state ≥ 1)` | 0 |
| `partial_given_build` | can start fixing (some F2P) — `P(state ≥ 2 \| ≥ 1)` | 1 |
| `full_f2p_given_partial` | can complete the F2P fix — `P(state ≥ 3 \| ≥ 2)` | 2 |
| `clean_given_full_f2p` | can fix without breaking P2P — `P(state = 4 \| ≥ 3)` | 3 |

An angle whose *conditioning* population is empty is `None` — never a fabricated
number. `angle_coverage(graded, min_support=3)` reports, per angle, the conditioning
`support`, whether it is `covered` (support `≥ min_support`), the list of
`uncovered_angles`, and `all_covered`. A set that never reaches stage ≥ 3 simply
**cannot** measure `clean_given_full_f2p`; this guard catches that dead angle before
the set ships. Advisory only.

### R — diversity / anti-redundancy · `diversity`

A living daily set can silently fill with near-clones of one PR-family. R scores the
set over **task signatures** (`{repo, files, f2p}`), *not* the response matrix:

- `task_similarity(a, b)` → `0.0` for different repos (definitionally diverse); for the
  same repo, the mean of the changed-file Jaccard and the F2P-selector Jaccard.
- `redundancy_rate(sigs, threshold=0.6)` → fraction of tasks with ≥ 1 near-duplicate.
- `diversity = 1 − redundancy_rate`.

`signature_of(task)` best-effort duck-types a signature from a task object; `None` for
fewer than 2 tasks.

### I — IRT (2PL) test information · `total_information_2pl`

The psychometric gold standard. The binary response matrix is fit to the **2-parameter
logistic** item-response model via `irt_item_stats`, giving each task an
`a` (discrimination) and `b` (difficulty):

- `b = logit(1 − solve_rate)` — harder tasks (low solve-rate) get higher `b`.
- `a = max(0.2, |r_pb|·2 + 0.2)` where `r_pb` is the task's **point-biserial**
  correlation with the per-model total score. An all-pass / all-fail / non-correlating
  item floors to a small `a` — it discriminates nothing.

Each item's **Fisher information** at ability `theta` is:

```
I_item(theta) = a² · P · (1 − P)        P = 1 / (1 + e^{−a(theta − b)})
```

Item information is **additive** (items conditionally independent), so test information
is the sum, and the max-information subset is exactly the top-k items by individual
information (`select_max_information`, no greedy interaction needed):

```
I_test(theta) = Σ_items a² · P · (1 − P)          SE(theta) = 1 / √I_test
```

`information_se(info)` returns that standard error (`∞` when there is no information).

### KR-20 — reliability · `reliability_kr20`

Internal-consistency reliability: do the items measure a **consistent** latent ability,
or noise? Kuder-Richardson 20 is the standard coefficient for binary items:

```
KR20 = ( k / (k−1) ) · ( 1 − Σ p_i·q_i / σ²_total )
```

where `k` = tasks, `p_i` = task `i`'s pass rate across models, `q_i = 1 − p_i`, and
`σ²_total` = variance of the per-model total scores. `kr20` is `None` when `k < 2` or the
total-score variance is `0` (no ability spread → undefined). Rule of thumb: `> 0.7`
acceptable, `> 0.8` good; it can go **negative** when items are mutually inconsistent.

---

## Uncertainty and power

### Bootstrap confidence intervals · `msq_bootstrap_ci`

At `N ≈ 6` tasks the point estimates carry huge sampling uncertainty; a research-grade
report must state it. This **resamples the task rows with replacement** `n_boot` times
(seeded RNG → resume-reproducible), recomputing D/C/M each time, and returns per axis:

```
{ estimate, lo, hi, se, n_valid }
```

`estimate` is the point estimate on the full set, `[lo, hi]` the central `ci`-percentile
interval (default 95%), `se` the bootstrap standard deviation. Thin sets produce **wide**
intervals — that is the honest point, not a defect.

### Precision-power (required-N) · `required_tasks_for_precision`

The actionable question: how many tasks buy a research-grade interval? Standard error
scales as `1/√N`, so from the bootstrap SE at the current `N₀`:

```
half_width h(N) = z · SE(N₀) · √(N₀ / N)
required N       = N₀ · ( z · SE(N₀) / target_half_width )²      (rounded up)
```

Returns `{axis, n_now, se_now, half_width_now, target_half_width, required_n}`.
`required_n` is `None` when the axis SE is undefined (too thin) and `0` when SE is
already `0`. `precision_curve(matrix, sizes, axis="D")` gives the full precision-vs-size
curve `[{n, half_width}, ...]` for setting a daily task-count target.

### Reliability-power (required-N) · `tasks_for_reliability`

The reliability twin of precision-power, via the **Spearman-Brown prophecy**: the test
*length* needed to reach a target KR-20 from the current one:

```
k' = k · [ ρ'·(1 − ρ) ] / [ ρ·(1 − ρ') ]        (rounded up, floored at 1)
```

Returns `{current_kr20, current_k, target_kr20, required_k}`. `required_k` is `None`
when current reliability is undefined or `≤ 0` (a test measuring noise cannot be
prophesied) or the target is not in `(0, 1)`. Two independent task-count targets
(precision + reliability) triangulate "how many tasks per day."

---

## The readiness verdict · `benchmark_readiness`

The capstone folds discrimination, reliability, and precision into **one daily GO/NO-GO
advisory** and names the binding bottleneck. A set is `ready` iff **all three** hold:

```
D ≥ min_D            (default 0.4)
KR-20 ≥ min_kr20     (default 0.7)
D 95%-CI half-width ≤ max_d_halfwidth   (default 0.15)
```

A `None` on any axis fails it (too thin to certify). On NO-GO, `reasons` lists each
failing constraint with its `value`, `threshold`, and `required_n`; `bottleneck` is the
constraint demanding the most tasks; and `recommended_n = max(precision-required-N,
reliability-required-N)` — the task count that closes the day's gap. Purely advisory: it
tells the pipeline when a set is too thin to report a research-grade leaderboard; it
never gates an accept.

---

## One-call quality card · `benchmark_quality_report`

`benchmark_quality_report(matrix, ..., deep=True)` aggregates every axis in a single
call: the MSQ profile (`D/C/M` + composite), diversity (from `signatures`), angle
coverage (from flat `graded` states), the `noisy_task_indices` (monotonicity
violations), a **curated** subset (monotonic core → info-max pick → diverse filter), and
— with `deep=True` — the IRT `total_information` + SE, the bootstrap `ci`, the precision
`power` read, `reliability` (KR-20), and the `reliability_prophecy`. Every axis is
reported separately; never a single scalar hiding a collapse.

```python
from terminal_daily_bench import quality as q

matrix = [
    [1, 0, 0],   # td-1: A solves, B/C fail  -> splits
    [1, 1, 0],   # td-2
    [1, 1, 1],   # td-3: all-pass            -> no discrimination
    [0, 0, 0],   # td-4: all-fail            -> no discrimination
    [1, 0, 1],   # td-5
    [1, 1, 0],   # td-6
]

card = q.benchmark_quality_report(matrix, deep=True)
print(card["msq"])          # {'D': 0.667, 'C': 0.896, 'M': 0.833, 'composite': 0.766, ...}
print(card["irt"]["total_information"])   # 1.808
print(card["reliability"]["kr20"])        # 0.514

verdict = q.benchmark_readiness(matrix)
print(verdict["ready"], verdict["bottleneck"], verdict["recommended_n"])
# False precision 37
```

Selection helpers built on the same primitives: `select_informative_subset` (greedy
`D + C` max), `select_max_information` (top-k Fisher information), `balanced_subset`
(spread across difficulty buckets), `diverse_subset` (farthest-point over signatures),
`select_mid_difficulty` (scaffold-relative discriminative band), and `filter_monotonic`
/ `flag_noisy_tasks` (drop ability-inverting tasks). `cross_scaffold_quality` compares
which scaffold frame gives the most discriminative benchmark.

---

## How `tdb quality` surfaces it

The CLI reads a results file (JSONL or a JSON list of records), builds the `(task ×
model)` matrix, and prints the card plus the readiness line. Each record needs a `task`
and `model`, and either `solved` or a `reward` (treated as solved when `reward ≥ 0.999`);
records with `model == "oracle"` are excluded from the matrix.

```bash
# results.jsonl — one record per (model, task) run, exactly as `tdb run` emits
# {"task":"td-1","model":"A","reward":1.0}
# {"task":"td-1","model":"B","reward":0.0}
# ...

tdb quality results.jsonl
```

Real output on the 6-task / 3-model example above:

```
tasks=6 models=3
  D(discrimination)=0.667  C(coverage)=0.896  M(monotonicity)=0.833
  IRT test-information=1.808  KR-20 reliability=0.5142857142857141
  D 95% CI=[0.333, 1.000]
  readiness: NOT-ready (bottleneck=precision, need ~37 tasks)
{"msq": {...}, "irt": {...}, "reliability": {...}, "readiness": {...}}
```

The last line is the full machine-readable card (`msq`, `irt`, `reliability`,
`readiness`) as JSON for downstream tooling. The command requires **≥ 1 task and ≥ 2
models** (multi-angle quality is undefined with a single model column) and exits `2`
otherwise.

Read the example above: `D = 0.667` (4 of 6 tasks split the field — the all-pass td-3
and all-fail td-4 do not), yet the `D 95% CI = [0.333, 1.000]` is enormous because
`N = 6` is tiny, and `KR-20 = 0.51` is below the `0.70` bar. The verdict is **NOT-ready**,
bottlenecked on **precision**, needing ~37 tasks to certify a research-grade
discrimination interval. That is exactly the judgment a solve-rate scalar can never
make — and the reason MSQ exists.
