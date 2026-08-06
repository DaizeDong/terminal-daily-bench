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
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
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
from .harbor_score import (
    _clean_subprocess_env,
    _maybe_inject_offline_eks,
    _read_harbor_reward,  # noqa: F401 - retained for diagnostic compatibility
    authoritative_harbor_result_snapshot,
    harbor_aggregate_status_from_snapshot,
    reward_from_harbor_result_snapshot,
)
from .adapters import create_adapter
from .adapters.base import HarborRunSpec
from .adapters.vendor import VendorConfigurationError, _safe_base_url

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

# Fixed, non-secret machine classes emitted by the localhost auth bridge.  This
# whitelist is duplicated at the evaluator boundary deliberately: importing the
# campaign runner here would couple the one-cell evaluator back to its optional
# orchestration layer.
_BRIDGE_FAILURE_CLASSES = (
    "BLOCKED_BRIDGE_STARTUP",
    "BLOCKED_BRIDGE_UNREACHABLE",
    "BLOCKED_NO_NETWORK_NAMESPACE",
    "BLOCKED_SHARED_RATE_LIMIT",
    "FAILED_BRIDGE_AUTH",
    "FAILED_BRIDGE_INTERNAL",
    "FAILED_BRIDGE_REQUEST_LIMIT",
    "FAILED_BRIDGE_REQUEST_PROTOCOL",
    "FAILED_BRIDGE_RESPONSE_LIMIT",
    "FAILED_BRIDGE_SHUTDOWN",
    "FAILED_CLIENT_DISCONNECT",
    "FAILED_UPSTREAM_CONNECT",
    "FAILED_UPSTREAM_HTTP",
    "FAILED_UPSTREAM_PROTOCOL",
    "FAILED_UPSTREAM_TIMEOUT",
)
_BRIDGE_FAILURE_CLASS_SET = frozenset(_BRIDGE_FAILURE_CLASSES)
_TRUSTED_BRIDGE_FAILURE_KEY = "_terminal_daily_trusted_bridge_failure_class"
_AGENT_BUDGET_FAILURE_CLASS = "FAILED_AGENT_BUDGET_EXHAUSTED"
_AGENT_ERROR_FAILURE_CLASS = "FAILED_AGENT_ERROR"
_EVALUATOR_FAILURE_CLASS_SET = frozenset(
    {
        "SKIPPED_UNSUPPORTED_AUTH",
        "FAILED_TIMEOUT",
        "FAILED_SIF_DRIFT",
        "FAILED_AGGREGATE_AUTHORITY",
        "FAILED_AGENT_SETUP",
        "FAILED_HARBOR",
    }
)


class _ModelEndpointError(RuntimeError):
    """Endpoint failure with optional bridge-header machine provenance."""

    def __init__(self, message: str, failure_class: Optional[str] = None) -> None:
        super().__init__(message)
        self.failure_class = (
            failure_class if failure_class in _BRIDGE_FAILURE_CLASS_SET else None
        )


class TaskSIFIntegrityError(ValueError):
    """A task SIF failed a pinned identity or byte-integrity check."""


def _log(msg: str) -> None:
    print(f"[model_eval] {msg}", file=sys.stderr, flush=True)


def _redact_openai_credential(value: str) -> str:
    key = os.environ.get("OPENAI_API_KEY", "")
    return value.replace(key, "<redacted:OPENAI_API_KEY>") if key else value


# ---------------------------------------------------------------------------
# model call -- GENERIC OpenAI-compatible endpoint (point it at ANY provider)
# ---------------------------------------------------------------------------
# Configure via env, so the public bundle is not tied to any one vendor:
#   OPENAI_BASE_URL  (default https://api.openai.com/v1)  -- any OpenAI-compatible
#                    endpoint: OpenAI, OpenRouter, vLLM, LiteLLM, a local server, ...
#   OPENAI_API_KEY   -- the bearer key for that endpoint (read from env, never stored).
def _openai_post(
    payload: Dict[str, Any],
    timeout: int = 120,
    base_url: str | None = None,
) -> Dict[str, Any]:
    """POST an OpenAI-format chat/completions payload to ``$OPENAI_BASE_URL``."""
    base = _safe_base_url(
        base_url
        or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )
    if base is None:  # The default above is non-empty; retain a fail-closed guard.
        raise RuntimeError("model endpoint base URL is empty")
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
        http_failure_class = None
    except HTTPError as e:
        # Provider error bodies are commonly valid JSON and are interpreted by
        # ``_call_model_once`` (including the max_completion_tokens fallback).
        candidate = e.headers.get("X-Terminal-Daily-Failure-Class")
        http_failure_class = (
            candidate if candidate in _BRIDGE_FAILURE_CLASS_SET else None
        )
        raw = e.read().decode("utf-8", errors="replace").strip()
    except URLError as e:
        reason = _redact_openai_credential(str(e.reason))
        raise RuntimeError(f"model endpoint request failed: {reason}") from e
    if not raw:
        raise RuntimeError("empty response from model endpoint")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        safe_raw = _redact_openai_credential(raw)
        raise RuntimeError(f"non-JSON response: {safe_raw[:300]}") from e
    if isinstance(data, dict):
        # This private hand-off is always cleared before use.  A provider body
        # cannot spoof it; only the bridge-added HTTP header can populate it.
        data.pop(_TRUSTED_BRIDGE_FAILURE_KEY, None)
        if http_failure_class is not None:
            data[_TRUSTED_BRIDGE_FAILURE_KEY] = http_failure_class
    return data


