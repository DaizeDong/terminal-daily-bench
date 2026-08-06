"""harbor_score.py -- the gate-free execution-scoring core of Terminal Daily.

Three self-contained helpers lifted verbatim from the (private) construction
stack so the PUBLIC eval framework scores a model's patch by execution truth
WITHOUT importing the task-construction pipeline or the RC-VH accept gate.
It proves the reward source, not semantic verifier false-accept.

Pure stdlib (json/os/glob/pathlib/subprocess-env); no td_pipeline / rcvh import.
"""
from __future__ import annotations
import json, math, os, re, stat, tomllib
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional

_MAX_RESULT_BYTES = 16 * 1024 * 1024


class HarborResultSnapshot(NamedTuple):
    """One fd-pinned authoritative result; reward and digest consume these bytes."""

    relative_path: str
    data: bytes


class HarborAggregateStatus(NamedTuple):
    """Strict terminal counters parsed from the same fd-pinned aggregate bytes."""

    reward: float
    n_total_trials: int
    n_completed_trials: int
    n_errored_trials: int
    n_running_trials: int
    n_pending_trials: int
    n_cancelled_trials: int
    n_retries: int
    eval_n_trials: int
    eval_n_errors: int
    clean: bool


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

    Exactly one direct-child aggregate ``<run>/result.json`` must exist under
    ``jobs_dir`` and it must have the single-eval aggregate schema.  Harbor
    0.13.1 also writes one ``<run>/<trial>/result.json`` per trial; those nested
    records are path- and metadata-validated but never participate in reward
    selection.  A second aggregate, cross-run/deeper shadow, fallback shape,
    boolean, NaN/Inf or out-of-range value all fail closed to ``None``.  The
    aggregate must also contain complete, internally consistent terminal
    counters.  Errored, cancelled, running or pending trials and non-empty
    ``exception_stats`` are diagnostic artifacts, not accepted scores.
    """
    snapshot = authoritative_harbor_result_snapshot(jobs_dir)
    return (
        reward_from_harbor_result_snapshot(snapshot)
        if snapshot is not None else None
    )


def authoritative_harbor_result_snapshot(
    jobs_dir: str,
) -> Optional[HarborResultSnapshot]:
    """Open, validate and read the sole result exactly once through pinned fds.

    The result and its run directory are opened with ``O_NOFOLLOW`` relative to an
    already-open jobs directory.  Device/inode facts must match the enumerated
    path, hardlinks are rejected, and metadata must remain stable across the
    bounded read.  Callers parse and hash the returned bytes; they never reopen
    the attacker-influenced path.
    """
    root_fd = run_fd = result_fd = None
    try:
        root = Path(jobs_dir).resolve(strict=True)
        if not root.is_dir():
            return None
        all_named = sorted(root.rglob("result.json"))
        candidates = sorted(root.glob("*/result.json"))
        if (len(candidates) != 1 or candidates[0].is_symlink()
                or candidates[0].parent.is_symlink()):
            return None
        candidate = candidates[0]
        candidate_relative = candidate.relative_to(root)
        nested = [path for path in all_named if path != candidate]
        nested_facts = []
        for path in nested:
            relative = path.relative_to(root)
            if (len(relative.parts) != 3
                    or relative.parts[0] != candidate_relative.parts[0]
                    or relative.name != "result.json"
                    or path.is_symlink() or path.parent.is_symlink()
                    or not path.is_file()):
                return None
            path_stat = path.lstat()
            parent_stat = path.parent.lstat()
            if path_stat.st_nlink != 1 or not path.parent.is_dir():
                return None
            nested_facts.append((path, path_stat, parent_stat))
        candidate_stat = candidate.lstat()
        parent_stat = candidate.parent.lstat()
        root_stat = root.lstat()
        if (not os.path.isfile(candidate) or candidate_stat.st_nlink != 1
                or not os.path.isdir(candidate.parent)):
            return None
        relative = candidate_relative
        if len(relative.parts) != 2 or relative.name != "result.json":
            return None

        nofollow = getattr(os, "O_NOFOLLOW", 0)
        cloexec = getattr(os, "O_CLOEXEC", 0)
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | nofollow | cloexec)
        opened_root = os.fstat(root_fd)
        if (opened_root.st_dev, opened_root.st_ino) != (root_stat.st_dev, root_stat.st_ino):
            return None
        run_fd = os.open(
            relative.parts[0], os.O_RDONLY | os.O_DIRECTORY | nofollow | cloexec,
            dir_fd=root_fd,
        )
        opened_parent = os.fstat(run_fd)
        if ((opened_parent.st_dev, opened_parent.st_ino)
                != (parent_stat.st_dev, parent_stat.st_ino)):
            return None
        result_fd = os.open(
            "result.json", os.O_RDONLY | nofollow | cloexec, dir_fd=run_fd,
        )
        before = os.fstat(result_fd)
        if (not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or (before.st_dev, before.st_ino)
                != (candidate_stat.st_dev, candidate_stat.st_ino)
                or before.st_size < 0 or before.st_size > _MAX_RESULT_BYTES):
            return None
        chunks: List[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(result_fd, min(1024 * 1024, remaining))
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(result_fd, 1):
            return None
        after = os.fstat(result_fd)
        stable_fields = (
            "st_dev", "st_ino", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns",
        )
        if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
            return None
        if nested:
            try:
                aggregate = json.loads(b"".join(chunks).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None
            if not isinstance(aggregate, dict):
                return None
            n_total = aggregate.get("n_total_trials")
            if (isinstance(n_total, bool) or not isinstance(n_total, int)
                    or n_total != len(nested)):
                return None
            try:
                evals = aggregate["stats"]["evals"]
            except (KeyError, TypeError):
                return None
            if not isinstance(evals, dict):
                return None
            bound_trials = set()

            def collect_trial_names(value: Any) -> None:
                if isinstance(value, dict):
                    for child in value.values():
                        collect_trial_names(child)
                elif isinstance(value, list):
                    for child in value:
                        if isinstance(child, str):
                            bound_trials.add(child)
                        else:
                            collect_trial_names(child)

            for eval_result in evals.values():
                if not isinstance(eval_result, dict):
                    return None
                collect_trial_names(eval_result.get("reward_stats", {}))
                collect_trial_names(eval_result.get("exception_stats", {}))
            nested_names = {path.parent.name for path in nested}
            if bound_trials != nested_names:
                return None
        current_root = root.lstat()
        current_parent = candidate.parent.lstat()
        current_candidate = candidate.lstat()
        if ((current_root.st_dev, current_root.st_ino)
                != (opened_root.st_dev, opened_root.st_ino)
                or (current_parent.st_dev, current_parent.st_ino)
                != (opened_parent.st_dev, opened_parent.st_ino)
                or (current_candidate.st_dev, current_candidate.st_ino)
                != (before.st_dev, before.st_ino)
                or current_candidate.st_nlink != 1):
            return None
        for nested_path, nested_before, nested_parent_before in nested_facts:
            nested_after = nested_path.lstat()
            nested_parent_after = nested_path.parent.lstat()
            if (nested_after.st_nlink != 1
                    or any(getattr(nested_before, field)
                           != getattr(nested_after, field)
                           for field in stable_fields)
                    or (nested_parent_before.st_dev, nested_parent_before.st_ino,
                        nested_parent_before.st_mtime_ns,
                        nested_parent_before.st_ctime_ns)
                    != (nested_parent_after.st_dev, nested_parent_after.st_ino,
                        nested_parent_after.st_mtime_ns,
                        nested_parent_after.st_ctime_ns)):
                return None
        # Re-enumeration closes insertion/removal races around the single path.
        if (sorted(root.rglob("result.json")) != all_named
                or sorted(root.glob("*/result.json")) != [candidate]):
            return None
        return HarborResultSnapshot(relative.as_posix(), b"".join(chunks))
    except (OSError, RuntimeError, ValueError):
        return None
    finally:
        for fd in (result_fd, run_fd, root_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass


def authoritative_harbor_result_path(jobs_dir: str) -> Optional[str]:
    """Compatibility path accessor; authority checks still use one fd snapshot."""
    snapshot = authoritative_harbor_result_snapshot(jobs_dir)
    if snapshot is None:
        return None
    return str(Path(jobs_dir).resolve() / snapshot.relative_path)


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

__all__ = [
    "HarborAggregateStatus", "HarborResultSnapshot", "read_harbor_reward",
    "authoritative_harbor_result_path", "authoritative_harbor_result_snapshot",
    "harbor_aggregate_status_from_snapshot", "reward_from_harbor_result_snapshot",
    "maybe_inject_offline_eks",
    "clean_subprocess_env", "_read_harbor_reward", "_maybe_inject_offline_eks",
    "_clean_subprocess_env",
]



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
        with open(toml_path, "rb") as fh:
            config = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    environment = config.get("environment") if isinstance(config, dict) else None
    if not isinstance(environment, dict):
        return False
    network_mode = environment.get("network_mode")
    if network_mode is not None:
        return network_mode == "no-network"
    return environment.get("allow_internet") is False


def _disable_internet_enabled() -> bool:
    """True iff the no-network `--ek` injection is switched on via env.

    Treats the usual truthy spellings as on ("1"/"true"/"yes"/"on", any case); an
    unset or falsey value leaves the online default path untouched (fail-closed:
    we never silently cut the net unless explicitly asked).
    """
    raw = (os.environ.get("RCVH_DISABLE_INTERNET") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def harbor_aggregate_status_from_snapshot(
    snapshot: HarborResultSnapshot,
) -> Optional[HarborAggregateStatus]:
    """Parse reward plus strict terminal counters from one pinned aggregate.

    Harbor can exit zero while recording a model-level agent exception.  Such an
    aggregate is useful diagnostics, but it must not look like a clean scored
    completion.  Missing counters fail closed; there is no compatibility path
    that infers success from ``metrics.mean`` alone.
    """
    try:
        data = json.loads(snapshot.data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    stats = data.get("stats")
    if not isinstance(stats, dict):
        return None
    evals = stats.get("evals")
    if not isinstance(evals, dict) or len(evals) != 1:
        return None

    def bounded_int(value: Any, *, upper: int = 1_000_000) -> Optional[int]:
        if type(value) is not int or value < 0 or value > upper:
            return None
        return value

    n_total = bounded_int(data.get("n_total_trials"))
    n_completed = bounded_int(stats.get("n_completed_trials"))
    n_errored = bounded_int(stats.get("n_errored_trials"))
    n_running = bounded_int(stats.get("n_running_trials"))
    n_pending = bounded_int(stats.get("n_pending_trials"))
    n_cancelled = bounded_int(stats.get("n_cancelled_trials"))
    n_retries = bounded_int(stats.get("n_retries"))
    counters = (
        n_total, n_completed, n_errored, n_running, n_pending, n_cancelled,
        n_retries,
    )
    # ``tdb run`` requests exactly one MODEL x TASK trial.  Accepting an
    # unexpected multi-trial aggregate would silently change the cell's score
    # denominator and make its provenance ambiguous.
    if any(value is None for value in counters) or n_total != 1:
        return None
    assert n_total is not None and n_completed is not None
    assert n_errored is not None and n_running is not None
    assert n_pending is not None and n_cancelled is not None
    assert n_retries is not None
    if (n_completed != n_total or n_errored > n_total
            or n_cancelled > n_total or n_running > n_total
            or n_pending > n_total):
        return None

    ev = next(iter(evals.values()))
    if not isinstance(ev, dict):
        return None
    eval_n_trials = bounded_int(ev.get("n_trials"))
    eval_n_errors = bounded_int(ev.get("n_errors"))
    if (eval_n_trials is None or eval_n_errors is None
            or eval_n_trials != n_total or eval_n_errors != n_errored):
        return None
    metrics = ev.get("metrics")
    if not isinstance(metrics, list) or len(metrics) != 1 or not isinstance(metrics[0], dict):
        return None
    mean = metrics[0].get("mean")
    if isinstance(mean, bool) or not isinstance(mean, (int, float)):
        return None
    reward = float(mean)
    if not math.isfinite(reward) or not 0.0 <= reward <= 1.0:
        return None

    reward_stats = ev.get("reward_stats")
    if not isinstance(reward_stats, dict):
        return None
    reward_distribution = reward_stats.get("reward")
    if not isinstance(reward_distribution, dict) or not reward_distribution:
        return None
    reward_trials: List[str] = []
    weighted_reward = 0.0
    for reward_key, trial_names in reward_distribution.items():
        try:
            reward_value = float(reward_key)
        except (TypeError, ValueError):
            return None
        if (not math.isfinite(reward_value) or not 0.0 <= reward_value <= 1.0
                or not isinstance(trial_names, list) or not trial_names
                or any(not isinstance(name, str) or not name for name in trial_names)):
            return None
        reward_trials.extend(trial_names)
        weighted_reward += reward_value * len(trial_names)
    if len(reward_trials) != n_total or len(set(reward_trials)) != n_total:
        return None
    if not math.isclose(
        reward, weighted_reward / n_total, rel_tol=0.0, abs_tol=1e-12
    ):
        return None

    exception_stats = ev.get("exception_stats")
    if not isinstance(exception_stats, dict):
        return None
    exception_trials: List[str] = []
    for exception_name, trial_names in exception_stats.items():
        if (not isinstance(exception_name, str) or not exception_name
                or not isinstance(trial_names, list)
                or any(not isinstance(name, str) or not name for name in trial_names)):
            return None
        exception_trials.extend(trial_names)
    if (len(exception_trials) != n_errored
            or len(set(exception_trials)) != n_errored
            or not set(exception_trials).issubset(reward_trials)):
        return None

    clean = (
        n_errored == 0
        and n_running == 0
        and n_pending == 0
        and n_cancelled == 0
        and eval_n_errors == 0
        and not exception_stats
    )
    return HarborAggregateStatus(
        reward=reward,
        n_total_trials=n_total,
        n_completed_trials=n_completed,
        n_errored_trials=n_errored,
        n_running_trials=n_running,
        n_pending_trials=n_pending,
        n_cancelled_trials=n_cancelled,
        n_retries=n_retries,
        eval_n_trials=eval_n_trials,
        eval_n_errors=eval_n_errors,
        clean=clean,
    )


def reward_from_harbor_result_snapshot(
    snapshot: HarborResultSnapshot,
) -> Optional[float]:
    """Return reward only for a complete, internally clean aggregate."""
    status = harbor_aggregate_status_from_snapshot(snapshot)
    if status is None or not status.clean:
        return None
    return status.reward


def _reward_from_result_file(path: str) -> Optional[float]:
    """Legacy direct-file helper; replay authority uses the fd snapshot API."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    return reward_from_harbor_result_snapshot(HarborResultSnapshot("result.json", data))


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
