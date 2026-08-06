#!/usr/bin/env python3
"""model-eval helper: one MODEL x one TASK, scored by the execution gate.

This is the reusable core behind ``scripts/v2/model_eval.sh``. It runs ONE model
against ONE harbor-native task package and returns an execution-truth score. The
model is the SUBJECT under test; it NEVER judges. Scoring is the harbor
execution gate and nothing else. This makes acceptance without protected-test
replay impossible by construction; it does not measure semantic verifier error.

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
execution-proof gate the SOLE authority (acceptance without replay is impossible).
The legacy ``false_accept`` field records replay integrity, not a claim that the
task verifier itself has zero semantic false accepts.

This is a SINGLE-SHOT, solution-localized scaffold -- NOT a multi-turn terminus-2
agent loop (the model gets the file to fix and one shot at the diff; it does not
explore the repo itself). Select ``--harness codex`` or ``--harness claude-code``
for Harbor's real installed, multi-turn vendor agents. Those adapters declare the
agent invocation; this module still owns the subprocess and reward boundary.

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
import shlex
import shutil
import signal
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

# The harness's own authoritative primitives (reused, NOT reinvented):
#   * _read_harbor_reward  -> the reward-truth reader the admission gate uses
#   * _maybe_inject_offline_eks -> the task-driven no-network `--ek` switch
#   * _clean_subprocess_env -> the host-conda scrub the live eval path uses
from .harbor_score import _read_harbor_reward, _maybe_inject_offline_eks
from .harbor_score import _clean_subprocess_env
from .adapters import REGISTRY, create_adapter
from .adapters.base import HarborRunSpec

# Singularity `--ek` backend knobs. Paths are env-driven so nothing host-specific
# ships: set TDB_SIF_CACHE / TDB_OVERLAY_DIR to override the generic defaults.
_DEFAULT_EKS = [
    f"singularity_image_cache_dir={os.environ.get('TDB_SIF_CACHE', './.tdb_work/sif_cache')}",
    "singularity_overlay_size_mb=8192",
    f"singularity_overlay_dir={os.environ.get('TDB_OVERLAY_DIR', '/tmp/tdb_overlays')}",
    "singularity_health_timeout_sec=480",
    "singularity_mksquashfs_mem=2G",
]

# A vendor-agent run must not receive the login session wholesale.  In
# particular, cloud credentials, SSH agents, unrelated provider tokens, and
# scheduler/runtime internals are ambient on many compute nodes.  Keep this list
# deliberately small and path-oriented; adapter-selected endpoint/credential
# values are added separately from ``HarborRunSpec.process_env``.
_VENDOR_HOST_ENV_ALLOWLIST = (
    "PATH",
    "VIRTUAL_ENV",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "APPTAINER_CACHEDIR",
    "APPTAINER_TMPDIR",
    "SINGULARITY_CACHEDIR",
    "SINGULARITY_TMPDIR",
)
_SENSITIVE_ENV_NAME = re.compile(
    r"(?:key|secret|token|password|credential|auth)", re.IGNORECASE
)


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
    request = Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace").strip()
    except HTTPError as e:
        # Provider error bodies are commonly valid JSON and are interpreted by
        # ``_call_model_once`` (including the max_completion_tokens fallback).
        raw = e.read().decode("utf-8", errors="replace").strip()
    except URLError as e:
        raise RuntimeError(f"model endpoint request failed: {e.reason}") from e
    if not raw:
        raise RuntimeError("empty response from model endpoint")
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
# Harbor invocation helpers (the runner owns execution and reward interpretation)
# ---------------------------------------------------------------------------
class HarborTimeoutError(TimeoutError):
    """A Harbor process group exceeded its deadline and was reaped."""

    def __init__(self, timeout_sec: int, trace: str = "") -> None:
        super().__init__(f"harbor timeout after {timeout_sec}s")
        self.trace = trace


def _run_process_group(cmd: List[str], *, env: Dict[str, str],
                       timeout_sec: int) -> tuple[int, str]:
    """Run a command in its own session and reap descendants on timeout."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_sec)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = proc.communicate()
        partial = "".join(
            part for part in (
                exc.stdout if isinstance(exc.stdout, str) else "",
                exc.stderr if isinstance(exc.stderr, str) else "",
                stdout or "",
                stderr or "",
            ) if part
        )
        raise HarborTimeoutError(timeout_sec, partial) from exc
    return proc.returncode, (stdout or "") + (stderr or "")


