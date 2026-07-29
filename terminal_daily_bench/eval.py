#!/usr/bin/env python3
"""model-eval helper: one MODEL x one TASK, scored by the execution gate.

This is the reusable core behind ``scripts/v2/model_eval.sh``. It runs ONE model
against ONE harbor-native task package and returns an execution-truth score. The
model is the SUBJECT under test; it NEVER judges. Scoring is the harbor
execution gate and nothing else -- so ``false_accept`` is 0 by construction.

Scaffold (``single_shot_patch``)
--------------------------------
The model is shown the task instruction + the source file(s) the reference
solution touches, and asked to emit a git-apply-compatible unified diff. That
diff is written as ``solution/oracle.patch`` into a RUN COPY of the task, and
harbor's built-in ``oracle`` agent is run: it applies the (now model-authored)
patch via ``solution/solve.sh`` inside the task's apptainer container, then
harbor RE-LAYS the protected ``tests/`` from the trusted task package and runs
them with trusted binaries on a face the agent never touched, writing the reward
to ``result.json``. We read that reward with the SAME reader the admission gate
uses (``rcvh.live._read_harbor_reward``) -- byte-for-byte execution truth.

Because the protected tests are re-laid by harbor from the trusted package (not
from the model's patch), the model cannot tamper with the judge: a patch that
edits ``tests/`` changes only the agent-side workspace, which is discarded before
scoring. This is why the ``single_shot_patch`` scaffold keeps the
execution-proof gate the SOLE authority (false_accept = 0).

This is a SINGLE-SHOT, solution-localized scaffold -- NOT a multi-turn terminus-2
agent loop (the model gets the file to fix and one shot at the diff; it does not
explore the repo itself). A multi-turn agent scaffold plugs in via the harness
adapter contract (see CONTRIBUTING.md).

Model call
----------
Generic OpenAI-compatible endpoint, configured by env so the bundle is not tied to
any vendor: ``OPENAI_BASE_URL`` (default ``https://api.openai.com/v1``; point it at
OpenAI / OpenRouter / vLLM / LiteLLM / a local server) + ``OPENAI_API_KEY`` (bearer,
read from env, never stored). Calls ``<base>/chat/completions``; if the upstream
rejects ``max_tokens`` (some reasoning models), it retries with
``max_completion_tokens`` automatically.

Special model id ``oracle`` runs the task's REAL ``oracle.patch`` (no model call)
-- the baseline that proves the gate returns 1.0 on this task.

BAD-safe: any failure (no patch, patch doesn't apply, hung trial, unparseable
result) yields reward 0.0 / solved False with the cause recorded -- never a
positive score on a crash.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Optional

# The harness's own authoritative primitives (reused, NOT reinvented):
#   * _read_harbor_reward  -> the reward-truth reader the admission gate uses
#   * _maybe_inject_offline_eks -> the task-driven no-network `--ek` switch
#   * _clean_subprocess_env -> the host-conda scrub the live eval path uses
from .harbor_score import _read_harbor_reward, _maybe_inject_offline_eks
from .harbor_score import _clean_subprocess_env

# Singularity `--ek` backend knobs. Paths are env-driven so nothing host-specific
# ships: set TDB_SIF_CACHE / TDB_OVERLAY_DIR to override the generic defaults.
_DEFAULT_EKS = [
    f"singularity_image_cache_dir={os.environ.get('TDB_SIF_CACHE', './.tdb_work/sif_cache')}",
    "singularity_overlay_size_mb=8192",
    f"singularity_overlay_dir={os.environ.get('TDB_OVERLAY_DIR', '/tmp/tdb_overlays')}",
    "singularity_health_timeout_sec=480",
    "singularity_mksquashfs_mem=2G",
]


def _log(msg: str) -> None:
    print(f"[model_eval] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# model call -- GENERIC OpenAI-compatible endpoint (point it at ANY provider)
# ---------------------------------------------------------------------------
# Configure via env, so the public bundle is not tied to any one vendor:
#   OPENAI_BASE_URL  (default https://api.openai.com/v1)  -- any OpenAI-compatible
#                    endpoint: OpenAI, OpenRouter, vLLM, LiteLLM, a local server, ...
#   OPENAI_API_KEY   -- the bearer key for that endpoint (read from env, never stored).
def _openai_post(payload: Dict[str, Any], timeout: int = 120) -> Dict[str, Any]:
    """POST an OpenAI-format chat/completions payload to ``$OPENAI_BASE_URL``."""
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    key = os.environ.get("OPENAI_API_KEY", "")
    cmd = [
        "curl", "-sS", "-m", str(timeout),
        "-H", f"Authorization: Bearer {key}",
        "-H", "content-type: application/json",
        "-X", "POST", f"{base}/chat/completions",
        "--data-binary", "@-",  # body via STDIN (avoid ARG_MAX E2BIG)
    ]
    proc = subprocess.run(cmd, input=json.dumps(payload), capture_output=True,
                          text=True, timeout=timeout + 15)
    raw = (proc.stdout or "").strip()
    if not raw:
        raise RuntimeError(f"empty response (curl rc={proc.returncode}): "
                           f"{(proc.stderr or '')[:200]}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"non-JSON response: {raw[:300]}") from e


def call_model(model: str, prompt: str, max_tokens: int = 4096,
               timeout: int = 180, retries: int = 1) -> str:
    """Call ``model`` on the configured OpenAI-compatible endpoint; return its text.

    Retries once on an empty/timeout response (cold models can 504 on first hit).
    Falls back from ``max_tokens`` to ``max_completion_tokens`` for reasoning models
    that reject the former.
    """
    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            return _call_model_once(model, prompt, max_tokens, timeout)
        except RuntimeError as e:
            last_err = e
            _log(f"model call attempt {attempt + 1} failed: {e}")
            time.sleep(2)
    raise last_err  # type: ignore[misc]


def _call_model_once(model: str, prompt: str, max_tokens: int, timeout: int) -> str:
    def _chat(tok_field: str) -> Dict[str, Any]:
        return _openai_post({"model": model, tok_field: max_tokens,
                             "messages": [{"role": "user", "content": prompt}]},
                            timeout=timeout)
    data = _chat("max_tokens")
    if "error" in data and "max_completion_tokens" in json.dumps(data.get("error", "")):
        data = _chat("max_completion_tokens")  # reasoning models reject max_tokens
    if "error" in data:
        raise RuntimeError(f"endpoint error: {str(data['error'])[:300]}")
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"no choices in response: {json.dumps(data)[:300]}")
    return (choices[0].get("message", {}) or {}).get("content") or ""


# ---------------------------------------------------------------------------
# task package helpers
# ---------------------------------------------------------------------------
def load_task(task_dir: str) -> Dict[str, Any]:
    with open(os.path.join(task_dir, "task.toml"), "rb") as fh:
        return tomllib.load(fh)


def solution_target_files(task_dir: str) -> List[str]:
    """Repo-relative paths the reference solution patch touches (for context)."""
    patch = os.path.join(task_dir, "solution", "oracle.patch")
    files: List[str] = []
    try:
        with open(patch, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = re.match(r"^\+\+\+ b/(.+?)\s*$", line)
                if m and m.group(1) != "/dev/null":
                    files.append(m.group(1))
    except OSError:
        pass
    # dedupe, preserve order
    seen: set = set()
    out: List[str] = []
    for f in files:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def extract_repo_files(sif: str, rel_paths: List[str], repo_root: str = "/app/repo",
                       max_bytes: int = 24000) -> Dict[str, str]:
    """Read repo files out of the SIF image (read-only apptainer exec). Best-effort."""
    if not rel_paths:
        return {}
    binname = shutil.which("apptainer") or shutil.which("singularity")
    if not binname:
        _log("no apptainer/singularity binary for context extraction")
        return {}
    out: Dict[str, str] = {}
    # One exec, cat each file with a unique separator so we can split.
    sep = "@@@V2FILE@@@"
    inner = "; ".join(
        f'echo "{sep}{p}"; cat "{repo_root}/{p}" 2>/dev/null || echo "(missing)"'
        for p in rel_paths
    )
    try:
        proc = subprocess.run(
            [binname, "exec", sif, "bash", "-lc", inner],
            capture_output=True, text=True, timeout=180,
        )
        blob = proc.stdout or ""
    except Exception as e:  # noqa: BLE001
        _log(f"context extraction failed: {e}")
        return {}
    for chunk in blob.split(sep)[1:]:
        nl = chunk.find("\n")
        if nl < 0:
            continue
        path = chunk[:nl].strip()
        body = chunk[nl + 1:]
        out[path] = body[:max_bytes]
    return out


def build_prompt(instruction: str, ctx_files: Dict[str, str],
                 target_files: List[str]) -> str:
    parts = [
        "You are an expert software engineer fixing a Python repository checked "
        "out at /app/repo. Read the task and the current source, then produce a "
        "fix.",
        "",
        "=== TASK ===",
        instruction.strip(),
        "",
        "=== FILE(S) YOU LIKELY NEED TO EDIT ===",
    ]
    if ctx_files:
        for path, body in ctx_files.items():
            parts += [f"--- BEGIN {path} ---", body.rstrip(), f"--- END {path} ---", ""]
    else:
        parts += ["(source not shown; edit these files: " + ", ".join(target_files) + ")", ""]
    parts += [
        "=== OUTPUT FORMAT (STRICT) ===",
        "Return ONLY a single unified diff that `git apply` can apply from the "
        "repository root (/app/repo). Use headers of the exact form:",
        "  diff --git a/<path> b/<path>",
        "  --- a/<path>",
        "  +++ b/<path>",
        "Do NOT modify any test files. Do NOT include explanation outside the "
        "diff. Wrap the diff in a ```diff fenced code block.",
    ]
    return "\n".join(parts)


_DIFF_FENCE = re.compile(r"```(?:diff|patch)?\s*\n(.*?)```", re.DOTALL)


def extract_diff(text: str) -> str:
    """Pull a unified diff out of a model response (fenced or bare)."""
    if not text:
        return ""
    m = _DIFF_FENCE.search(text)
    if m:
        cand = m.group(1)
    else:
        cand = text
    # Trim to the first diff/--- header so leading prose is dropped.
    lines = cand.splitlines()
    start = 0
    for i, ln in enumerate(lines):
        if ln.startswith("diff --git ") or ln.startswith("--- "):
            start = i
            break
    diff = "\n".join(lines[start:]).strip("\n")
    if diff and not diff.endswith("\n"):
        diff += "\n"
    return diff


def diff_touches_tests(diff: str) -> bool:
    for line in diff.splitlines():
        m = re.match(r"^\+\+\+ b/(.+?)\s*$", line)
        if m and ("test" in m.group(1).lower()):
            return True
    return False


# ---------------------------------------------------------------------------
# harbor oracle run (reuses harness cmd shape + reward reader)
# ---------------------------------------------------------------------------
def run_harbor_oracle(run_task_dir: str, jobs_dir: str, eks: List[str],
                      timeout_sec: int) -> str:
    cmd = ["harbor", "run", "-p", run_task_dir, "-a", "oracle", "-e", "singularity"]
    for ek in eks:
        cmd += ["--ek", ek]
    cmd += ["--timeout-multiplier", "2.0", "-o", jobs_dir]
    # Task-driven no-network switch (death point #1) via the harness injector.
    cmd = _maybe_inject_offline_eks(cmd)
    env = _clean_subprocess_env(os.environ)
    _log("harbor: " + " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout_sec, env=env)
    return (proc.stdout or "") + (proc.stderr or "")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True,
                    help="model id for the configured endpoint, or 'oracle' for the gate baseline")
    ap.add_argument("--task", required=True, help="harbor-native task dir")
    ap.add_argument("--out", required=True, help="result JSON path")
    ap.add_argument("--work", default=os.environ.get("TDB_WORK", "./.tdb_work"),
                    help="scratch/work root for run copies + results")
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--call-timeout", type=int, default=180,
                    help="per-attempt model call timeout (s); raise for big max-tokens")
    ap.add_argument("--harbor-timeout", type=int, default=1800)
    args = ap.parse_args(argv)

    t0 = time.time()
    task_dir = os.path.abspath(args.task)
    task_id = os.path.basename(task_dir.rstrip("/"))
    is_baseline = args.model.lower() == "oracle"

    result: Dict[str, Any] = {
        "model": args.model,
        "task": task_id,
        "task_dir": task_dir,
        "scaffold": "oracle_baseline" if is_baseline else "single_shot_patch",
        "reward": 0.0,
        "solved": False,
        "patch_applied": None,
        "error": None,
        "model_endpoint": None,
        "runtime_sec": None,
        "false_accept_check": {
            "gate": "harbor_protected_tests",
            "reward_source": "result.json via harbor_score.read_harbor_reward",
            "protected_tests_relaid_by_harbor": True,
            "model_is_judge": False,
            "model_patch_touched_tests": False,
            "false_accept": 0,
        },
    }

    try:
        cfg = load_task(task_dir)
        env_cfg = cfg.get("environment", {})
        sif = env_cfg.get("docker_image", "")
        allow_internet = bool(env_cfg.get("allow_internet", True))
        result["image"] = sif
        result["allow_internet"] = allow_internet

        # per-run scratch on shared FS
        run_root = os.path.join(args.work, "runs", f"{task_id}__{_slug(args.model)}__{os.getpid()}")
        run_task = os.path.join(run_root, "task")
        jobs_dir = os.path.join(run_root, "jobs")
        shutil.rmtree(run_root, ignore_errors=True)
        shutil.copytree(task_dir, run_task)
        os.makedirs(jobs_dir, exist_ok=True)

        if not is_baseline:
            # --- model call -> patch ---
            targets = solution_target_files(task_dir)
            ctx = extract_repo_files(sif, targets) if sif and os.path.exists(sif) else {}
            instruction = _read(os.path.join(task_dir, "instruction.md"))
            prompt = build_prompt(instruction, ctx, targets)
            result["model_endpoint"] = (
                os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
                + "/chat/completions")
            _log(f"calling model {args.model} ({len(prompt)} char prompt)")
            raw = call_model(args.model, prompt, max_tokens=args.max_tokens,
                             timeout=args.call_timeout)
            diff = extract_diff(raw)
            result["model_raw_len"] = len(raw)
            result["patch_len"] = len(diff)
            (Path(run_root) / "model_response.txt").write_text(raw)
            (Path(run_root) / "model_patch.diff").write_text(diff)
            if not diff.strip():
                result["error"] = "model produced no diff"
                result["patch_applied"] = False
                return _finish(result, args.out, t0)
            result["false_accept_check"]["model_patch_touched_tests"] = diff_touches_tests(diff)
            # place the model's patch where the oracle agent applies it
            (Path(run_task) / "solution" / "oracle.patch").write_text(diff)

        # --- execution gate (harbor oracle applies patch + runs protected tests) ---
        eks = list(_DEFAULT_EKS)
        trace = run_harbor_oracle(run_task, jobs_dir, eks, args.harbor_timeout)
        (Path(run_root) / "harbor.log").write_text(trace)
        reward = _read_harbor_reward(jobs_dir)
        if "oracle patch does not apply" in trace:
            result["patch_applied"] = False
        elif reward is not None:
            result["patch_applied"] = True
        result["reward"] = float(reward) if reward is not None else 0.0
        result["solved"] = bool(reward is not None and float(reward) >= 0.999)
        result["jobs_dir"] = jobs_dir
        if reward is None:
            result["error"] = "no reward parsed (patch failed to apply / tests failed / trial error)"
    except Exception as e:  # noqa: BLE001 -- BAD-safe: report, never fake a score
        result["error"] = f"{type(e).__name__}: {e}"

    return _finish(result, args.out, t0)


def _finish(result: Dict[str, Any], out: str, t0: float) -> int:
    result["runtime_sec"] = round(time.time() - t0, 1)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as fh:
        json.dump(result, fh, indent=2)
    print(json.dumps(result, indent=2))
    return 0


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s)


if __name__ == "__main__":
    raise SystemExit(main())
