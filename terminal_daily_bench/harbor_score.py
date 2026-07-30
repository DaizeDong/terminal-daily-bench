"""harbor_score.py -- the gate-free execution-scoring core of Terminal Daily.

Three self-contained helpers lifted verbatim from the (private) construction
stack so the PUBLIC eval framework scores a model's patch by execution truth
WITHOUT importing the task-construction pipeline or the RC-VH accept gate.
false_accept=0 is a property of execution scoring, preserved here.

Pure stdlib (json/os/glob/pathlib/subprocess-env); no td_pipeline / rcvh import.
"""
from __future__ import annotations
import glob, json, os, re
from pathlib import Path
from typing import Any, Dict, List, Optional

def _read_harbor_reward(jobs_dir: str) -> Optional[float]:
    """Parse the Harbor trial reward out of a ``result.json`` under ``jobs_dir``.

    ROOT-CAUSE FIX (Round-5): Harbor does NOT print a bare reward float to stdout
    -- it renders a rich TABLE and writes the structured reward to
    ``<jobs_dir>/<TIMESTAMP>/result.json``. The earlier ``reward_leading_run_cmd``
    wrongly treated harbor's first stdout token as the reward float, so
    ``reward_to_solved(float(...))`` was ALWAYS False -> the oracle always read
    "failed" -> no positive certificate was ever minted -> every candidate was
    REJECTed (yield 0). The reward must instead be READ from result.json.

    The TOP-LEVEL aggregate ``result.json`` has the shape::

        { "stats": { "evals": { "<eval_key>": {
              "metrics": [ { "mean": <reward> } ],
              "reward_stats": { "reward": { "<reward>": ["taskid__hash"] } } } } } }

    where ``<eval_key>`` is the single eval (e.g. ``"oracle__adhoc"``). The reward
    is ``stats.evals.<eval_key>.metrics[0].mean``; for a single trial it is also
    recoverable as the (max) float key of ``reward_stats.reward``.

    Strategy: glob ``result.json`` recursively under ``jobs_dir`` and return the
    reward from the FIRST file that yields a parseable value (preferring the
    ``metrics[0].mean`` shape, falling back to the max float key of
    ``reward_stats.reward``). Robust to missing keys / malformed JSON: returns
    ``None`` (never raises) if nothing is parseable.
    """
    try:
        paths = sorted(glob.glob(os.path.join(jobs_dir, "**", "result.json"),
                                 recursive=True))
    except Exception:  # noqa: BLE001 -- a bad jobs_dir must not raise
        return None
    for path in paths:
        r = _reward_from_result_file(path)
        if r is not None:
            return r
    return None


def _maybe_inject_offline_eks(cmd: list) -> list:
    """Return ``cmd`` with the no-network `--ek` switch(es) appended when enabled.

    No-op (returns the input list object) unless BOTH:
      * the command targets the singularity backend (``-e singularity``) -- the
        switch is singularity-specific; a docker/other run is never touched, AND
      * the no-network cut is REQUESTED, by EITHER:
          - the task itself declaring run-offline (``-p`` task.toml has
            ``allow_internet = false``) -> AUTOMATIC on the literal default path
            (death point #1), OR
          - the ``RCVH_DISABLE_INTERNET`` env knob being truthy -> an explicit
            operator override (can only ADD isolation, never remove it).
    Idempotent: a switch already present (e.g. injected by
    ``verification.py._no_network_sing_kwargs``) is not duplicated. The
    ``RCVH_OFFLINE_DEPS_DIR`` bind is added only when it names an existing dir.

    This is the ONLY place the default repro-gate path acquires the no-network
    capability switch; keeping it idempotent + singularity-gated + task-driven
    means it composes cleanly with the verification stage's own explicit injection
    AND closes death point #1 without any global state on the literal default run.
    accept-only-on-proof is preserved: the switch both clears the harbor network
    policy validation AND physically cuts egress (--net --network none), so a task
    can never clear the policy without the cut actually being enforced; and an
    online task is never cut (its verdict-poisoning network stays as the gate's S0
    sees it).
    """
    # Singularity-specific: require `-e singularity` (run_trial emits it for the
    # non-docker backend). Never touch a docker/other-backend command.
    is_singularity = any(
        cmd[i] == "-e" and i + 1 < len(cmd) and cmd[i + 1] == "singularity"
        for i in range(len(cmd))
    )
    if not is_singularity:
        return cmd
    # Request the cut iff the task asked for it OR an operator override is set.
    if not (_disable_internet_enabled() or _task_declares_run_offline(cmd)):
        return cmd

    existing_eks = {
        cmd[i + 1] for i, t in enumerate(cmd) if t == "--ek" and i + 1 < len(cmd)
    }
    additions: list = []
    if _NO_NETWORK_EK_VALUE not in existing_eks:
        additions += ["--ek", _NO_NETWORK_EK_VALUE]
    deps_dir = _offline_deps_dir()
    if deps_dir is not None and not any(
        ek.startswith(_OFFLINE_DEPS_EK_KEY + "=") for ek in existing_eks
    ):
        additions += ["--ek", f"{_OFFLINE_DEPS_EK_KEY}={deps_dir}"]
    if not additions:
        return cmd
    return list(cmd) + additions