def _write_private_text(path: Path, text: str) -> None:
    """Write a potentially sensitive local artifact with mode ``0600``.

    Passing ``mode`` to ``open`` only affects a newly-created file.  ``fchmod``
    also tightens an existing file before any new trace content is written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fd = -1
            fh.write(text)
    finally:
        if fd >= 0:
            os.close(fd)


def _vendor_child_env(
    environ: Dict[str, str] | os._Environ[str],
    spec: HarborRunSpec,
    runtime_root: str,
) -> Dict[str, str]:
    """Build an explicit, minimal environment for a vendor Harbor child.

    Host values enter only through ``_VENDOR_HOST_ENV_ALLOWLIST``.  A private
    HOME/tmp/XDG tree prevents tools from implicitly consulting login-session
    credential files.  The only adapter values added are those the adapter put
    in ``spec.process_env``; credential entries must use the matching
    ``${NAME}`` template in ``agent_env`` so a literal can never enter argv.
    """
    inherited = {
        name: value
        for name in _VENDOR_HOST_ENV_ALLOWLIST
        if (value := environ.get(name))
    }
    child = _clean_subprocess_env(inherited)

    private_root = Path(runtime_root) / "vendor-runtime"
    private_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(private_root, 0o700)
    private_paths = {
        "HOME": private_root / "home",
        "TMPDIR": private_root / "tmp",
        "TMP": private_root / "tmp",
        "TEMP": private_root / "tmp",
        "XDG_CACHE_HOME": private_root / "cache",
        "XDG_CONFIG_HOME": private_root / "config",
        "XDG_DATA_HOME": private_root / "data",
        "XDG_RUNTIME_DIR": private_root / "runtime",
    }
    for path in set(private_paths.values()):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path, 0o700)
    child.update({name: str(path) for name, path in private_paths.items()})

    credential_names = set(spec.credential_env_names)
    for name, value in spec.process_env.items():
        agent_value = spec.agent_env.get(name)
        if name in credential_names:
            if agent_value != "${" + name + "}":
                raise ValueError(
                    f"credential environment {name!r} lacks a matching argv template"
                )
        else:
            # Non-secret process settings (currently the validated base URL)
            # must be mirrored exactly in the declarative agent environment.
            if _SENSITIVE_ENV_NAME.search(name):
                raise ValueError(
                    f"sensitive process environment {name!r} is not marked as a credential"
                )
            if agent_value != value:
                raise ValueError(
                    f"unsupported process-only vendor environment setting: {name!r}"
                )
        child[name] = value
    return child


def _set_task_allow_internet(task_toml: str, allow: bool) -> bool:
    """Edit only a per-run task copy so an installed agent can reach its API.

    The patched singularity backend used by this bundle has no phase-specific
    network switching.  Vendor agents therefore need the run copy's legacy
    ``allow_internet`` baseline enabled for setup and inference.  Harbor still
    re-lays the trusted verifier files after the agent phase.
    """
    try:
        text = Path(task_toml).read_text()
    except OSError:
        return False
    lines = text.splitlines(keepends=True)
    start = next(
        (i for i, line in enumerate(lines) if line.strip() == "[environment]"),
        None,
    )
    if start is None:
        return False
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")),
        len(lines),
    )
    target_bool = "true" if allow else "false"
    target_mode = "public" if allow else "no-network"
    saw_policy = False
    for index in range(start + 1, end):
        line = lines[index]
        allow_match = re.match(
            r"^(\s*allow_internet\s*=\s*)(true|false)(\s*(?:#.*)?)(\r?\n)?$",
            line,
        )
        if allow_match:
            lines[index] = (
                allow_match.group(1) + target_bool + allow_match.group(3)
                + (allow_match.group(4) or "")
            )
            saw_policy = True
            continue
        mode_match = re.match(
            r'^(\s*network_mode\s*=\s*)"(?:public|no-network|allowlist)"'
            r'(\s*(?:#.*)?)(\r?\n)?$',
            line,
        )
        if mode_match:
            lines[index] = (
                mode_match.group(1) + f'"{target_mode}"' + mode_match.group(2)
                + (mode_match.group(3) or "")
            )
            saw_policy = True
    if not saw_policy:
        if end > 0 and not lines[end - 1].endswith(("\n", "\r")):
            lines[end - 1] += "\n"
        lines.insert(end, f"allow_internet = {target_bool}\n")
    updated = "".join(lines)
    if updated == text:
        return False
    Path(task_toml).write_text(updated)
    return True


def _parse_agent_kwargs(items: Optional[List[str]]) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"invalid --agent-kwarg {item!r}; expected KEY=VALUE")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("--agent-kwarg key must not be empty")
        parsed[key] = value
    return parsed


def build_harbor_agent_command(run_task_dir: str, jobs_dir: str,
                               spec: HarborRunSpec, eks: List[str]) -> List[str]:
    """Build the stable Harbor CLI boundary shared by all vendor adapters."""
    cmd = [
        "harbor", "run", "-p", run_task_dir,
        "-a", spec.agent, "-m", spec.model,
        "-e", "singularity",
    ]
    for key, value in spec.agent_kwargs.items():
        cmd += ["--agent-kwarg", f"{key}={value}"]
    for key, value in spec.agent_env.items():
        cmd += ["--ae", f"{key}={value}"]
    for ek in eks:
        cmd += ["--ek", ek]
    cmd += ["--timeout-multiplier", "2.0", "-o", jobs_dir]
    return _maybe_inject_offline_eks(cmd)


def _redact_trace(text: str, spec: HarborRunSpec) -> str:
    """Remove every adapter-injected secret if a child unexpectedly echoes it."""
    redacted = text
    secret_names = set(spec.credential_env_names)
    secret_names.update(
        name for name in spec.process_env
        if spec.agent_env.get(name) == "${" + name + "}"
    )
    values = [
        (name, spec.process_env.get(name, ""))
        for name in secret_names
        if spec.process_env.get(name, "")
    ]
    # Longest first prevents a short credential that prefixes another one from
    # partially replacing the longer value and leaving its suffix in the trace.
    for name, value in sorted(values, key=lambda item: (-len(item[1]), item[0])):
        redacted = redacted.replace(value, f"<redacted:{name}>")
    return redacted


def _require_harbor() -> str:
    executable = shutil.which("harbor")
    if not executable:
        raise RuntimeError("harbor is not on PATH; run `tdb doctor` first")
    return executable


def _failing_test_ids(task_dir: str) -> List[str]:
    """Read only public failure identifiers from record metadata, when present."""
    try:
        data = json.loads(Path(task_dir, "record.json").read_text())
    except (OSError, json.JSONDecodeError):
        return []
    values = data.get("fail_to_pass", []) if isinstance(data, dict) else []
    return [str(value) for value in values] if isinstance(values, list) else []


def _public_endpoint(url: str) -> str:
    """Strip URL credentials/query data before persisting endpoint metadata."""
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if parsed.port is not None:
        host += f":{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def read_harness_telemetry(jobs_dir: str) -> Dict[str, Any]:
    """Read additive usage metadata from Harbor's ATIF trajectory, if present."""
    try:
        paths = sorted(Path(jobs_dir).rglob("trajectory.json"))
    except OSError:
        return {}
    for path in paths:
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
            continue
        steps = data["steps"]
        final = data.get("final_metrics") or {}
        agent = data.get("agent") or {}
        if not isinstance(final, dict) or not isinstance(agent, dict):
            continue
        n_llm_calls = 0
        n_tool_calls = 0
        for step in steps:
            if not isinstance(step, dict):
                continue
            count = step.get("llm_call_count")
            if isinstance(count, int):
                n_llm_calls += count
            calls = step.get("tool_calls")
            if isinstance(calls, list):
                n_tool_calls += len(calls)
        prompt = final.get("total_prompt_tokens")
        completion = final.get("total_completion_tokens")
        extra = final.get("extra") or {}
        total = extra.get("total_tokens") if isinstance(extra, dict) else None
        if total is None and isinstance(prompt, int) and isinstance(completion, int):
            total = prompt + completion
        return {
            "version": agent.get("version"),
            "trajectory_model": agent.get("model_name"),
            "n_turns": final.get("total_steps", len(steps)),
            "n_llm_calls": n_llm_calls,
            "n_tool_calls": n_tool_calls,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "cached_tokens": final.get("total_cached_tokens"),
            "total_tokens": total,
            "cost_usd": final.get("total_cost_usd"),
            "trajectory_path": str(path),
        }
    return {}