def call_model(model: str, prompt: str, max_tokens: int = 4096,
               timeout: int = 180, retries: int = 1,
               base_url: str | None = None, seed: int | None = None) -> str:
    """Call ``model`` on the configured OpenAI-compatible endpoint; return its text.

    Retries once on an empty/timeout response (cold models can 504 on first hit).
    Falls back from ``max_tokens`` to ``max_completion_tokens`` for reasoning models
    that reject the former.
    """
    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            return _call_model_once(
                model, prompt, max_tokens, timeout, base_url=base_url, seed=seed
            )
        except RuntimeError as e:
            last_err = e
            _log(f"model call attempt {attempt + 1} failed: {e}")
            time.sleep(2)
    raise last_err  # type: ignore[misc]


def _call_model_once(
    model: str,
    prompt: str,
    max_tokens: int,
    timeout: int,
    *,
    base_url: str | None = None,
    seed: int | None = None,
) -> str:
    def _chat(tok_field: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            tok_field: max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if seed is not None:
            payload["seed"] = seed
        return _openai_post(payload, timeout=timeout, base_url=base_url)
    data = _chat("max_tokens")
    if "error" in data and "max_completion_tokens" in json.dumps(data.get("error", "")):
        data = _chat("max_completion_tokens")  # reasoning models reject max_tokens
    if "error" in data:
        safe_error = _redact_openai_credential(str(data["error"]))
        failure_class = data.get(_TRUSTED_BRIDGE_FAILURE_KEY)
        prefix = (
            f"{failure_class}: "
            if failure_class in _BRIDGE_FAILURE_CLASS_SET else ""
        )
        raise _ModelEndpointError(
            f"{prefix}endpoint error: {safe_error[:300]}",
            failure_class=failure_class,
        )
    choices = data.get("choices") or []
    if not choices:
        safe_data = _redact_openai_credential(json.dumps(data))
        raise RuntimeError(f"no choices in response: {safe_data[:300]}")
    content = (choices[0].get("message", {}) or {}).get("content") or ""
    return _redact_openai_credential(content)


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


def _base_harbor_child_env(
    environ: Dict[str, str] | os._Environ[str],
    runtime_root: str,
    private_dir_name: str,
) -> Dict[str, str]:
    """Build the credential-free host baseline shared by every Harbor child."""
    inherited = {
        name: value
        for name in _VENDOR_HOST_ENV_ALLOWLIST
        if (value := environ.get(name))
    }
    child = _clean_subprocess_env(inherited)

    private_root = Path(runtime_root) / private_dir_name
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
    return child


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
    child = _base_harbor_child_env(environ, runtime_root, "vendor-runtime")

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


_SIF_STABLE_FIELDS = (
    "st_dev", "st_ino", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns",
)
_SIF_IDENTITY_FIELDS = ("st_dev", "st_ino", "st_nlink", "st_size")


def _stable_sif_facts(value: os.stat_result) -> tuple[int, ...]:
    return tuple(getattr(value, field) for field in _SIF_STABLE_FIELDS)


def _sif_identity_facts(value: os.stat_result) -> tuple[int, ...]:
    return tuple(getattr(value, field) for field in _SIF_IDENTITY_FIELDS)


def _stage_pinned_task_sif(
    path: str, expected_sha256: str, run_root: str,
) -> tuple[str, str, str, tuple[int, ...]]:
    """Copy a stable source SIF into the disposable run before Harbor opens it."""
    if not os.path.isabs(path):
        raise TaskSIFIntegrityError("--task-sif must be an absolute path")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256 or ""):
        raise TaskSIFIntegrityError(
            "--task-sif-sha256 must be exactly 64 hexadecimal characters"
        )
    supplied = Path(path)
    resolved = supplied.resolve(strict=True)
    if os.path.abspath(path) != str(resolved):
        raise TaskSIFIntegrityError("--task-sif must not traverse a symbolic link")
    if resolved.suffix.lower() != ".sif":
        raise TaskSIFIntegrityError(
            "--task-sif must resolve to a regular .sif file"
        )
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    source_fd = destination_fd = None
    staged_dir = Path(run_root) / "pinned-image"
    staged_path = staged_dir / "task.sif"
    try:
        source_lstat = resolved.lstat()
        source_fd = os.open(resolved, os.O_RDONLY | nofollow | cloexec)
        source_before = os.fstat(source_fd)
        if (not stat.S_ISREG(source_before.st_mode) or source_before.st_nlink != 1
                or (source_before.st_dev, source_before.st_ino)
                != (source_lstat.st_dev, source_lstat.st_ino)):
            raise TaskSIFIntegrityError(
                "--task-sif must be a single-link regular file"
            )
        staged_dir.mkdir(mode=0o700)
        os.chmod(staged_dir, 0o700)
        destination_fd = os.open(
            staged_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow | cloexec,
            0o400,
        )
        digest = hashlib.sha256()
        copied = 0
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            copied += len(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(destination_fd, view)
                if written <= 0:
                    raise OSError("short write while staging task SIF")
                view = view[written:]
        os.fchmod(destination_fd, 0o400)
        os.fsync(destination_fd)
        source_after = os.fstat(source_fd)
        if _stable_sif_facts(source_before) != _stable_sif_facts(source_after):
            raise TaskSIFIntegrityError(
                "source task SIF changed while it was staged"
            )
        destination_after = os.fstat(destination_fd)
        if (not stat.S_ISREG(destination_after.st_mode)
                or destination_after.st_nlink != 1
                or destination_after.st_size != copied
                or stat.S_IMODE(destination_after.st_mode) != 0o400):
            raise TaskSIFIntegrityError(
                "staged task SIF failed private-file validation"
            )
        actual = digest.hexdigest()
        if actual != expected_sha256.lower():
            raise TaskSIFIntegrityError(
                f"task SIF digest mismatch: expected {expected_sha256.lower()}, got {actual}"
            )
        # WekaFS may finalize ctime/mtime after close.  Bind the cross-process
        # identity to the inode and size; each hashing window independently
        # requires ctime/mtime stability and the full digest binds the bytes.
        facts = _sif_identity_facts(destination_after)
        return str(staged_path), str(resolved), actual, facts
    except Exception:
        if destination_fd is not None:
            os.close(destination_fd)
            destination_fd = None
        try:
            staged_path.unlink()
        except FileNotFoundError:
            pass
        raise
    finally:
        for fd in (destination_fd, source_fd):
            if fd is not None:
                os.close(fd)


def _verify_staged_task_sif(
    path: str, expected_sha256: str, expected_facts: tuple[int, ...],
) -> str:
    """Recheck the exact staged SIF after Harbor exits, before accepting reward."""
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    fd = None
    try:
        candidate = Path(path)
        path_stat = candidate.lstat()
        fd = os.open(candidate, os.O_RDONLY | nofollow | cloexec)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != 0o400
                or (before.st_dev, before.st_ino) != (path_stat.st_dev, path_stat.st_ino)
                or _sif_identity_facts(before) != expected_facts):
            raise TaskSIFIntegrityError(
                "staged task SIF identity changed before post-run verification"
            )
        digest = hashlib.sha256()
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                raise TaskSIFIntegrityError(
                    "staged task SIF was truncated during verification"
                )
            digest.update(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise TaskSIFIntegrityError(
                "staged task SIF grew during verification"
            )
        after = os.fstat(fd)
        if _stable_sif_facts(before) != _stable_sif_facts(after):
            raise TaskSIFIntegrityError(
                "staged task SIF changed during post-run verification"
            )
        actual = digest.hexdigest()
        if actual != expected_sha256:
            raise TaskSIFIntegrityError(
                "staged task SIF digest changed during Harbor execution"
            )
        return actual
    finally:
        if fd is not None:
            os.close(fd)


def _set_task_docker_image(task_toml: str, image: str) -> None:
    """Point only a disposable task copy at a verified, absolute task SIF."""
    text = Path(task_toml).read_text()
    lines = text.splitlines(keepends=True)
    start = next(
        (i for i, line in enumerate(lines) if line.strip() == "[environment]"),
        None,
    )
    if start is None:
        raise ValueError("task.toml has no [environment] table")
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")),
        len(lines),
    )
    encoded = json.dumps(image)
    replaced = False
    for index in range(start + 1, end):
        match = re.match(
            r"^(\s*docker_image\s*=\s*)(?:\"(?:[^\"\\]|\\.)*\"|'[^']*')"
            r"(\s*(?:#.*)?)(\r?\n)?$",
            lines[index],
        )
        if match:
            lines[index] = (
                match.group(1) + encoded + match.group(2) + (match.group(3) or "")
            )
            replaced = True
            break
    if not replaced:
        if end > 0 and not lines[end - 1].endswith(("\n", "\r")):
            lines[end - 1] += "\n"
        lines.insert(end, f"docker_image = {encoded}\n")
    Path(task_toml).write_text("".join(lines))
    with Path(task_toml).open("rb") as fh:
        effective = (tomllib.load(fh).get("environment", {}) or {}).get("docker_image")
    if effective != image:
        raise ValueError("failed to set the verified task SIF on the disposable copy")


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