def _clean_subprocess_env(environ: "os._Environ[str] | Dict[str, str]") -> Dict[str, str]:
    """Return a copy of ``environ`` scrubbed of host conda / virtualenv pollution.

    Why (crack-D): the daily pipeline runs with the host conda ``base`` env active
    -- ``$PATH`` leads with ``.../miniconda3/bin`` (a ``python3`` WITHOUT
    ``uvicorn``) and a host ``PYTHONPATH``/``PYTHONHOME``/``CONDA_*`` are set. A
    harbor trial spawned with that inherited env can resolve the wrong interpreter
    (host conda instead of the project ``.venv`` or the container's own python),
    surfacing as ``ModuleNotFoundError: uvicorn`` in the in-container server. The
    gate runner only drives oracle/nop and so never tripped it; the live agent
    (terminus-2 + server) does.

    The scrub is conservative and deterministic:
      * DROP ``PYTHONPATH``/``PYTHONHOME`` entirely -- a host sys.path injection
        (e.g. ``/opt/rocm-.../amd_smi``) must never shadow the trial's interpreter,
        and apptainer would otherwise carry these into a non-``--containall`` path.
      * DROP conda bookkeeping (``CONDA_PREFIX``/``CONDA_DEFAULT_ENV``/
        ``CONDA_EXE``/``CONDA_PYTHON_EXE``/``CONDA_SHLVL``/``_CE_CONDA``/...) so no
        downstream activation hook re-derives the conda interpreter.
      * REWRITE ``$PATH`` to remove any entry under a conda root (``miniconda``/
        ``anaconda``/``conda``) AND any stale ``$VIRTUAL_ENV/bin``. The project
        ``.venv`` (where ``harbor`` and ``uvicorn`` live) is detected from the
        running interpreter's prefix and PREPENDED so the trial's ``python3`` /
        ``harbor`` resolve to it deterministically. If no venv is detectable the
        PATH is still conda-stripped (falling back to the system python).

    Pure and host-testable: takes the source mapping in, returns a fresh dict; it
    never mutates ``os.environ`` and makes no subprocess calls.
    """
    import os
    import sys

    env: Dict[str, str] = dict(environ)

    # 1) Drop interpreter-path / conda-bookkeeping pollution outright.
    for k in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"):
        env.pop(k, None)
    for k in list(env):
        ku = k.upper()
        if ku.startswith("CONDA") or ku.startswith("_CONDA") or ku == "_CE_CONDA":
            env.pop(k, None)

    # 2) Identify entries to strip from PATH: any conda-rooted dir, and any stale
    #    active-virtualenv bin that is NOT our project venv.
    def _is_conda_path(p: str) -> bool:
        pl = p.lower()
        return ("miniconda" in pl or "anaconda" in pl or
                os.sep + "conda" in pl or pl.rstrip(os.sep).endswith("condabin"))

    old_path = env.get("PATH", "") or ""
    parts = [p for p in old_path.split(os.pathsep) if p]

    # Our project venv bin (where harbor + uvicorn live): derive from the running
    # interpreter if it is inside a venv (``sys.prefix != sys.base_prefix``);
    # otherwise honour an explicit ``VIRTUAL_ENV`` only if it is not conda.
    venv_bin = ""
    try:
        in_venv = getattr(sys, "prefix", "") != getattr(sys, "base_prefix", sys.prefix)
        if in_venv and sys.prefix and not _is_conda_path(sys.prefix):
            venv_bin = os.path.join(sys.prefix, "bin")
    except Exception:
        venv_bin = ""
    if not venv_bin:
        ve = env.get("VIRTUAL_ENV", "")
        if ve and not _is_conda_path(ve):
            venv_bin = os.path.join(ve, "bin")

    # A stale VIRTUAL_ENV pointing at conda must not keep its bin on PATH.
    stale_venv_bin = ""
    ve = environ.get("VIRTUAL_ENV", "") if hasattr(environ, "get") else env.get("VIRTUAL_ENV", "")
    if ve and _is_conda_path(ve):
        stale_venv_bin = os.path.join(ve, "bin")
        env.pop("VIRTUAL_ENV", None)

    kept = [
        p for p in parts
        if not _is_conda_path(p)
        and os.path.normpath(p) != os.path.normpath(stale_venv_bin or "\0")
    ]
    if venv_bin:
        nv = os.path.normpath(venv_bin)
        kept = [p for p in kept if os.path.normpath(p) != nv]
        kept.insert(0, venv_bin)
        env["VIRTUAL_ENV"] = os.path.dirname(venv_bin)
    if not kept:
        # Never hand the child an empty PATH -- fall back to a sane system default.
        kept = ["/usr/local/bin", "/usr/bin", "/bin", "/usr/local/sbin", "/usr/sbin"]
    env["PATH"] = os.pathsep.join(kept)
    return env