def run_harbor_oracle(run_task_dir: str, jobs_dir: str, eks: List[str],
                      timeout_sec: int) -> str:
    cmd = ["harbor", "run", "-p", run_task_dir, "-a", "oracle", "-e", "singularity"]
    for ek in eks:
        cmd += ["--ek", ek]
    cmd += ["--timeout-multiplier", "2.0", "-o", jobs_dir]
    # Task-driven no-network switch (death point #1) via the harness injector.
    cmd = _maybe_inject_offline_eks(cmd)
    env = _clean_subprocess_env(os.environ)
    _require_harbor()
    _log("harbor: " + shlex.join(cmd))
    _, trace = _run_process_group(cmd, env=env, timeout_sec=timeout_sec)
    return trace


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True,
                    help="model id for the configured endpoint, or 'oracle' for the gate baseline")
    ap.add_argument("--task", required=True, help="harbor-native task dir")
    ap.add_argument("--out", required=True, help="result JSON path")
    ap.add_argument("--harness", default="single_shot",
                    help="harness adapter (single_shot, claude-code, codex)")
    ap.add_argument("--harness-base-url", default=None,
                    help="optional vendor API/proxy base URL (never put credentials in it)")
    ap.add_argument("--agent-kwarg", action="append", default=[], metavar="KEY=VALUE",
                    help="safe non-secret Harbor agent kwarg; repeatable")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate and emit a secret-free run plan without calling a model/Harbor")
    ap.add_argument("--keep-task-network-policy", action="store_true",
                    help="do not enable network in the per-run copy for an installed vendor agent")
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
    harness_name = "oracle" if is_baseline else args.harness

    result: Dict[str, Any] = {
        "model": args.model,
        "task": task_id,
        "task_dir": task_dir,
        "scaffold": "oracle_baseline" if is_baseline else harness_name,
        "reward": None if args.dry_run else 0.0,
        "solved": None if args.dry_run else False,
        "patch_applied": None,
        "error": None,
        "model_endpoint": None,
        "runtime_sec": None,
        "dry_run": bool(args.dry_run),
        "false_accept_check": None if args.dry_run else {
            "gate": "harbor_protected_tests",
            "reward_source": "result.json via harbor_score.read_harbor_reward",
            "protected_tests_relaid_by_harbor": True,
            "model_is_judge": False,
            "model_patch_touched_tests": False,
            "scope": "protected_test_replay_integrity",
            "claim_acceptance_without_replay": False,
            "semantic_false_accept": None,
            "false_accept": 0,
        },
    }

    try:
        adapter = None if is_baseline else create_adapter(args.harness)
        if adapter is not None:
            result["scaffold"] = (
                "single_shot_patch" if adapter.name == "single_shot" else adapter.name
            )
            result["harness"] = {
                **adapter.metadata(),
                "wall_sec": None,
                "timed_out": False,
                "stop_reason": None,
                "trace_path": None,
                "harness_error": None,
            }

        cfg = load_task(task_dir)
        env_cfg = cfg.get("environment", {})
        sif = env_cfg.get("docker_image", "")
        network_mode = env_cfg.get("network_mode")
        allow_internet = (
            network_mode == "public"
            if network_mode is not None else bool(env_cfg.get("allow_internet", True))
        )
        result["image"] = sif
        result["source_allow_internet"] = allow_internet
        result["source_network_mode"] = network_mode

        # per-run scratch on shared FS
        run_root = os.path.join(
            args.work,
            "runs",
            f"{task_id}__{_slug(harness_name)}__{_slug(args.model)}__{os.getpid()}",
        )
        run_task = os.path.join(run_root, "task")
        jobs_dir = os.path.join(run_root, "jobs")
        shutil.rmtree(run_root, ignore_errors=True)
        shutil.copytree(task_dir, run_task)
        os.makedirs(jobs_dir, exist_ok=True)

        eks = list(_DEFAULT_EKS)
        if is_baseline:
            if args.dry_run:
                result["plan"] = {"agent": "oracle", "jobs_dir": jobs_dir}
                return _finish(result, args.out, t0)
            trace = run_harbor_oracle(run_task, jobs_dir, eks, args.harbor_timeout)
            _write_private_text(Path(run_root) / "harbor.log", trace)
            reward = _read_harbor_reward(jobs_dir)
            result["patch_applied"] = reward is not None
            if "oracle patch does not apply" in trace:
                result["patch_applied"] = False

        elif adapter is not None and adapter.integration_path == "external-diff":
            if args.dry_run:
                result["plan"] = {
                    "integration_path": adapter.integration_path,
                    "model_call": "skipped",
                    "gate": "harbor oracle after adapter diff",
                }
                return _finish(result, args.out, t0)

            base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
            result["model_endpoint"] = _public_endpoint(
                base.rstrip("/") + "/chat/completions"
            )
            attempt = adapter.produce_patch(
                task_dir,
                _failing_test_ids(task_dir),
                args.model,
                max_tokens=args.max_tokens,
                timeout=args.call_timeout,
            )
            result["harness"].update(attempt.telemetry)
            if attempt.error:
                result["error"] = attempt.error
                result["patch_applied"] = False
                result["harness"]["harness_error"] = attempt.error
                result["harness"]["stop_reason"] = "error"
                return _finish(result, args.out, t0)
            diff = attempt.patch
            result["patch_len"] = len(diff)
            result["harness"]["patch_len"] = len(diff)
            (Path(run_root) / "model_patch.diff").write_text(diff)
            if not diff.strip():
                result["error"] = "model produced no diff"
                result["patch_applied"] = False
                result["harness"]["stop_reason"] = "no_diff"
                return _finish(result, args.out, t0)
            touched_tests = diff_touches_tests(diff)
            result["false_accept_check"]["model_patch_touched_tests"] = touched_tests
            result["harness"]["patch_touched_tests"] = touched_tests
            (Path(run_task) / "solution" / "oracle.patch").write_text(diff)

            trace = run_harbor_oracle(run_task, jobs_dir, eks, args.harbor_timeout)
            trace_path = Path(run_root) / "harbor.log"
            _write_private_text(trace_path, trace)
            result["harness"]["trace_path"] = str(trace_path)
            reward = _read_harbor_reward(jobs_dir)
            if "oracle patch does not apply" in trace:
                result["patch_applied"] = False
            elif reward is not None:
                result["patch_applied"] = True

        elif adapter is not None and adapter.integration_path == "harbor-agent":
            agent_kwargs = _parse_agent_kwargs(args.agent_kwarg)
            spec = adapter.harbor_run_spec(
                args.model,
                base_url=args.harness_base_url,
                environ=os.environ,
                agent_kwargs=agent_kwargs,
                require_credentials=not args.dry_run,
            )
            result["harness"]["run_spec"] = spec.public_summary()
            result["model_endpoint"] = (
                _public_endpoint(args.harness_base_url)
                if args.harness_base_url else
                _public_endpoint(os.environ[adapter.spec.base_url_env])
                if os.environ.get(adapter.spec.base_url_env) else None
            )

            network_changed = False
            if spec.requires_public_network and not args.keep_task_network_policy:
                network_changed = _set_task_allow_internet(
                    os.path.join(run_task, "task.toml"), True
                )
                if not allow_internet and not network_changed:
                    raise RuntimeError(
                        "could not enable network in the disposable vendor-agent task copy"
                    )
            result["effective_allow_internet"] = (
                allow_internet if args.keep_task_network_policy
                else bool(allow_internet or network_changed)
            )
            result["network_policy_changed_on_run_copy"] = network_changed

            cmd = build_harbor_agent_command(run_task, jobs_dir, spec, eks)
            command_text = shlex.join(cmd)
            _write_private_text(Path(run_root) / "harbor_cmd.txt", command_text + "\n")
            result["plan"] = {
                "command": cmd,
                "jobs_dir": jobs_dir,
                "run_task": run_task,
            }
            if args.dry_run:
                result["harness"]["stop_reason"] = "dry_run"
                return _finish(result, args.out, t0)

            _require_harbor()
            child_env = _vendor_child_env(os.environ, spec, run_root)
            _log("harbor: " + command_text)
            harness_started = time.time()
            try:
                returncode, raw_trace = _run_process_group(
                    cmd, env=child_env, timeout_sec=args.harbor_timeout
                )
            except HarborTimeoutError as exc:
                trace = _redact_trace(exc.trace, spec)
                trace_path = Path(run_root) / "harbor.log"
                _write_private_text(trace_path, trace)
                result["harness"].update({
                    "timed_out": True,
                    "stop_reason": "timeout",
                    "trace_path": str(trace_path),
                    "wall_sec": round(time.time() - harness_started, 3),
                })
                raise
            trace = _redact_trace(raw_trace, spec)
            trace_path = Path(run_root) / "harbor.log"
            _write_private_text(trace_path, trace)
            result["harness"].update({
                "harbor_returncode": returncode,
                "trace_path": str(trace_path),
                "wall_sec": round(time.time() - harness_started, 3),
            })
            reward = _read_harbor_reward(jobs_dir)
            result["harness"].update(read_harness_telemetry(jobs_dir))
            result["harness"]["stop_reason"] = (
                "completed" if reward is not None else "error"
            )
            result["agent_completed"] = reward is not None
            # Harbor-native agents mutate a workspace; there is no oracle patch.
            result["patch_applied"] = None
            result["false_accept_check"]["model_patch_touched_tests"] = None
        else:
            raise RuntimeError(f"unsupported adapter integration path: {adapter!r}")

        result["reward"] = float(reward) if reward is not None else 0.0
        result["solved"] = bool(reward is not None and float(reward) >= 0.999)
        result["jobs_dir"] = jobs_dir
        if reward is None:
            result["error"] = "no reward parsed (agent/patch failed, trial errored, or gate did not run)"
            if result.get("harness"):
                result["harness"]["harness_error"] = result["error"]
                result["harness"]["stop_reason"] = "error"
    except HarborTimeoutError as e:
        result["error"] = str(e)
        if result.get("harness"):
            result["harness"]["harness_error"] = str(e)
    except Exception as e:  # noqa: BLE001 -- BAD-safe: report, never fake a score
        result["error"] = f"{type(e).__name__}: {e}"
        if result.get("harness"):
            result["harness"]["harness_error"] = result["error"]
            result["harness"]["stop_reason"] = "error"

    return _finish(result, args.out, t0)


def _finish(result: Dict[str, Any], out: str, t0: float) -> int:
    """Write the result record and exit with a TRUTHFUL status.

    A scoring FAILURE (no patch, harbor never ran, an exception) must not look like
    a clean zero-reward run: it exits non-zero so a harness/CI notices. A genuine
    unsolved attempt (no error, reward 0.0) still exits 0 -- that is a real result.
    """
    result["runtime_sec"] = round(time.time() - t0, 1)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as fh:
        json.dump(result, fh, indent=2)
    print(json.dumps(result, indent=2))
    return 1 if result.get("error") else 0


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