def _credential_replacements(spec: HarborRunSpec) -> List[tuple[str, str]]:
    """Return every selected credential value, longest first, with its label."""
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
    return sorted(values, key=lambda item: (-len(item[1]), item[0]))


def _redact_credentials(value: Any, spec: HarborRunSpec) -> Any:
    """Recursively remove selected credential values before persistence.

    Trajectory JSON is agent-controlled.  Redacting only the captured Harbor
    stdout is insufficient because a credential can be copied into a telemetry
    string or even a nested mapping key.  Preserve JSON structure while replacing
    every occurrence of every selected value, including auth-file paths.
    """
    replacements = _credential_replacements(spec)

    def redact(item: Any) -> Any:
        if isinstance(item, str):
            for name, secret in replacements:
                item = item.replace(secret, f"<redacted:{name}>")
            return item
        if isinstance(item, dict):
            return {
                redact(key) if isinstance(key, str) else key: redact(child)
                for key, child in item.items()
            }
        if isinstance(item, list):
            return [redact(child) for child in item]
        if isinstance(item, tuple):
            return tuple(redact(child) for child in item)
        return item

    return redact(value)


def _redact_trace(text: str, spec: HarborRunSpec) -> str:
    """Remove every adapter-injected secret if a child unexpectedly echoes it."""
    return _redact_credentials(text, spec)


def _require_harbor() -> str:
    executable = shutil.which("harbor")
    if not executable:
        # Console scripts do not add their own virtualenv to the caller's PATH.
        # Use the same deterministic PATH cleanup as the child as a fallback,
        # then pin the resolved launcher below so validation and execution
        # cannot silently select different Harbor installations.
        cleaned = _clean_subprocess_env(os.environ)
        executable = shutil.which("harbor", path=cleaned.get("PATH"))
    if not executable:
        raise RuntimeError("harbor is not on PATH; run `tdb doctor` first")
    return os.path.abspath(executable)


