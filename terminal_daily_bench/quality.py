"""quality.py -- self-contained multi-angle benchmark Selection-Quality (MSQ).

Public port of the MSQ instrument: measures how well a benchmark task set
discriminates models across orthogonal angles. Zero td_pipeline/rcvh import.

Multi-angle Selection Quality (MSQ) — quantitative benchmark-set quality metrics.

Given a graded ``(task x model)`` response matrix, compute ORTHOGONAL quality axes so
a daily task set can be selected / pruned to maximize discriminative power across many
angles instead of one solve-rate scalar. Pure functions over plain lists; reuses the
IRT machinery in :mod:`grm_spectrum`. No advisory / scoring imports (crown-seal clean):
this module measures a benchmark set, it never gates an accept.

Matrix convention
-----------------
``matrix`` is ``rows = tasks, cols = models``; each entry is an outcome grade (``int``,
``0`` = fail). A model "solved" a task iff its grade ``>= solved_threshold`` (default 1),
so a binary 0/1 matrix and a graded 0..K matrix both work.

The axes (each in ``[0, 1]``, higher = better)
----------------------------------------------
* **D — discriminative yield**: fraction of tasks that SPLIT the field (neither all-pass
  nor all-fail). A task everyone or no-one solves carries zero discrimination.
* **C — difficulty coverage**: normalized entropy of the per-task solve-rate bucket
  occupancy. High = the set spans easy→hard, not clustered at one difficulty.
* **M — monotonicity**: fraction of tasks with no STRONG ability inversion (a
  lower-ability model solving a task a higher-ability model misses is a noise/mislabel
  signal). Ability defaults to each model's overall solve-rate.

``msq_profile`` returns every axis SEPARATELY plus a transparent weighted composite —
never a single scalar that could hide one axis collapsing.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence


# --- Inlined leaf helpers (verbatim from private grm_spectrum / difficulty_synth;
# keeps this module SELF-CONTAINED for the public release) ---
N_CATEGORIES = 5
CAT_ALL_F2P_BREAKS_P2P = 3
CAT_FULL_ACCEPT = 4


def capability_profile(graded: Sequence[int]) -> Dict[str, Optional[float]]:
    """Decompose a model's graded gate-states into a MULTI-ANGLE capability profile.

    A single ability scalar (or overall solve-rate) conflates several distinct skills.
    From the ordinal gate-states 0..4 we compute four CONDITIONAL rates, each isolating
    one capability by conditioning on having reached the previous stage:

      * ``build_rate``            = P(state ≥ 1)               — can produce a building env.
      * ``partial_given_build``   = P(state ≥ 2 | state ≥ 1)   — can start fixing (some F2P).
      * ``full_f2p_given_partial``= P(state ≥ 3 | state ≥ 2)   — can complete the F2P fix.
      * ``clean_given_full_f2p``  = P(state = 4 | state ≥ 3)   — can fix WITHOUT breaking P2P.

    These four angles are orthogonal skills (a model can be strong at one and weak at
    another) — the "measure the model from different angles" property. Each rate whose
    CONDITIONING population is empty is ``None`` (undefined, never a fabricated number).
    Also returns ``n`` and ``full_accept_rate`` = P(state = 4) (the headline solve rate)
    for reference. Deterministic; consumes execution-graded states, no model signal.
    """
    xs = [g for g in graded if 0 <= g < N_CATEGORIES]
    n = len(xs)

    def _cond(reach: int, given: int) -> Optional[float]:
        denom = sum(1 for g in xs if g >= given)
        if denom == 0:
            return None
        num = sum(1 for g in xs if g >= reach)
        return num / denom

    return {
        "n": n,
        "build_rate": (sum(1 for g in xs if g >= 1) / n) if n else None,
        "partial_given_build": _cond(2, 1),
        "full_f2p_given_partial": _cond(3, 2),
        # clean-accept given all-F2P-reached: state==4 among state>=3
        "clean_given_full_f2p": (
            (sum(1 for g in xs if g == CAT_FULL_ACCEPT)
             / sum(1 for g in xs if g >= CAT_ALL_F2P_BREAKS_P2P))
            if any(g >= CAT_ALL_F2P_BREAKS_P2P for g in xs) else None),
        "full_accept_rate": (sum(1 for g in xs if g == CAT_FULL_ACCEPT) / n) if n else None,
    }


# ---------------------------------------------------------------------------
# Samejima Graded Response Model — probabilities, information, SE (correct math).
# ---------------------------------------------------------------------------


def coarse_bucket(value: float, *, n_buckets: int = 4,
                  lo: float = 0.0, hi: float = 1.0) -> int:
    """Map a scalar into one of ``n_buckets`` coarse ordinal bands ``0..n_buckets-1``.

    Deterministic equal-width binning over ``[lo, hi]`` (values are clamped). Coarse on
    purpose: 3–5 bands are identifiable at N≈10 models where a 25-dim latent space is
    not. The top edge maps into the last bucket (half-open bins except the closed top).
    """
    n = max(1, int(n_buckets))
    if hi <= lo:
        return 0
    v = max(lo, min(hi, value))
    idx = int((v - lo) / (hi - lo) * n)
    return min(n - 1, idx)


Matrix = Sequence[Sequence[int]]


def _dims(matrix: Matrix) -> tuple:
    n_tasks = len(matrix)
    n_models = len(matrix[0]) if n_tasks else 0
    return n_tasks, n_models


def _solved_row(row: Sequence[int], threshold: int) -> List[int]:
    return [1 if (x is not None and x >= threshold) else 0 for x in row]


def discriminative_yield(matrix: Matrix, *, solved_threshold: int = 1) -> Optional[float]:
    """Fraction of tasks that split the field (0 < #solvers < n_models).

    None when the matrix has < 2 models (splitting is undefined with one column).
    """
    n_tasks, n_models = _dims(matrix)
    if n_tasks == 0 or n_models < 2:
        return None
    split = 0
    for row in matrix:
        s = sum(_solved_row(row, solved_threshold))
        if 0 < s < n_models:
            split += 1
    return split / n_tasks


def _task_solve_rate(row: Sequence[int], threshold: int) -> float:
    s = _solved_row(row, threshold)
    return sum(s) / len(s) if s else 0.0


def difficulty_coverage(matrix: Matrix, *, n_buckets: int = 4,
                        solved_threshold: int = 1) -> Optional[float]:
    """Normalized entropy of the per-task solve-rate bucket occupancy, in ``[0,1]``.

    Each task's solve-rate (across models) lands in one of ``n_buckets`` equal-width
    bins over ``[0,1]``; the entropy of that occupancy distribution, divided by
    ``log(n_buckets)``, is 1 when tasks spread evenly across difficulties and 0 when
    they all cluster in one bucket. None for an empty matrix / n_buckets < 2.
    """
    n_tasks, n_models = _dims(matrix)
    if n_tasks == 0 or n_models == 0 or n_buckets < 2:
        return None
    counts = [0] * n_buckets
    for row in matrix:
        r = _task_solve_rate(row, solved_threshold)
        b = min(n_buckets - 1, int(r * n_buckets))   # r==1.0 -> last bucket
        counts[b] += 1
    total = sum(counts)
    if total == 0:
        return None
    h = 0.0
    for c in counts:
        if c:
            p = c / total
            h -= p * math.log(p)
    return h / math.log(n_buckets)


def _model_abilities(matrix: Matrix, threshold: int) -> List[float]:
    """Per-model ability = its overall solve-rate across tasks."""
    n_tasks, n_models = _dims(matrix)
    if n_tasks == 0 or n_models == 0:
        return []
    ab = [0.0] * n_models
    for row in matrix:
        s = _solved_row(row, threshold)
        for j in range(n_models):
            ab[j] += s[j]
    return [a / n_tasks for a in ab]


def monotonicity(matrix: Matrix, *, abilities: Optional[Sequence[float]] = None,
                 solved_threshold: int = 1, ability_eps: float = 0.05) -> Optional[float]:
    """Fraction of tasks with NO strong ability inversion.

    For each task, over all model pairs ``(i, j)`` where model ``i`` is clearly abler
    than ``j`` (``ability_i > ability_j + ability_eps``), a STRONG inversion is
    ``solved_j and not solved_i`` — a weaker model passing a task the abler one misses.
    A task is monotonic iff it has zero such inversions. Returns the fraction of
    monotonic tasks. ``abilities`` defaults to each model's overall solve-rate.
    None when < 2 models.
    """
    n_tasks, n_models = _dims(matrix)
    if n_tasks == 0 or n_models < 2:
        return None
    ab = list(abilities) if abilities is not None else _model_abilities(matrix, solved_threshold)
    # ordered clearly-abler pairs (i abler than j)
    pairs = [(i, j) for i in range(n_models) for j in range(n_models)
             if ab[i] > ab[j] + ability_eps]
    if not pairs:
        return 1.0  # no ability separation to violate -> vacuously monotonic
    mono = 0
    for row in matrix:
        s = _solved_row(row, solved_threshold)
        inverted = any(s[j] == 1 and s[i] == 0 for (i, j) in pairs)
        if not inverted:
            mono += 1
    return mono / n_tasks


DEFAULT_WEIGHTS = {"D": 0.5, "C": 0.25, "M": 0.25}


def msq_profile(matrix: Matrix, *, solved_threshold: int = 1, n_buckets: int = 4,
                abilities: Optional[Sequence[float]] = None,
                weights: Optional[Dict[str, float]] = None) -> Dict[str, Optional[float]]:
    """Return every MSQ axis SEPARATELY plus a transparent weighted composite.

    Composite averages only the axes that are defined (not None), renormalizing the
    weights over the present axes, so a thin matrix that cannot support an axis does
    not silently zero the composite. Weights are echoed for auditability.
    """
    D = discriminative_yield(matrix, solved_threshold=solved_threshold)
    C = difficulty_coverage(matrix, n_buckets=n_buckets, solved_threshold=solved_threshold)
    M = monotonicity(matrix, abilities=abilities, solved_threshold=solved_threshold)
    w = dict(weights or DEFAULT_WEIGHTS)
    axes = {"D": D, "C": C, "M": M}
    present = {k: v for k, v in axes.items() if v is not None}
    if present:
        wsum = sum(w.get(k, 0.0) for k in present) or 1.0
        composite = sum(present[k] * w.get(k, 0.0) for k in present) / wsum
    else:
        composite = None
    n_tasks, n_models = _dims(matrix)
    return {"D": D, "C": C, "M": M, "composite": composite,
            "n_tasks": n_tasks, "n_models": n_models, "weights": w}


def _subset_objective(rows: Sequence[Sequence[int]], *, solved_threshold: int,
                      n_buckets: int) -> float:
    """Discrimination + coverage objective for a candidate task subset, in ``[0, 2]``.

    ``D(subset) + C(subset)`` — reward a subset that both SPLITS the field and SPANS
    difficulties. Undefined axes (thin subset) contribute 0. This is what
    :func:`select_informative_subset` greedily maximizes.
    """
    if not rows:
        return 0.0
    d = discriminative_yield(rows, solved_threshold=solved_threshold)
    c = difficulty_coverage(rows, n_buckets=n_buckets, solved_threshold=solved_threshold)
    return (d or 0.0) + (c or 0.0)


def select_informative_subset(matrix: Matrix, k: int, *, solved_threshold: int = 1,
                              n_buckets: int = 4) -> List[int]:
    """Greedily pick ``k`` task indices maximizing discrimination + difficulty coverage.

    Forward selection: repeatedly add the not-yet-chosen task whose addition most
    increases ``D(subset) + C(subset)``; ties break by lowest task index (deterministic
    — no RNG, so a resume reproduces the pick). Returns the chosen indices in selection
    order. ``k`` is clamped to ``[0, n_tasks]``.

    This is the data-driven core of a benchmark selector: from a day's candidate tasks
    (rows) it keeps the ``k`` that best separate models across angles, instead of a
    first-k or random slice. It reads ONLY the response matrix — never a reward gate —
    so it cannot affect false_accept.
    """
    n_tasks, _ = _dims(matrix)
    k = max(0, min(k, n_tasks))
    chosen: List[int] = []
    remaining = list(range(n_tasks))
    while len(chosen) < k and remaining:
        best_idx = None
        best_obj = -1.0
        for idx in remaining:
            trial = [matrix[i] for i in chosen] + [matrix[idx]]
            obj = _subset_objective(trial, solved_threshold=solved_threshold,
                                    n_buckets=n_buckets)
            if obj > best_obj + 1e-12:
                best_obj = obj
                best_idx = idx
        # best_idx is the lowest-index maximizer (remaining is ascending)
        chosen.append(best_idx)
        remaining.remove(best_idx)
    return chosen


# ===========================================================================
# R axis — diversity / anti-redundancy (task-metadata, not the response matrix)
# ===========================================================================
# A living daily set can silently fill with near-clones of one PR-family (same
# repo, overlapping changed files / F2P selectors) — the "PRs all repeat" failure.
# These functions score + select for diversity over TASK SIGNATURES, decoupled from
# the response matrix and from any reward gate (FA=0 untouched).

Signature = Dict[str, object]  # {"repo": str, "files": iterable, "f2p": iterable}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    u = a | b
    return (len(a & b) / len(u)) if u else 1.0


def task_similarity(sig_a: Signature, sig_b: Signature) -> float:
    """Similarity in ``[0,1]`` of two task signatures.

    Different repos → ``0.0`` (definitionally diverse). Same repo → the mean of the
    changed-file Jaccard and the F2P-selector Jaccard, so two PRs to the same repo
    that touch the same files / assert the same tests score high (near-duplicate).
    """
    if sig_a.get("repo") != sig_b.get("repo"):
        return 0.0
    fj = _jaccard(set(sig_a.get("files") or ()), set(sig_b.get("files") or ()))
    tj = _jaccard(set(sig_a.get("f2p") or ()), set(sig_b.get("f2p") or ()))
    return 0.5 * fj + 0.5 * tj


def redundancy_rate(sigs: Sequence[Signature], *, threshold: float = 0.6) -> Optional[float]:
    """Fraction of tasks with ≥1 near-duplicate (similarity ≥ ``threshold``).

    None for < 2 tasks (redundancy undefined). O(n²) — daily sets are small.
    """
    n = len(sigs)
    if n < 2:
        return None
    dup = 0
    for i in range(n):
        if any(i != j and task_similarity(sigs[i], sigs[j]) >= threshold
               for j in range(n)):
            dup += 1
    return dup / n


def diversity(sigs: Sequence[Signature], *, threshold: float = 0.6) -> Optional[float]:
    """The R axis: ``1 − redundancy_rate`` (higher = more diverse). None for < 2."""
    r = redundancy_rate(sigs, threshold=threshold)
    return None if r is None else 1.0 - r


def diverse_subset(sigs: Sequence[Signature], k: int) -> List[int]:
    """Greedily pick ``k`` task indices maximizing diversity (farthest-point).

    Seed with task 0, then repeatedly add the task whose MAX similarity to the already
    chosen set is smallest (the most different remaining task); ties break by lowest
    index (deterministic, resume-reproducible). Returns indices in selection order.
    """
    n = len(sigs)
    k = max(0, min(k, n))
    if k == 0:
        return []
    chosen = [0]
    remaining = list(range(1, n))
    while len(chosen) < k and remaining:
        best_idx = None
        best_maxsim = 2.0
        for idx in remaining:
            maxsim = max(task_similarity(sigs[idx], sigs[c]) for c in chosen)
            if maxsim < best_maxsim - 1e-12:
                best_maxsim = maxsim
                best_idx = idx
        chosen.append(best_idx)
        remaining.remove(best_idx)
    return chosen


def signature_of(task: object) -> Signature:
    """Best-effort ``{repo, files, f2p}`` signature from a GeneratedTask/candidate-like
    object (duck-typed). Tolerant of missing attrs → empty sets. Never raises."""
    def _get(o, *names, default=None):
        for nm in names:
            v = getattr(o, nm, None)
            if v is None and isinstance(o, dict):
                v = o.get(nm)
            if v is not None:
                return v
        return default
    src = _get(task, "source", default=None)
    cand = _get(src, "candidate", default=src) if src is not None else task
    repo = _get(cand, "repo", default="") or ""
    files = _get(cand, "files", "changed_files", default=[]) or []
    f2p = _get(task, "f2p_selectors", default=None)
    if f2p is None:
        f2p = _get(cand, "f2p_selectors", "f2p", default=[]) or []
    return {"repo": str(repo), "files": list(files), "f2p": list(f2p)}


# ===========================================================================
# R4 — difficulty-balanced selection (angle coverage over the C axis)
# ===========================================================================
def balanced_subset(matrix: Matrix, k: int, *, n_buckets: int = 4,
                    solved_threshold: int = 1) -> List[int]:
    """Pick ``k`` task indices SPREAD across difficulty buckets (anti-clustering).

    Bucket each task by its solve-rate, then round-robin across buckets (easy→hard),
    taking the lowest-index unused task in each, so the chosen set spans difficulties
    even when the candidate pool is skewed. Deterministic. Complements
    :func:`select_informative_subset` (which maximizes D+C but can still concentrate
    difficulty); use this when coverage across the C axis is the priority.
    """
    n_tasks, _ = _dims(matrix)
    k = max(0, min(k, n_tasks))
    if k == 0:
        return []
    buckets: List[List[int]] = [[] for _ in range(n_buckets)]
    for i, row in enumerate(matrix):
        r = _task_solve_rate(row, solved_threshold)
        b = min(n_buckets - 1, int(r * n_buckets))
        buckets[b].append(i)
    chosen: List[int] = []
    # round-robin across buckets until k picked or all exhausted
    while len(chosen) < k and any(buckets):
        for b in range(n_buckets):
            if buckets[b]:
                chosen.append(buckets[b].pop(0))
                if len(chosen) >= k:
                    break
    return chosen


# ===========================================================================
# R5 — monotonicity noise filter (raise M / trustworthiness)
# ===========================================================================
def flag_noisy_tasks(matrix: Matrix, *, abilities: Optional[Sequence[float]] = None,
                     solved_threshold: int = 1, ability_eps: float = 0.05,
                     max_inversions: int = 0) -> List[int]:
    """Return indices of tasks whose response pattern violates ability-monotonicity.

    A task is NOISY when its count of strong ability inversions (a clearly-weaker model
    solving it while a clearly-abler model misses) exceeds ``max_inversions``. Such a
    task is likely mislabeled / flaky / gameable and pollutes discriminative reads.
    Ability defaults to per-model overall solve-rate. (A NON-gating advisory: it
    surfaces suspects; the caller decides — FA=0 untouched.)
    """
    n_tasks, n_models = _dims(matrix)
    if n_tasks == 0 or n_models < 2:
        return []
    ab = list(abilities) if abilities is not None else _model_abilities(matrix, solved_threshold)
    pairs = [(i, j) for i in range(n_models) for j in range(n_models)
             if ab[i] > ab[j] + ability_eps]
    noisy: List[int] = []
    for t, row in enumerate(matrix):
        s = _solved_row(row, solved_threshold)
        inv = sum(1 for (i, j) in pairs if s[j] == 1 and s[i] == 0)
        if inv > max_inversions:
            noisy.append(t)
    return noisy


def filter_monotonic(matrix: Matrix, **kwargs) -> List[int]:
    """Indices of the task rows that SURVIVE the monotonicity noise filter (the
    complement of :func:`flag_noisy_tasks`). Order-preserving, deterministic."""
    noisy = set(flag_noisy_tasks(matrix, **kwargs))
    return [i for i in range(len(matrix)) if i not in noisy]


# ===========================================================================
# R6 — angle-coverage guard (A axis): can the set populate every capability angle?
# ===========================================================================
# The four capability angles (grm_spectrum.capability_profile) each CONDITION on
# reaching the previous gate-stage. A daily set that never reaches stage ≥3 cannot
# measure `clean_given_full_f2p` at all — a dead angle. This guard reports each
# angle's conditioning support so an under-covered set is caught BEFORE it ships.

_ANGLE_GIVEN = {           # angle -> minimum gate-state its conditioning population needs
    "build_rate": 0,
    "partial_given_build": 1,
    "full_f2p_given_partial": 2,
    "clean_given_full_f2p": 3,
}


def angle_coverage(graded: Sequence[int], *, min_support: int = 3) -> Dict[str, object]:
    """Report each capability angle's conditioning support + adequacy.

    ``graded`` is the flat list of ordinal gate-states (0..4) over the set's
    ``(model, task)`` cells. For each angle, the conditioning population is the count
    of cells at ``>= given`` stage; an angle is COVERED iff that count ``>= min_support``
    (else its rate is statistically meaningless / undefined). Returns the per-angle
    ``{support, covered}``, the underlying ``capability_profile``, the list of
    under-covered angles, and ``all_covered``. Advisory only — never gates (FA=0).
    """
    xs = [g for g in graded if isinstance(g, int) and 0 <= g <= 4]
    prof = capability_profile(xs)
    per_angle = {}
    uncovered = []
    for angle, given in _ANGLE_GIVEN.items():
        support = sum(1 for g in xs if g >= given)
        covered = support >= min_support
        per_angle[angle] = {"support": support, "covered": covered,
                            "rate": prof.get(angle)}
        if not covered:
            uncovered.append(angle)
    return {"per_angle": per_angle, "profile": prof,
            "uncovered_angles": uncovered, "all_covered": not uncovered,
            "n": len(xs), "min_support": min_support}


# ===========================================================================
# R7 — end-to-end benchmark quality report + curation (all axes in one call)
# ===========================================================================
def benchmark_quality_report(matrix: Matrix, *,
                             signatures: Optional[Sequence[Signature]] = None,
                             graded: Optional[Sequence[int]] = None,
                             target_k: Optional[int] = None,
                             solved_threshold: int = 1, n_buckets: int = 4,
                             sim_threshold: float = 0.6, min_support: int = 3,
                             deep: bool = True, ci_n_boot: int = 500, ci_seed: int = 0,
                             power_target_half_width: float = 0.1
                             ) -> Dict[str, object]:
    """One-call MULTI-ANGLE quality assessment + curation of a benchmark task set.

    Aggregates every axis so a day's set can be scored and curated in one place:
      * **MSQ** (D/C/M + composite) from the ``(task×model)`` response ``matrix``;
      * **R** (diversity) from per-task ``signatures`` (optional);
      * **A** (angle coverage) from flat ``graded`` gate-states (optional);
      * **noisy** task indices (monotonicity violations);
      * a **curated** subset — the monotonic tasks, then ``target_k`` (default: all
        surviving) picked by info-max on the response matrix and, when signatures are
        given, filtered to the diverse core — the discriminative, non-redundant set.

    Pure aggregation of the R1–R6 primitives; reads no reward gate (FA=0 untouched).
    Every axis is reported SEPARATELY (never a single scalar hiding a collapse).
    """
    msq = msq_profile(matrix, solved_threshold=solved_threshold, n_buckets=n_buckets)
    report: Dict[str, object] = {"msq": msq}

    noisy = flag_noisy_tasks(matrix, solved_threshold=solved_threshold)
    report["noisy_task_indices"] = noisy
    monotonic = [i for i in range(len(matrix)) if i not in set(noisy)]

    report["diversity"] = (diversity(signatures, threshold=sim_threshold)
                           if signatures is not None else None)
    report["angle_coverage"] = (angle_coverage(graded, min_support=min_support)
                                if graded is not None else None)

    # ---- curate: monotonic core -> info-max pick -> diverse filter ----
    k = target_k if target_k is not None else len(monotonic)
    mono_matrix = [matrix[i] for i in monotonic]
    picked_local = select_informative_subset(mono_matrix, k,
                                             solved_threshold=solved_threshold,
                                             n_buckets=n_buckets)
    curated = [monotonic[i] for i in picked_local]
    if signatures is not None and curated:
        cur_sigs = [signatures[i] for i in curated]
        div_local = diverse_subset(cur_sigs, len(curated))
        curated = [curated[i] for i in div_local]
    report["curated_task_indices"] = curated
    if curated:
        report["curated_msq"] = msq_profile([matrix[i] for i in curated],
                                            solved_threshold=solved_threshold,
                                            n_buckets=n_buckets)

    # ---- R14 capstone: the research-grade quality card (I axis + CI + power) ----
    # `deep` (default on) folds in the IRT test-information, bootstrap CIs, and the
    # required-N power read so ONE call yields a complete, uncertainty-aware quality
    # card. All still crown-seal-clean, deterministic (seeded), FA=0 untouched.
    if deep:
        stats = irt_item_stats(matrix, solved_threshold=solved_threshold)
        ti = total_information_2pl(stats, 0.0)
        report["irt"] = {"total_information": ti, "se": information_se(ti),
                         "item_stats": stats}
        report["ci"] = msq_bootstrap_ci(matrix, n_boot=ci_n_boot, seed=ci_seed,
                                        solved_threshold=solved_threshold,
                                        n_buckets=n_buckets)
        report["power"] = required_tasks_for_precision(
            matrix, target_half_width=power_target_half_width, axis="D",
            seed=ci_seed, n_boot=ci_n_boot, solved_threshold=solved_threshold,
            n_buckets=n_buckets)
        report["reliability"] = reliability_kr20(matrix, solved_threshold=solved_threshold)
        report["reliability_prophecy"] = tasks_for_reliability(
            matrix, target_kr20=0.7, solved_threshold=solved_threshold)
    return report


# ===========================================================================
# R9 — difficulty-coverage gap report + synthesis targets (attacks the C axis)
# ===========================================================================
# C (difficulty coverage) is the weakest measured axis: a day's tasks cluster at
# one difficulty (e.g. 4/6 all-fail for single-shot → C=0.325). These functions
# locate the UNDER-populated difficulty buckets and recommend which easier tasks to
# COMPOSE (composition raises difficulty, `difficulty_synth.compose`) to fill a
# harder gap — turning a low-C pool into a difficulty-spanning one. Advisory only
# (surfaces targets; the caller synthesizes + re-measures → FA=0 untouched).

def difficulty_gaps(matrix: Matrix, *, n_buckets: int = 4, min_per_bucket: int = 1,
                    solved_threshold: int = 1) -> Dict[str, object]:
    """Per-difficulty-bucket occupancy + the coverage gaps.

    Difficulty of a task = ``1 - solve_rate`` (0 = everyone solves … 1 = no one),
    binned by ``difficulty_synth.coarse_bucket``. A bucket is a GAP when it holds
    ``< min_per_bucket`` tasks. Returns bucket counts, the task-index occupancy,
    ``gap_buckets``, and the C-axis ``coverage`` (unchanged definition).
    """
    n_tasks, _ = _dims(matrix)
    occ: Dict[int, List[int]] = {b: [] for b in range(n_buckets)}
    for i, row in enumerate(matrix):
        diff = 1.0 - _task_solve_rate(row, solved_threshold)
        occ[coarse_bucket(diff, n_buckets=n_buckets)].append(i)
    counts = [len(occ[b]) for b in range(n_buckets)]
    gaps = [b for b in range(n_buckets) if counts[b] < min_per_bucket]
    cov = difficulty_coverage(matrix, n_buckets=n_buckets, solved_threshold=solved_threshold)
    return {"bucket_counts": counts, "occupancy": occ, "gap_buckets": gaps,
            "coverage": cov, "n_tasks": n_tasks, "min_per_bucket": min_per_bucket}


def synthesis_recommendations(matrix: Matrix, *, n_buckets: int = 4,
                              min_per_bucket: int = 1, solved_threshold: int = 1,
                              max_pairs: int = 3) -> Dict[str, object]:
    """Advisory: for each HARDER gap bucket, recommend easier tasks to compose into it.

    Composition raises difficulty, so a hard gap ``b`` is fillable only from tasks in
    EASIER populated buckets (``< b``); each recommendation lists those source buckets
    and up to ``max_pairs`` example source task-index pairs to compose. A gap with no
    easier source (e.g. the easiest bucket empty) yields no recommendation — honestly
    unfillable by composition. Never gates; the caller composes + re-measures C.
    """
    rep = difficulty_gaps(matrix, n_buckets=n_buckets, min_per_bucket=min_per_bucket,
                          solved_threshold=solved_threshold)
    occ = rep["occupancy"]
    recs = []
    for b in rep["gap_buckets"]:
        source_buckets = [sb for sb in range(b) if occ[sb]]
        if not source_buckets:
            continue
        pool = [i for sb in source_buckets for i in occ[sb]]
        pairs: List = []
        for x in range(len(pool)):
            for y in range(x + 1, len(pool)):
                pairs.append((pool[x], pool[y]))
                if len(pairs) >= max_pairs:
                    break
            if len(pairs) >= max_pairs:
                break
        recs.append({"target_bucket": b, "source_buckets": source_buckets,
                     "example_source_pairs": pairs})
    return {"recommendations": recs, "gap_buckets": rep["gap_buckets"],
            "coverage": rep["coverage"], "advisory": True}


# ===========================================================================
# R10 — scaffold-relative difficulty (attacks the easy-end C gap R9 found)
# ===========================================================================
# A task's difficulty is RELATIVE to the scaffold: a PR fix that is "all-fail" for a
# single LLM call is often mid-difficulty for a multi-turn agent. Reading difficulty
# in ONE scaffold's frame (R9) mislabels the pool. These functions read difficulty in
# EACH scaffold's frame and select the tasks that are mid-difficulty FOR THAT frame,
# so every scaffold's leaderboard gets a discriminative, difficulty-spanning set.

def scaffold_relative_difficulty(matrices_by_scaffold: Dict[str, Matrix], *,
                                 solved_threshold: int = 1) -> Dict[str, object]:
    """Per-task difficulty (``1 − solve_rate``) computed in EACH scaffold's frame.

    ``matrices_by_scaffold`` maps scaffold name → its ``(task×model)`` matrix; all
    matrices MUST share the task order (row i is the same task everywhere). Returns
    ``by_scaffold`` (scaffold → per-task difficulty list), ``per_task`` (task index →
    {scaffold: difficulty}), and each scaffold's ``coverage`` (C). Makes a task's
    difficulty SHIFT across scaffolds explicit (hard for single-shot, mid for agent).
    """
    by_scaffold: Dict[str, List[float]] = {}
    covs: Dict[str, Optional[float]] = {}
    n_tasks = 0
    for name, m in matrices_by_scaffold.items():
        by_scaffold[name] = [1.0 - _task_solve_rate(row, solved_threshold) for row in m]
        covs[name] = difficulty_coverage(m, solved_threshold=solved_threshold)
        n_tasks = max(n_tasks, len(m))
    per_task = []
    for i in range(n_tasks):
        per_task.append({name: (by_scaffold[name][i] if i < len(by_scaffold[name]) else None)
                         for name in matrices_by_scaffold})
    return {"by_scaffold": by_scaffold, "per_task": per_task, "coverage": covs,
            "n_tasks": n_tasks}


def select_mid_difficulty(matrix: Matrix, k: Optional[int] = None, *,
                          band: tuple = (0.25, 0.75), solved_threshold: int = 1,
                          n_buckets: int = 4) -> List[int]:
    """Select task indices whose solve-rate lies in the mid band (most discriminative
    for THIS scaffold's frame), spread across difficulty within the band.

    Mid-difficulty tasks (solve-rate in ``[lo, hi]``) carry the most discrimination:
    all-solve/all-fail tasks are non-informative. Among the in-band tasks we keep the
    ``balanced_subset`` (difficulty spread) up to ``k`` (default: all in-band). A task
    all-fail for single-shot is out-of-band there but mid for an agent → it lands in
    the agent's set, not the single-shot's. Deterministic.
    """
    lo, hi = band
    in_band = [i for i, row in enumerate(matrix)
               if lo <= _task_solve_rate(row, solved_threshold) <= hi]
    if k is None or k >= len(in_band):
        return in_band
    sub = [matrix[i] for i in in_band]
    local = balanced_subset(sub, k, n_buckets=n_buckets, solved_threshold=solved_threshold)
    return [in_band[i] for i in local]


# ===========================================================================
# R11 — IRT (2PL) test-information item selection (the I axis)
# ===========================================================================
# The psychometric gold standard for benchmark quality: pick the items (tasks) that
# carry the most Fisher information about model ability at the operating point. The
# response matrix is BINARY (solved 0/1), so the correct model is the 2PL — which the
# grm_spectrum 5-category GRM reduces to in the m=1 case (a²·P·(1−P)). Item Fisher
# information is ADDITIVE (items conditionally independent), so max-total-info = the
# top-k items by individual information — no greedy interaction needed. Pure math,
# crown-seal clean, reads no reward gate (FA=0 untouched).

def _logit(p: float, eps: float = 1e-6) -> float:
    p = min(1.0 - eps, max(eps, p))
    return math.log(p / (1.0 - p))


def _point_biserial(item: Sequence[int], totals: Sequence[float]) -> float:
    """Point-biserial correlation of a binary item with the continuous total score."""
    n = len(item)
    if n < 2:
        return 0.0
    ones = [totals[j] for j in range(n) if item[j] == 1]
    zeros = [totals[j] for j in range(n) if item[j] == 0]
    if not ones or not zeros:
        return 0.0
    mean = sum(totals) / n
    var = sum((t - mean) ** 2 for t in totals) / n
    if var <= 1e-12:
        return 0.0
    sd = math.sqrt(var)
    m1 = sum(ones) / len(ones)
    m0 = sum(zeros) / len(zeros)
    p = len(ones) / n
    return ((m1 - m0) / sd) * math.sqrt(p * (1.0 - p))


def irt_item_stats(matrix: Matrix, *, solved_threshold: int = 1) -> List[Dict[str, float]]:
    """Estimate per-task 2PL IRT params ``{a, b, solve_rate}`` from a binary matrix.

    ``b`` (difficulty) = ``logit(1 − solve_rate)`` — harder tasks (low solve-rate) get
    higher ``b``. ``a`` (discrimination) = the item's point-biserial correlation with
    the per-model total score, rescaled to a strictly-positive discrimination (an
    all-pass / all-fail / non-correlating item floors to a small ``a`` — it discriminates
    nothing). Deterministic.
    """
    n_tasks, n_models = _dims(matrix)
    solved = [[1 if (x is not None and x >= solved_threshold) else 0 for x in row]
              for row in matrix]
    totals = [sum(solved[t][j] for t in range(n_tasks)) for j in range(n_models)]
    stats: List[Dict[str, float]] = []
    for t in range(n_tasks):
        sr = (sum(solved[t]) / n_models) if n_models else 0.0
        rpb = _point_biserial(solved[t], totals)
        a = max(0.2, abs(rpb) * 2.0 + 0.2)   # keep a>0; scale point-biserial -> discrimination
        stats.append({"a": a, "b": _logit(1.0 - sr), "solve_rate": sr})
    return stats


def item_information_2pl(a: float, b: float, theta: float) -> float:
    """2PL Fisher information of one binary item at ``theta``: ``a²·P·(1−P)``."""
    z = a * (theta - b)
    if z > 700:
        p = 1.0
    elif z < -700:
        p = 0.0
    else:
        p = 1.0 / (1.0 + math.exp(-z))
    return a * a * p * (1.0 - p)


def total_information_2pl(stats: Sequence[Dict[str, float]], theta: float = 0.0) -> float:
    """Test information = Σ item information at ``theta`` (items independent)."""
    return sum(item_information_2pl(s["a"], s["b"], theta) for s in stats)


def information_se(info: float) -> float:
    """SE(θ) = 1/√I (∞ when no information). Mirrors grm_spectrum.standard_error."""
    return math.inf if info <= 0 else 1.0 / math.sqrt(info)


def select_max_information(matrix: Matrix, k: int, *, theta: float = 0.0,
                           solved_threshold: int = 1) -> List[int]:
    """Select the ``k`` task indices carrying the most 2PL Fisher information at ``theta``.

    Because item information is additive, the max-total-information subset is exactly the
    top-``k`` items by individual information (ties break by lowest index → deterministic).
    This is a stricter, information-theoretic complement to R2's D+C objective.
    """
    stats = irt_item_stats(matrix, solved_threshold=solved_threshold)
    k = max(0, min(k, len(stats)))
    scored = sorted(range(len(stats)),
                    key=lambda i: (-item_information_2pl(stats[i]["a"], stats[i]["b"], theta), i))
    return sorted(scored[:k])


# ===========================================================================
# R12 — bootstrap confidence intervals on the MSQ axes (honest uncertainty)
# ===========================================================================
# At N≈6 tasks the MSQ point estimates (D=0.333, C=0.325) carry huge sampling
# uncertainty. A benchmark reported at research standard must state that uncertainty,
# not a bare point. This resamples TASKS (rows) with replacement and recomputes each
# axis, yielding a percentile CI + bootstrap SE per axis. DETERMINISTIC: a seeded
# ``random.Random`` (never bare ``random``) so a resume reproduces the interval.

def _percentile(sorted_vals: List[float], q: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_vals[lo]
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def msq_bootstrap_ci(matrix: Matrix, *, n_boot: int = 1000, ci: float = 0.95,
                     seed: int = 0, solved_threshold: int = 1, n_buckets: int = 4
                     ) -> Dict[str, object]:
    """Deterministic task-bootstrap confidence intervals for the D/C/M axes.

    Resamples the task rows with replacement ``n_boot`` times (seeded RNG →
    resume-reproducible), recomputing each axis each time; undefined draws (None) are
    dropped from that axis's distribution. Returns per-axis
    ``{estimate, lo, hi, se, n_valid}`` where ``estimate`` is the point estimate on the
    full set, ``[lo, hi]`` the central ``ci`` percentile interval, ``se`` the bootstrap
    standard deviation. Honest about thin N: intervals will be WIDE and that is the
    point. FA=0 untouched (reads only the response matrix).
    """
    import random as _random
    n_tasks, n_models = _dims(matrix)
    point = {"D": discriminative_yield(matrix, solved_threshold=solved_threshold),
             "C": difficulty_coverage(matrix, n_buckets=n_buckets, solved_threshold=solved_threshold),
             "M": monotonicity(matrix, solved_threshold=solved_threshold)}
    out: Dict[str, object] = {"n_tasks": n_tasks, "n_models": n_models,
                              "n_boot": int(n_boot), "ci": ci, "seed": seed}
    if n_tasks < 2:
        for ax in ("D", "C", "M"):
            out[ax] = {"estimate": point[ax], "lo": None, "hi": None, "se": None, "n_valid": 0}
        return out
    rng = _random.Random(seed)
    dists: Dict[str, List[float]] = {"D": [], "C": [], "M": []}
    for _ in range(int(n_boot)):
        idx = [rng.randrange(n_tasks) for _ in range(n_tasks)]
        res = [matrix[i] for i in idx]
        d = discriminative_yield(res, solved_threshold=solved_threshold)
        c = difficulty_coverage(res, n_buckets=n_buckets, solved_threshold=solved_threshold)
        m = monotonicity(res, solved_threshold=solved_threshold)
        if d is not None:
            dists["D"].append(d)
        if c is not None:
            dists["C"].append(c)
        if m is not None:
            dists["M"].append(m)
    lo_q, hi_q = (1 - ci) / 2, 1 - (1 - ci) / 2
    for ax in ("D", "C", "M"):
        vals = sorted(dists[ax])
        if vals:
            mean = sum(vals) / len(vals)
            var = sum((v - mean) ** 2 for v in vals) / len(vals)
            out[ax] = {"estimate": point[ax],
                       "lo": _percentile(vals, lo_q), "hi": _percentile(vals, hi_q),
                       "se": math.sqrt(var), "n_valid": len(vals)}
        else:
            out[ax] = {"estimate": point[ax], "lo": None, "hi": None, "se": None, "n_valid": 0}
    return out


# ===========================================================================
# R13 — power analysis: tasks required for a target MSQ precision
# ===========================================================================
# R12 showed D at N=6 has a ±0.33-wide interval. The actionable question is: how many
# tasks buy a research-grade interval? A standard-error scales as 1/√N, so from the
# bootstrap SE at the current N we extrapolate the N needed for a target CI half-width.
# This converts "the universe went 83→435 (dozens of tasks/day)" into a *precision*
# target. Deterministic (seeded via msq_bootstrap_ci). FA=0 untouched.

_Z95 = 1.959963984540054  # standard normal 97.5th percentile


def required_tasks_for_precision(matrix: Matrix, *, target_half_width: float,
                                 axis: str = "D", z: float = _Z95, seed: int = 0,
                                 n_boot: int = 1000, solved_threshold: int = 1,
                                 n_buckets: int = 4) -> Dict[str, object]:
    """Estimate the task count needed to shrink ``axis``'s 95% CI half-width to target.

    Uses the bootstrap SE at the current N (``msq_bootstrap_ci``) and the ``SE ∝ 1/√N``
    law: half-width ``h(N) = z·SE(N0)·√(N0/N)``, so the required ``N = N0·(z·SE(N0)/target)²``
    (rounded up). Returns ``{axis, n_now, se_now, half_width_now, target_half_width,
    required_n}``. ``required_n`` is None when the axis SE is undefined (too thin) and
    0 when SE is already 0 (perfectly precise, e.g. a degenerate axis). Never gates.
    """
    ci = msq_bootstrap_ci(matrix, n_boot=n_boot, seed=seed,
                          solved_threshold=solved_threshold, n_buckets=n_buckets)
    n_now = ci["n_tasks"]
    cell = ci.get(axis) or {}
    se = cell.get("se")
    out = {"axis": axis, "n_now": n_now, "se_now": se,
           "target_half_width": target_half_width}
    if se is None:
        out["half_width_now"] = None
        out["required_n"] = None
        return out
    hw_now = z * se
    out["half_width_now"] = hw_now
    if se <= 1e-12:
        out["required_n"] = 0  # already perfectly precise on this axis
    elif target_half_width <= 0:
        out["required_n"] = None
    else:
        out["required_n"] = int(math.ceil(n_now * (hw_now / target_half_width) ** 2))
    return out


def precision_curve(matrix: Matrix, sizes: Sequence[int], *, axis: str = "D",
                    z: float = _Z95, seed: int = 0, n_boot: int = 1000,
                    solved_threshold: int = 1, n_buckets: int = 4
                    ) -> List[Dict[str, float]]:
    """Expected 95% CI half-width of ``axis`` at each task count in ``sizes``.

    ``h(N) = z·SE(N0)·√(N0/N)`` from the current bootstrap SE. Returns
    ``[{n, half_width}, ...]`` — the precision-vs-size curve that sets a daily
    task-count target. Empty when the axis SE is undefined.
    """
    ci = msq_bootstrap_ci(matrix, n_boot=n_boot, seed=seed,
                          solved_threshold=solved_threshold, n_buckets=n_buckets)
    n_now = ci["n_tasks"]
    se = (ci.get(axis) or {}).get("se")
    if se is None or n_now < 1:
        return []
    hw0 = z * se * math.sqrt(n_now)  # = z·SE·√N0 ; then h(N)=hw0/√N
    curve = []
    for n in sizes:
        if n and n > 0:
            curve.append({"n": int(n), "half_width": hw0 / math.sqrt(n)})
    return curve


# ===========================================================================
# R15 — cross-scaffold quality comparison (which scaffold's benchmark discriminates)
# ===========================================================================
# The same tasks discriminate differently under different scaffolds (R10). This reads
# each scaffold's benchmark quality and answers: which scaffold frame gives the most
# discriminative / informative benchmark, and which tasks discriminate in ANY frame
# (the cross-scaffold discriminative union — the tasks worth keeping). FA=0 untouched.

def _row_splits(row: Sequence[int], threshold: int) -> bool:
    s = _solved_row(row, threshold)
    n = len(s)
    return n >= 2 and 0 < sum(s) < n


def cross_scaffold_quality(matrices_by_scaffold: Dict[str, Matrix], *,
                           solved_threshold: int = 1, n_buckets: int = 4
                           ) -> Dict[str, object]:
    """Per-scaffold quality card + cross-scaffold comparison.

    ``matrices_by_scaffold`` maps scaffold → its ``(task×model)`` matrix; the matrices
    SHOULD share the task order (row i = same task) for the union to be meaningful.
    Returns ``by_scaffold`` (scaffold → {D, C, M, irt_total_information}),
    ``best_by_discrimination`` / ``best_by_information`` (the winning scaffold, ties by
    name), ``discriminative_union`` (indices discriminating in ANY scaffold) and its
    fraction over the max task count. Deterministic; reads only response matrices.
    """
    by_scaffold: Dict[str, Dict[str, object]] = {}
    n_tasks_max = 0
    for name, m in matrices_by_scaffold.items():
        stats = irt_item_stats(m, solved_threshold=solved_threshold)
        by_scaffold[name] = {
            "D": discriminative_yield(m, solved_threshold=solved_threshold),
            "C": difficulty_coverage(m, n_buckets=n_buckets, solved_threshold=solved_threshold),
            "M": monotonicity(m, solved_threshold=solved_threshold),
            "irt_total_information": total_information_2pl(stats, 0.0),
            "n_tasks": len(m),
        }
        n_tasks_max = max(n_tasks_max, len(m))

    def _best(key: str) -> Optional[str]:
        cands = [(name, v[key]) for name, v in by_scaffold.items() if v.get(key) is not None]
        if not cands:
            return None
        # highest value, ties broken by scaffold name (deterministic)
        return min(sorted(cands, key=lambda t: t[0]), key=lambda t: -t[1])[0]

    union = []
    for i in range(n_tasks_max):
        if any(i < len(m) and _row_splits(m[i], solved_threshold)
               for m in matrices_by_scaffold.values()):
            union.append(i)
    return {"by_scaffold": by_scaffold,
            "best_by_discrimination": _best("D"),
            "best_by_information": _best("irt_total_information"),
            "discriminative_union": union,
            "discriminative_union_frac": (len(union) / n_tasks_max) if n_tasks_max else None,
            "n_tasks": n_tasks_max}


# ===========================================================================
# R16 — KR-20 reliability (psychometric internal consistency of the benchmark)
# ===========================================================================
# Alongside IRT information (R11), RELIABILITY is the other pillar of test quality:
# do the items measure a CONSISTENT latent ability? Kuder-Richardson 20 is the
# standard internal-consistency coefficient for binary items. A benchmark with low
# KR-20 is measuring noise, not a coherent skill. Pure math, FA=0 untouched.

def reliability_kr20(matrix: Matrix, *, solved_threshold: int = 1) -> Dict[str, object]:
    """Kuder-Richardson 20 internal-consistency reliability of a binary benchmark.

    ``KR20 = (k/(k−1))·(1 − Σ p_i·q_i / σ²_total)`` where ``k`` = tasks, ``p_i`` = task
    ``i``'s pass rate across models, ``q_i = 1 − p_i``, and ``σ²_total`` = variance of the
    per-model total scores. Returns ``{kr20, k, n_models, total_variance}``. ``kr20`` is
    None when ``k < 2`` or the total-score variance is 0 (no ability spread → reliability
    undefined). KR-20 ≤ 1; ``>0.7`` acceptable, ``>0.8`` good; can go negative when items
    are inconsistent. Deterministic; reads only the response matrix.
    """
    n_tasks, n_models = _dims(matrix)
    if n_tasks < 2 or n_models < 1:
        return {"kr20": None, "k": n_tasks, "n_models": n_models, "total_variance": None}
    solved = [[1 if (x is not None and x >= solved_threshold) else 0 for x in row]
              for row in matrix]
    # per-model total score
    totals = [sum(solved[t][j] for t in range(n_tasks)) for j in range(n_models)]
    mean = sum(totals) / n_models
    var_total = sum((x - mean) ** 2 for x in totals) / n_models
    sum_pq = 0.0
    for t in range(n_tasks):
        p = sum(solved[t]) / n_models
        sum_pq += p * (1.0 - p)
    if var_total <= 1e-12:
        return {"kr20": None, "k": n_tasks, "n_models": n_models, "total_variance": var_total}
    kr20 = (n_tasks / (n_tasks - 1)) * (1.0 - sum_pq / var_total)
    return {"kr20": kr20, "k": n_tasks, "n_models": n_models, "total_variance": var_total}


# ===========================================================================
# R18 — Spearman-Brown reliability prophecy (tasks needed for a target KR-20)
# ===========================================================================
# R13 gave the task count for a target CI half-width (precision-power). Its
# reliability twin: the Spearman-Brown prophecy formula extrapolates the test LENGTH
# needed to reach a target reliability from the current KR-20. Two independent
# task-count targets (precision + reliability) triangulate "how many tasks/day".

def tasks_for_reliability(matrix: Matrix, *, target_kr20: float,
                          solved_threshold: int = 1) -> Dict[str, object]:
    """Task count needed to reach ``target_kr20`` via the Spearman-Brown prophecy.

    From current reliability ``ρ`` at length ``k``, the length for ``ρ'`` is
    ``k' = k·[ρ'(1−ρ)] / [ρ(1−ρ')]`` (rounded up, floored at 1). Returns
    ``{current_kr20, current_k, target_kr20, required_k}``. ``required_k`` is None when
    the current reliability is undefined or ``≤ 0`` (a test measuring noise cannot be
    prophesied) or the target is not in ``(0, 1)``. Deterministic; FA=0 untouched.
    """
    rel = reliability_kr20(matrix, solved_threshold=solved_threshold)
    rho = rel.get("kr20")
    k = rel.get("k")
    out = {"current_kr20": rho, "current_k": k, "target_kr20": target_kr20}
    if rho is None or rho <= 0.0 or rho >= 1.0 or not (0.0 < target_kr20 < 1.0) or not k:
        out["required_k"] = None
        return out
    kprime = k * (target_kr20 * (1.0 - rho)) / (rho * (1.0 - target_kr20))
    out["required_k"] = max(1, int(math.ceil(kprime)))
    return out


# ===========================================================================
# R20 — benchmark readiness verdict (operationalize all metrics into GO/NO-GO)
# ===========================================================================
# The capstone: fold discrimination + reliability + precision into ONE daily
# advisory decision "is today's set benchmark-ready?", name the binding bottleneck,
# and recommend how many tasks close it (max of the precision- and reliability-power
# targets). ADVISORY ONLY — it never gates an accept (FA=0 untouched); it tells the
# pipeline when a day's set is too thin to report a research-grade leaderboard.

def benchmark_readiness(matrix: Matrix, *, min_D: float = 0.4, min_kr20: float = 0.7,
                        max_d_halfwidth: float = 0.15, ci_n_boot: int = 1000,
                        ci_seed: int = 0, solved_threshold: int = 1,
                        n_buckets: int = 4) -> Dict[str, object]:
    """Daily GO/NO-GO readiness verdict over the three research-grade constraints.

    ``ready`` iff discrimination ``D ≥ min_D`` AND reliability ``KR-20 ≥ min_kr20`` AND
    the D 95%-CI half-width ``≤ max_d_halfwidth`` (a None on any axis fails it — too thin
    to certify). On NO-GO, ``reasons`` lists each failing constraint, ``bottleneck`` is
    the one demanding the most tasks, and ``recommended_n`` = max(precision-required-N,
    reliability-required-N). Pure advisory — never gates an accept. Deterministic.
    """
    D = discriminative_yield(matrix, solved_threshold=solved_threshold)
    kr = reliability_kr20(matrix, solved_threshold=solved_threshold).get("kr20")
    ci = msq_bootstrap_ci(matrix, n_boot=ci_n_boot, seed=ci_seed,
                          solved_threshold=solved_threshold, n_buckets=n_buckets)
    dcell = ci.get("D") or {}
    d_hw = None
    if dcell.get("lo") is not None and dcell.get("hi") is not None:
        d_hw = (dcell["hi"] - dcell["lo"]) / 2.0

    prec = required_tasks_for_precision(matrix, target_half_width=max_d_halfwidth,
                                        axis="D", seed=ci_seed, n_boot=ci_n_boot,
                                        solved_threshold=solved_threshold,
                                        n_buckets=n_buckets).get("required_n")
    rel_n = tasks_for_reliability(matrix, target_kr20=min_kr20,
                                  solved_threshold=solved_threshold).get("required_k")
    req = [n for n in (prec, rel_n) if isinstance(n, int)]
    recommended_n = max(req) if req else None

    reasons = []
    checks = {
        "discrimination": (D is not None and D >= min_D, D, min_D, rel_n),
        "reliability": (kr is not None and kr >= min_kr20, kr, min_kr20, rel_n),
        "precision": (d_hw is not None and d_hw <= max_d_halfwidth, d_hw, max_d_halfwidth, prec),
    }
    for name, (ok, val, thr, need) in checks.items():
        if not ok:
            reasons.append({"constraint": name, "value": val, "threshold": thr,
                            "required_n": need})
    ready = not reasons
    # bottleneck = the failing constraint demanding the most tasks (ties by list order)
    bottleneck = None
    if reasons:
        with_n = [r for r in reasons if isinstance(r.get("required_n"), int)]
        bottleneck = (max(with_n, key=lambda r: r["required_n"])["constraint"]
                      if with_n else reasons[0]["constraint"])
    return {"ready": ready, "bottleneck": bottleneck, "reasons": reasons,
            "recommended_n": recommended_n,
            "card_summary": {"D": D, "kr20": kr, "d_ci_halfwidth": d_hw,
                             "n_tasks": ci.get("n_tasks")},
            "thresholds": {"min_D": min_D, "min_kr20": min_kr20,
                           "max_d_halfwidth": max_d_halfwidth}}


# ===========================================================================
# Public API — the complete multi-angle Selection-Quality instrument
# ===========================================================================
# Measurement axes: D (discriminative_yield), C (difficulty_coverage), M
# (monotonicity), A (angle_coverage), R (diversity), I (IRT total_information_2pl),
# KR-20 (reliability_kr20). Selection: informative / diverse / difficulty-balanced /
# monotonicity-filter / scaffold-relative-mid / IRT-max-information. Uncertainty:
# bootstrap CIs + precision- & reliability-power. One-call: benchmark_quality_report
# (the quality card) + benchmark_readiness (the daily GO/NO-GO). All pure, crown-seal
# clean (no reward-gate read), deterministic — FA=0 can never be perturbed.
__all__ = [
    # --- MSQ axes ---
    "msq_profile", "discriminative_yield", "difficulty_coverage", "monotonicity",
    "angle_coverage", "diversity", "redundancy_rate", "task_similarity", "signature_of",
    "reliability_kr20",
    # --- IRT (I axis) ---
    "irt_item_stats", "item_information_2pl", "total_information_2pl", "information_se",
    # --- selection mechanisms ---
    "select_informative_subset", "diverse_subset", "balanced_subset",
    "flag_noisy_tasks", "filter_monotonic", "select_mid_difficulty",
    "select_max_information",
    # --- difficulty coverage / scaffold-relative ---
    "difficulty_gaps", "synthesis_recommendations", "scaffold_relative_difficulty",
    # --- uncertainty + power ---
    "msq_bootstrap_ci", "required_tasks_for_precision", "precision_curve",
    "tasks_for_reliability",
    # --- one-call card + cross-scaffold + readiness ---
    "benchmark_quality_report", "cross_scaffold_quality", "benchmark_readiness",
]