# Public aliases (stable released names):
read_harbor_reward = _read_harbor_reward
maybe_inject_offline_eks = _maybe_inject_offline_eks
clean_subprocess_env = _clean_subprocess_env

__all__ = ["read_harbor_reward","maybe_inject_offline_eks","clean_subprocess_env",
           "_read_harbor_reward","_maybe_inject_offline_eks","_clean_subprocess_env"]



# --- lifted helper closure (verbatim from private rcvh.live; self-contained) ---
def _offline_deps_dir() -> Optional[str]:
    """Return the configured offline server-deps dir, or None.

    Only honoured (non-None) when it names an existing directory, so a stale/typo
    path is silently ignored rather than handed to harbor as a bind that would
    fail. ``RCVH_OFFLINE_DEPS_DIR`` is the knob.
    """
    raw = (os.environ.get("RCVH_OFFLINE_DEPS_DIR") or "").strip()
    if raw and os.path.isdir(raw):
        return raw
    return None


def _task_declares_run_offline(cmd: list) -> bool:
    """True iff the `-p <task dir>` in ``cmd`` declares a runtime-offline policy.

    Reads the task's ``task.toml`` and returns True when ``[environment]
    allow_internet`` is false -- the signal ``env_generation`` writes for a
    build-online/run-offline task (which harbor migrates to network_mode=
    NO_NETWORK). This is what makes the no-network `--ek` injection AUTOMATIC on
    the literal default path: the task itself carries the run-offline intent, so
    the repro gate cuts egress for exactly those tasks and NOTHING else.

    accept-only-on-proof: an online task (allow_internet=true, or no task.toml /
    unreadable) returns False -> NOT cut -> its online exec path is unchanged. We
    only ever ADD isolation for a task that explicitly asked to run offline; we
    never infer "online" into a cut. Tolerant of a missing/odd toml (returns
    False -> default online behaviour, never raises out of the runner).
    """
    p_dir = None
    for i, tok in enumerate(cmd):
        if tok == "-p" and i + 1 < len(cmd):
            p_dir = cmd[i + 1]
            break
    if not p_dir:
        return False
    toml_path = os.path.join(p_dir, "task.toml")
    try:
        with open(toml_path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return False
    # Match `allow_internet = false` (TOML bare bool, optional surrounding ws). A
    # tiny regex is sufficient + dependency-free; the value env_generation writes
    # is always a bare lower-case bool.
    m = re.search(r"(?m)^\s*allow_internet\s*=\s*(true|false)\s*$", text)
    return bool(m and m.group(1) == "false")


def _disable_internet_enabled() -> bool:
    """True iff the no-network `--ek` injection is switched on via env.

    Treats the usual truthy spellings as on ("1"/"true"/"yes"/"on", any case); an
    unset or falsey value leaves the online default path untouched (fail-closed:
    we never silently cut the net unless explicitly asked).
    """
    raw = (os.environ.get("RCVH_DISABLE_INTERNET") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _reward_from_result_file(path: str) -> Optional[float]:
    """Extract the reward float from a single ``result.json``; None if not found.

    Tries ``stats.evals.<key>.metrics[0].mean`` first (the TOP-LEVEL aggregate
    shape), then the max float key of ``stats.evals.<key>.reward_stats.reward``.
    Any missing key / wrong type / malformed JSON -> None (never raises)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:  # noqa: BLE001 -- malformed/unreadable -> not parseable
        return None
    try:
        evals = (data.get("stats", {}) or {}).get("evals", {}) or {}
    except AttributeError:
        return None
    if not isinstance(evals, dict):
        return None
    for ev in evals.values():
        if not isinstance(ev, dict):
            continue
        # 1) metrics[0].mean (preferred).
        metrics = ev.get("metrics")
        if isinstance(metrics, list) and metrics and isinstance(metrics[0], dict):
            mean = metrics[0].get("mean")
            if isinstance(mean, (int, float)):
                return float(mean)
        # 2) fallback: max float key of reward_stats.reward (single-trial).
        rewards = (ev.get("reward_stats", {}) or {}).get("reward", {})
        if isinstance(rewards, dict) and rewards:
            floats = []
            for k in rewards:
                try:
                    floats.append(float(k))
                except (TypeError, ValueError):
                    continue
            if floats:
                return max(floats)
    return None


# ---------------------------------------------------------------------------
# DEFAULT-PATH no-network `--ek` injection (Cycle 1.5 env-config death point #1).
# ---------------------------------------------------------------------------
# The most-fatal of the 3 env-config death points: a generated run-offline task's
# task.toml carries ``allow_internet=false`` -> harbor migrates it to
# ``network_mode=NO_NETWORK`` -> at env CONSTRUCTION (before any container starts)
# ``BaseEnvironment._validate_network_policy_support`` raises ``ValueError`` UNLESS
# the singularity backend ADVERTISES ``disable_internet`` capability, which it does
# IFF launched with ``--ek singularity_disable_internet=true``. The audited default
# ``td_phase0.execution.SING_KWARGS`` does NOT carry that switch, so EVERY repro-gate
# oracle/nop/rerun trial on the DEFAULT path crashed with ValueError -> reward=0 ->
# verdict=oracle_unsolvable. The repro gate funnels ALL its harbor trials through
# this single runner (``run_trial(run_cmd=reward_leading_run_cmd)``), so injecting
# the switch HERE closes the death point for the literal default path without
# touching the frozen ``td_phase0`` SING_KWARGS.
#
# OPT-IN + fail-closed-on-proof. Injection is gated on the ``RCVH_DISABLE_INTERNET``
# env knob: UNSET -> the online default path is byte-identical to before (no `--ek`
# added, no behaviour change; the offline unit tests assert this). When SET, the
# switch is added ONLY to a singularity-backed command (``-e singularity`` present)
# and ONLY if not already there (idempotent -- ``verification.py``'s
# ``_no_network_sing_kwargs`` may have added it). accept-only-on-proof is preserved
# BECAUSE ``singularity_disable_internet=true`` is not a mere capability label: the
# backend, on the no-network path, PHYSICALLY adds ``apptainer exec --net --network
# none`` (a fresh empty netns). So the SAME switch that stops S0/policy rejection
# also enforces the egress cut -- the two can never drift apart. The optional
# ``RCVH_OFFLINE_DEPS_DIR`` knob additionally binds a host dir of pre-installed
# server deps (``--ek singularity_offline_deps_dir=<dir>``) as the offline
# server-start fallback (death point #3's server side).
_NO_NETWORK_EK_VALUE = "singularity_disable_internet=true"
_OFFLINE_DEPS_EK_KEY = "singularity_offline_deps_dir"


_OFFLINE_DEPS_EK_KEY = "singularity_offline_deps_dir"


_NO_NETWORK_EK_VALUE = "singularity_disable_internet=true"