def _failing_test_ids(task_dir: str) -> List[str]:
    """Read only public failure identifiers from record metadata, when present."""
    try:
        data = json.loads(Path(task_dir, "record.json").read_text())
    except (OSError, json.JSONDecodeError):
        return []
    values = data.get("fail_to_pass", []) if isinstance(data, dict) else []
    return [str(value) for value in values] if isinstance(values, list) else []


def _public_endpoint(url: str) -> Optional[str]:
    """Strip URL credentials/query data before persisting endpoint metadata."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return None
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if port is not None:
        host += f":{port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


_MAX_TRAJECTORY_BYTES = 16 * 1024 * 1024
_MAX_TRAJECTORY_FILES = 128
_MAX_CLAUDE_STREAM_BYTES = 16 * 1024 * 1024
_MAX_CLAUDE_STREAM_LINES = 200_000
_MAX_CLAUDE_RESULT_EVENTS = 10_000
_MAX_TELEMETRY_STEPS = 100_000
_MAX_TELEMETRY_COUNT = 1_000_000_000_000
_MAX_TELEMETRY_COST = 1_000_000_000.0
_TERMINAL_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def _record_bridge_failure(
    result: Dict[str, Any], failure_class: Optional[str]
) -> None:
    """Persist evaluator-owned machine metadata in the dedicated namespace."""
    if failure_class not in _BRIDGE_FAILURE_CLASS_SET:
        return
    result["bridge"] = {
        "failure_class": failure_class,
        "source": "evaluator_machine_metadata",
    }


def _bridge_failure_from_exception(exc: BaseException) -> Optional[str]:
    """Accept provenance only from the evaluator's private endpoint error type."""
    if not isinstance(exc, _ModelEndpointError):
        return None
    return exc.failure_class


def _record_evaluator_failure(
    result: Dict[str, Any], failure_class: Optional[str]
) -> None:
    """Persist a fixed evaluator-owned class without parsing exception text."""
    if (
        failure_class in _EVALUATOR_FAILURE_CLASS_SET
        and "evaluator_failure_class" not in result
    ):
        result["evaluator_failure_class"] = failure_class


def _read_pinned_trajectory(path: Path, jobs_dir: str) -> Optional[Dict[str, Any]]:
    """Read one regular, single-link trajectory through a no-follow fd chain."""
    descriptors: List[int] = []
    try:
        search_root = Path(jobs_dir)
        root = search_root.resolve(strict=True)
        relative = path.relative_to(search_root)
        if not relative.parts or relative.name != "trajectory.json":
            return None
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        cloexec = getattr(os, "O_CLOEXEC", 0)
        current_fd = os.open(
            root, os.O_RDONLY | os.O_DIRECTORY | nofollow | cloexec
        )
        descriptors.append(current_fd)
        for component in relative.parts[:-1]:
            current_fd = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | nofollow | cloexec,
                dir_fd=current_fd,
            )
            descriptors.append(current_fd)
        file_fd = os.open(
            relative.name, os.O_RDONLY | nofollow | cloexec, dir_fd=current_fd
        )
        descriptors.append(file_fd)
        before = os.fstat(file_fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size < 0 or before.st_size > _MAX_TRAJECTORY_BYTES):
            return None
        chunks: List[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(file_fd, min(1024 * 1024, remaining))
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(file_fd, 1):
            return None
        after = os.fstat(file_fd)
        stable = ("st_dev", "st_ino", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, field) != getattr(after, field) for field in stable):
            return None
        data = json.loads(b"".join(chunks).decode("utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return None
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _read_pinned_claude_stream(path: Path, jobs_dir: str) -> Optional[bytes]:
    """Read one bounded ``claude-code.txt`` below the fixed jobs root.

    Every path component is opened relative to an already-open directory with
    ``O_NOFOLLOW``. The returned bytes therefore cannot come from a symlink,
    hard link, path escape, or file swapped while it is being read.
    """
    descriptors: List[int] = []
    try:
        search_root = Path(jobs_dir).absolute()
        root_path_facts = search_root.lstat()
        if search_root.is_symlink() or not stat.S_ISDIR(root_path_facts.st_mode):
            return None
        candidate = path.absolute()
        relative = candidate.relative_to(search_root)
        if not relative.parts or relative.name != "claude-code.txt":
            return None

        nofollow = getattr(os, "O_NOFOLLOW", 0)
        cloexec = getattr(os, "O_CLOEXEC", 0)
        current_fd = os.open(
            search_root, os.O_RDONLY | os.O_DIRECTORY | nofollow | cloexec
        )
        descriptors.append(current_fd)
        root_fd_facts = os.fstat(current_fd)
        if (
            not stat.S_ISDIR(root_fd_facts.st_mode)
            or (root_fd_facts.st_dev, root_fd_facts.st_ino)
            != (root_path_facts.st_dev, root_path_facts.st_ino)
        ):
            return None

        for component in relative.parts[:-1]:
            current_fd = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | nofollow | cloexec,
                dir_fd=current_fd,
            )
            descriptors.append(current_fd)
        file_fd = os.open(
            relative.name, os.O_RDONLY | nofollow | cloexec, dir_fd=current_fd
        )
        descriptors.append(file_fd)
        before = os.fstat(file_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size < 0
            or before.st_size > _MAX_CLAUDE_STREAM_BYTES
        ):
            return None

        chunks: List[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(file_fd, min(1024 * 1024, remaining))
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(file_fd, 1):
            return None
        after = os.fstat(file_fd)
        stable = (
            "st_dev", "st_ino", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns",
        )
        if any(getattr(before, field) != getattr(after, field) for field in stable):
            return None
        current_path_facts = candidate.lstat()
        if (
            not stat.S_ISREG(current_path_facts.st_mode)
            or (current_path_facts.st_dev, current_path_facts.st_ino,
                current_path_facts.st_nlink, current_path_facts.st_size)
            != (after.st_dev, after.st_ino, after.st_nlink, after.st_size)
        ):
            return None
        return b"".join(chunks)
    except (OSError, ValueError):
        return None
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _parse_claude_terminal_stream(path: Path, jobs_dir: str) -> Dict[str, Any]:
    """Select the final valid top-level Claude result event.

    Only four bounded scalar fields cross this boundary. In particular, nested
    model text, error arrays, prompts, response bodies, and arbitrary extra
    fields are never returned or persisted.
    """
    raw = _read_pinned_claude_stream(path, jobs_dir)
    if raw is None:
        return {}
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {}
    lines = text.splitlines()
    if len(lines) > _MAX_CLAUDE_STREAM_LINES:
        return {}

    terminal: Optional[Dict[str, Any]] = None
    count = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("{"):
            if terminal is not None:
                return {}
            continue
        try:
            event = json.loads(stripped)
        except (json.JSONDecodeError, RecursionError):
            if terminal is not None:
                return {}
            continue
        if not isinstance(event, dict) or event.get("type") != "result":
            continue

        subtype = event.get("subtype")
        reason = event.get("terminal_reason")
        is_error = event.get("is_error")
        cost = event.get("total_cost_usd")
        if (
            not isinstance(subtype, str)
            or _TERMINAL_IDENTIFIER_RE.fullmatch(subtype) is None
            or not isinstance(reason, str)
            or _TERMINAL_IDENTIFIER_RE.fullmatch(reason) is None
            or type(is_error) is not bool
        ):
            if terminal is not None:
                return {}
            continue
        bounded_cost = _bounded_telemetry_cost(cost)
        if bounded_cost is None:
            if terminal is not None:
                return {}
            continue
        terminal = {
            "terminal_subtype": subtype,
            "terminal_reason": reason,
            "terminal_is_error": is_error,
            "terminal_total_cost_usd": bounded_cost,
        }
        count += 1
        if count > _MAX_CLAUDE_RESULT_EVENTS:
            return {}

    if terminal is None:
        return {}
    return {
        **terminal,
        "terminal_result_count": count,
        "terminal_result_selected_ordinal": count,
        "terminal_result_source": "claude_code_stream_final_result",
        "terminal_stream_sha256": hashlib.sha256(raw).hexdigest(),
        "cost_usd": terminal["terminal_total_cost_usd"],
        "cost_source": "claude_code_stream_final_result",
    }


def _bounded_telemetry_int(value: Any) -> Optional[int]:
    if type(value) is not int or value < 0 or value > _MAX_TELEMETRY_COUNT:
        return None
    return value


def _bounded_telemetry_text(value: Any, maximum: int) -> Optional[str]:
    if (not isinstance(value, str) or not value or len(value) > maximum
            or any(ord(character) < 0x20 for character in value)):
        return None
    return value


def _bounded_telemetry_cost(value: Any) -> Optional[float]:
    if type(value) not in (int, float):
        return None
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= _MAX_TELEMETRY_COST:
        return None
    return number


def _agent_budget_failure_class(
    spec: HarborRunSpec,
    telemetry: Dict[str, Any],
    aggregate_status: Any,
) -> Optional[str]:
    """Derive budget exhaustion only from bounded machine facts, never text."""
    if (
        aggregate_status is None
        or aggregate_status.clean
        or (
            aggregate_status.n_errored_trials <= 0
            and aggregate_status.eval_n_errors <= 0
        )
    ):
        return None
    if (
        spec.agent == "claude-code"
        and telemetry.get("terminal_subtype") == "error_max_budget_usd"
        and telemetry.get("terminal_reason") == "budget_exhausted"
        and telemetry.get("terminal_is_error") is True
        and type(telemetry.get("terminal_total_cost_usd")) in (int, float)
    ):
        return _AGENT_BUDGET_FAILURE_CLASS
    raw_limit = spec.agent_kwargs.get("max_budget_usd")
    try:
        limit = float(raw_limit) if raw_limit is not None else None
    except (TypeError, ValueError):
        return None
    cost = telemetry.get("cost_usd")
    if (
        limit is None
        or not math.isfinite(limit)
        or limit <= 0
        or type(cost) not in (int, float)
        or not math.isfinite(float(cost))
        or float(cost) < limit
    ):
        return None
    return _AGENT_BUDGET_FAILURE_CLASS


def read_harness_telemetry(jobs_dir: str) -> Dict[str, Any]:
    """Read a fixed, bounded telemetry whitelist from untrusted ATIF JSON."""
    try:
        paths = sorted(Path(jobs_dir).rglob("trajectory.json"))
        claude_stream_paths = sorted(Path(jobs_dir).rglob("claude-code.txt"))
    except OSError:
        return {}
    if len(paths) > _MAX_TRAJECTORY_FILES:
        return {}
    for path in paths:
        data = _read_pinned_trajectory(path, jobs_dir)
        if data is None:
            continue
        steps = data.get("steps")
        final = data.get("final_metrics")
        agent = data.get("agent")
        if (not isinstance(steps, list) or len(steps) > _MAX_TELEMETRY_STEPS
                or any(not isinstance(step, dict) for step in steps)
                or not isinstance(final, dict) or not isinstance(agent, dict)):
            continue

        n_llm_calls = 0
        n_tool_calls = 0
        counts_valid = True
        for step in steps:
            if "llm_call_count" in step:
                count = _bounded_telemetry_int(step.get("llm_call_count"))
                if count is None:
                    counts_valid = False
                    break
                n_llm_calls += count
            if "tool_calls" in step:
                calls = step.get("tool_calls")
                if not isinstance(calls, list) or len(calls) > _MAX_TELEMETRY_STEPS:
                    counts_valid = False
                    break
                n_tool_calls += len(calls)
            if (n_llm_calls > _MAX_TELEMETRY_COUNT
                    or n_tool_calls > _MAX_TELEMETRY_COUNT):
                counts_valid = False
                break
        if not counts_valid:
            continue

        telemetry: Dict[str, Any] = {
            "n_turns": len(steps),
            "n_llm_calls": n_llm_calls,
            "n_tool_calls": n_tool_calls,
            "trajectory_path": str(path),
        }
        version = _bounded_telemetry_text(agent.get("version"), 128)
        model = _bounded_telemetry_text(agent.get("model_name"), 256)
        turns = _bounded_telemetry_int(final.get("total_steps"))
        prompt = _bounded_telemetry_int(final.get("total_prompt_tokens"))
        completion = _bounded_telemetry_int(final.get("total_completion_tokens"))
        cached = _bounded_telemetry_int(final.get("total_cached_tokens"))
        cost = _bounded_telemetry_cost(final.get("total_cost_usd"))
        if version is not None:
            telemetry["version"] = version
        if model is not None:
            telemetry["trajectory_model"] = model
        if turns is not None:
            telemetry["n_turns"] = turns
        if prompt is not None:
            telemetry["prompt_tokens"] = prompt
        if completion is not None:
            telemetry["completion_tokens"] = completion
        if cached is not None:
            telemetry["cached_tokens"] = cached
        if cost is not None:
            telemetry["cost_usd"] = cost

        extra = final.get("extra")
        total = (
            _bounded_telemetry_int(extra.get("total_tokens"))
            if isinstance(extra, dict) else None
        )
        if total is None and prompt is not None and completion is not None:
            candidate = prompt + completion
            total = candidate if candidate <= _MAX_TELEMETRY_COUNT else None
        if total is not None:
            telemetry["total_tokens"] = total
        if (
            agent.get("name") == "claude-code"
            and len(claude_stream_paths) == 1
            and claude_stream_paths[0].parent == path.parent
        ):
            telemetry.update(
                _parse_claude_terminal_stream(claude_stream_paths[0], jobs_dir)
            )
        return telemetry
    return {}


def run_harbor_oracle(run_task_dir: str, jobs_dir: str, eks: List[str],
                      timeout_sec: int) -> tuple[int, str]:
    cmd = ["harbor", "run", "-p", run_task_dir, "-a", "oracle", "-e", "singularity"]
    for ek in eks:
        cmd += ["--ek", ek]
    cmd += ["--timeout-multiplier", "2.0", "-o", jobs_dir]
    # Task-driven no-network switch (death point #1) via the harness injector.
    cmd = _maybe_inject_offline_eks(cmd)
    env = _base_harbor_child_env(
        os.environ, str(Path(jobs_dir).parent), "oracle-runtime"
    )
    # The offline Singularity backend uses a Unix-domain socket below TMPDIR.
    # A private TMPDIR nested under the durable run path can exceed Linux's
    # sockaddr_un limit before ``.../singularity_staging_*/hbexec.sock`` is
    # appended.  Keep only this ephemeral transport root short and node-local;
    # mkdtemp makes it owner-only and the exact directory is removed below.
    node_tmp = tempfile.mkdtemp(prefix="tdb-oracle-", dir="/tmp")
    try:
        os.chmod(node_tmp, 0o700)
        env.update({name: node_tmp for name in ("TMPDIR", "TMP", "TEMP")})
        cmd[0] = _require_harbor()
        _log("harbor: " + shlex.join(cmd))
        return _run_process_group(cmd, env=env, timeout_sec=timeout_sec)
    finally:
        # ``node_tmp`` is the resolved, exact path returned by mkdtemp above.
        if os.path.lexists(node_tmp):
            shutil.rmtree(node_tmp)
        if os.path.lexists(node_tmp):
            raise RuntimeError("failed to remove private oracle temporary directory")


def _authoritative_reward_and_digest(
    jobs_dir: str,
) -> tuple[float | None, str | None]:
    """Read the authoritative aggregate once and bind the accepted bytes."""
    snapshot = authoritative_harbor_result_snapshot(jobs_dir)
    if snapshot is None:
        return None, None
    reward = reward_from_harbor_result_snapshot(snapshot)
    return reward, hashlib.sha256(snapshot.data).hexdigest()


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
    ap.add_argument("--model-protocol", default=None,
                    help="explicit negotiated API protocol (campaigns always set this)")
    ap.add_argument("--seed", type=int, default=None,
                    help="optional model sampling seed; vendor agents require a mapped kwarg")
    ap.add_argument("--agent-kwarg", action="append", default=[], metavar="KEY=VALUE",
                    help="safe non-secret Harbor agent kwarg; repeatable")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate and emit a secret-free run plan without calling a model/Harbor")
    ap.add_argument("--keep-task-network-policy", action="store_true",
                    help="do not enable network in the per-run copy for an installed vendor agent")
    ap.add_argument("--task-sif", default=None,
                    help="absolute prebuilt SIF path applied only to the disposable task copy")
    ap.add_argument("--task-sif-sha256", default=None,
                    help="required expected SHA-256 for --task-sif")
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
        "model_protocol": args.model_protocol,
        "seed": args.seed,
        "task": task_id,
        "task_dir": task_dir,
        "scaffold": "oracle_baseline" if is_baseline else harness_name,
        "outcome": None,
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
    vendor_score_candidate = False

    try:
        adapter = None if is_baseline else create_adapter(args.harness)
        if adapter is not None:
            if (args.model_protocol is not None
                    and args.model_protocol not in adapter.supported_protocols):
                supported = ", ".join(adapter.supported_protocols) or "none"
                raise ValueError(
                    f"harness {adapter.name!r} does not support protocol "
                    f"{args.model_protocol!r}; supported: {supported}"
                )
            effective_protocol = args.model_protocol or (
                adapter.supported_protocols[0]
                if len(adapter.supported_protocols) == 1 else None
            )
            result["model_protocol"] = effective_protocol
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

        staged_task_sif_facts = None
        if bool(args.task_sif) != bool(args.task_sif_sha256):
            raise TaskSIFIntegrityError(
                "--task-sif and --task-sif-sha256 must be provided together"
            )
        if args.task_sif:
            (task_sif, task_sif_source, task_sif_sha256,
             staged_task_sif_facts) = _stage_pinned_task_sif(
                args.task_sif, args.task_sif_sha256, run_root
            )
            _set_task_docker_image(os.path.join(run_task, "task.toml"), task_sif)
            result["effective_image"] = task_sif
            result["task_sif_source"] = task_sif_source
            result["task_sif_sha256"] = task_sif_sha256
        else:
            result["effective_image"] = sif

        eks = list(_DEFAULT_EKS)
        if is_baseline:
            if args.dry_run:
                result["plan"] = {"agent": "oracle", "jobs_dir": jobs_dir}
                return _finish(result, args.out, t0)
            harbor_returncode, trace = run_harbor_oracle(
                run_task, jobs_dir, eks, args.harbor_timeout
            )
            result["harbor_returncode"] = harbor_returncode
            _write_private_text(Path(run_root) / "harbor.log", trace)
            reward, aggregate_digest = (
                _authoritative_reward_and_digest(jobs_dir)
                if harbor_returncode == 0 else (None, None)
            )
            if aggregate_digest is not None:
                result["harbor_result_sha256"] = aggregate_digest
            result["patch_applied"] = reward is not None
            if harbor_returncode != 0:
                result["error"] = f"harbor exited with status {harbor_returncode}"
                _record_evaluator_failure(result, "FAILED_HARBOR")
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

            base = _safe_base_url(
                args.harness_base_url
                or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
            )
            if base is None:
                raise ValueError("model endpoint base URL is empty")
            result["model_endpoint"] = _public_endpoint(
                base.rstrip("/") + "/chat/completions"
            )
            attempt = adapter.produce_patch(
                task_dir,
                _failing_test_ids(task_dir),
                args.model,
                max_tokens=args.max_tokens,
                timeout=args.call_timeout,
                base_url=base,
                seed=args.seed,
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

            harbor_returncode, trace = run_harbor_oracle(
                run_task, jobs_dir, eks, args.harbor_timeout
            )
            trace_path = Path(run_root) / "harbor.log"
            _write_private_text(trace_path, trace)
            result["harness"]["harbor_returncode"] = harbor_returncode
            result["harness"]["trace_path"] = str(trace_path)
            reward, aggregate_digest = (
                _authoritative_reward_and_digest(jobs_dir)
                if harbor_returncode == 0 else (None, None)
            )
            if aggregate_digest is not None:
                result["harness"]["harbor_result_sha256"] = aggregate_digest
            if harbor_returncode != 0:
                result["error"] = f"harbor exited with status {harbor_returncode}"
                _record_evaluator_failure(result, "FAILED_HARBOR")
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
                protocol=result.get("model_protocol"),
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

            harbor_executable = _require_harbor()
            cmd[0] = harbor_executable
            command_text = shlex.join(cmd)
            _write_private_text(Path(run_root) / "harbor_cmd.txt", command_text + "\n")
            result["plan"]["command"] = cmd
            result["harness"]["harbor_executable"] = harbor_executable
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
            aggregate_status = None
            result["harness"]["score_accepted"] = False
            if returncode == 0:
                snapshot = authoritative_harbor_result_snapshot(jobs_dir)
                if snapshot is not None:
                    aggregate_status = harbor_aggregate_status_from_snapshot(snapshot)
                    result["harness"]["harbor_result_sha256"] = hashlib.sha256(
                        snapshot.data
                    ).hexdigest()
            reward = (
                aggregate_status.reward
                if aggregate_status is not None and aggregate_status.clean else None
            )
            if aggregate_status is not None:
                result["harness"]["aggregate_status"] = {
                    "n_total_trials": aggregate_status.n_total_trials,
                    "n_completed_trials": aggregate_status.n_completed_trials,
                    "n_errored_trials": aggregate_status.n_errored_trials,
                    "n_running_trials": aggregate_status.n_running_trials,
                    "n_pending_trials": aggregate_status.n_pending_trials,
                    "n_cancelled_trials": aggregate_status.n_cancelled_trials,
                    "n_retries": aggregate_status.n_retries,
                    "eval_n_trials": aggregate_status.eval_n_trials,
                    "eval_n_errors": aggregate_status.eval_n_errors,
                    "clean": aggregate_status.clean,
                }
                if not aggregate_status.clean:
                    result["harness"]["harbor_diagnostic_reward"] = (
                        aggregate_status.reward
                    )
                    result["error"] = "harbor aggregate reports agent/trial errors"
            telemetry = _redact_credentials(
                read_harness_telemetry(jobs_dir), spec
            )
            result["harness"].update(telemetry)
            # Harbor stdout/stderr, trajectories, and agent-authored files are
            # untrusted model channels.  Text found there must never downgrade
            # an agent failure into an excluded infrastructure failure.  Until
            # Harbor has a private, digest-bound wrapper result channel, only
            # the direct evaluator HTTP-header path may assert bridge classes.
            agent_failure_class = _agent_budget_failure_class(
                spec, telemetry, aggregate_status
            )
            if agent_failure_class is not None:
                result["agent_failure_class"] = agent_failure_class
                result["harness"]["agent_failure_class"] = agent_failure_class
                result["error"] = "agent budget exhausted before clean completion"
                result["harness"]["stop_reason"] = "budget_exhausted"
            elif (aggregate_status is not None and not aggregate_status.clean
                    and (aggregate_status.n_errored_trials > 0
                         or aggregate_status.eval_n_errors > 0)):
                result["agent_failure_class"] = _AGENT_ERROR_FAILURE_CLASS
                result["harness"]["stop_reason"] = "scored_agent_error"
            else:
                result["harness"]["stop_reason"] = (
                    "completed" if returncode == 0 and reward is not None else "error"
                )
            vendor_score_candidate = (
                returncode == 0
                and aggregate_status is not None
                and aggregate_status.clean
                and reward is not None
            )
            result["agent_completed"] = False
            if returncode != 0:
                result["error"] = f"harbor exited with status {returncode}"
                result["harness"]["harness_error"] = result["error"]
                _record_evaluator_failure(result, "FAILED_HARBOR")
            # Harbor-native agents mutate a workspace; there is no oracle patch.
            result["patch_applied"] = None
            result["false_accept_check"]["model_patch_touched_tests"] = None
            result = _redact_credentials(result, spec)
        else:
            raise RuntimeError(f"unsupported adapter integration path: {adapter!r}")

        if staged_task_sif_facts is not None:
            result["task_sif_post_sha256"] = _verify_staged_task_sif(
                task_sif, task_sif_sha256, staged_task_sif_facts
            )
        if vendor_score_candidate:
            result["harness"]["score_accepted"] = True
            result["agent_completed"] = True

        score_accepted = (
            vendor_score_candidate
            if adapter is not None and adapter.integration_path == "harbor-agent"
            else reward is not None and not result.get("error")
        )
        result["outcome"] = float(reward) if score_accepted else None
        if isinstance(result.get("harness"), dict):
            result["harness"]["score_accepted"] = score_accepted
        result["jobs_dir"] = jobs_dir
        if reward is None:
            if not result.get("error"):
                result["error"] = (
                    "no reward parsed (agent/patch failed, trial errored, or gate did not run)"
                )
            if result.get("harness"):
                if not result["harness"].get("harness_error"):
                    result["harness"]["harness_error"] = result["error"]
                if result["harness"].get("stop_reason") not in {
                    "scored_agent_error", "budget_exhausted",
                }:
                    result["harness"]["stop_reason"] = "error"
                    _record_evaluator_failure(
                        result, "FAILED_AGGREGATE_AUTHORITY"
                    )
    except HarborTimeoutError as e:
        result["error"] = str(e)
        result["agent_completed"] = False
        _record_evaluator_failure(result, "FAILED_TIMEOUT")
        if result.get("harness"):
            result["harness"]["harness_error"] = str(e)
            result["harness"]["score_accepted"] = False
    except Exception as e:  # noqa: BLE001 -- BAD-safe: report, never fake a score
        result["error"] = f"{type(e).__name__}: {e}"
        result["agent_completed"] = False
        _record_bridge_failure(
            result,
            _bridge_failure_from_exception(e),
        )
        if isinstance(e, TaskSIFIntegrityError):
            _record_evaluator_failure(result, "FAILED_SIF_DRIFT")
        elif isinstance(e, VendorConfigurationError):
            _record_evaluator_failure(result, "FAILED_AGENT_SETUP")
        if result.get("harness"):
            result["harness"]["harness_error"] = result["error"]
            result["harness"]["stop_reason"] = "error"
            result["harness"]["score_accepted"] = False

    return _finish(result, args.out, t0)


def _finish(result: Dict[str, Any], out: str, t0: float) -> int:
    """Write the result record and exit with a TRUTHFUL status.

    A scoring FAILURE (no patch, harbor never ran, an exception) must not look like
    a clean zero-reward run: it exits non-zero so a harness/CI notices. A genuine
    unsolved attempt (no error, reward 0.0) still exits 0 -- that is a real result.
    """
    # Numeric/boolean score aliases are valid only for an accepted outcome.
    # A failed, blocked, dry-run, or otherwise unaccepted row must be explicit
    # null and must not be observationally equivalent to a genuine zero.
    raw_outcome = result.get("outcome")
    if "outcome" not in result:
        raw_outcome = result.get("reward")
    harness = result.get("harness")
    harness_rejected = (
        isinstance(harness, dict) and harness.get("score_accepted") is False
    )
    outcome_accepted = (
        type(raw_outcome) in (int, float)
        and math.isfinite(float(raw_outcome))
        and 0.0 <= float(raw_outcome) <= 1.0
        and result.get("error") is None
        and not harness_rejected
    )
    if outcome_accepted:
        result["outcome"] = float(raw_outcome)
        result["reward"] = float(raw_outcome)
        result["solved"] = float(raw_outcome) >= 0.999
        result.pop("passed", None)
    else:
        result["outcome"] = None
        for alias in ("reward", "solved", "passed"):
            result.pop(alias, None)

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
