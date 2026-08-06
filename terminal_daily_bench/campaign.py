"""Protocol-aware sparse campaigns built on the single-cell execution gate.

This module plans model-profile x agent-profile x task cells, but only executes
protocol-compatible combinations.  It deliberately does *not* batch trials in
Harbor: every cell invokes :mod:`terminal_daily_bench.eval` once and therefore
retains that module's one-trial aggregate, score-authority, and post-run SIF
checks.

Campaign files and checkpoints never contain credential values.  Authentication
remains an environment concern of the existing adapter boundary.
"""
from __future__ import annotations

import concurrent.futures
import contextlib
import dataclasses
import datetime as _datetime
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Mapping

from .adapters import create_adapter
from .adapters.vendor import _safe_agent_kwargs, _safe_base_url
from . import __version__


SPEC_SCHEMA = "tdb-campaign/v1"
MANIFEST_SCHEMA = "tdb-campaign-manifest/v1"
CHECKPOINT_SCHEMA = "tdb-campaign-checkpoint/v1"
FROZEN_CATALOG_SCHEMA = "terminal-daily-gateway-model-catalog-v1"

SUCCESS = "SUCCESS"
FAILED = "FAILED"
NOT_RUN = "NOT_RUN"
BLOCKED = "BLOCKED"
STATUSES = {SUCCESS, FAILED, NOT_RUN, BLOCKED}

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_PROTOCOL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_SPEC_BYTES = 4 * 1024 * 1024
_MAX_STATE_BYTES = 32 * 1024 * 1024
_MAX_TASK_FILES = 100_000


class CampaignError(RuntimeError):
    """A campaign definition, plan, or persisted state is invalid."""


class CampaignBusyError(CampaignError):
    """Another process owns the campaign state directory."""


def _utc_now() -> str:
    return _datetime.datetime.now(_datetime.timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CampaignError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _read_stable_regular_bytes(path: Path, *, maximum: int) -> bytes:
    try:
        path_facts = path.lstat()
    except OSError as exc:
        raise CampaignError(f"cannot read {path}: {exc}") from exc
    if (path.is_symlink() or not stat.S_ISREG(path_facts.st_mode)
            or path_facts.st_nlink != 1):
        raise CampaignError(f"JSON input must be a regular non-symlink file: {path}")
    if path_facts.st_size < 0 or path_facts.st_size > maximum:
        raise CampaignError(f"JSON input exceeds {maximum} bytes: {path}")
    fd = None
    try:
        fd = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or (before.st_dev, before.st_ino)
                != (path_facts.st_dev, path_facts.st_ino)
                or before.st_size != path_facts.st_size):
            raise CampaignError(f"JSON input changed while opening: {path}")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                raise CampaignError(f"JSON input was truncated while reading: {path}")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise CampaignError(f"JSON input grew while reading: {path}")
        after = os.fstat(fd)
        stable = ("st_dev", "st_ino", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, field) != getattr(after, field) for field in stable):
            raise CampaignError(f"JSON input changed while reading: {path}")
        current = path.lstat()
        if ((current.st_dev, current.st_ino, current.st_nlink, current.st_size)
                != (after.st_dev, after.st_ino, after.st_nlink, after.st_size)):
            raise CampaignError(f"JSON input path changed while reading: {path}")
        return b"".join(chunks)
    except OSError as exc:
        raise CampaignError(f"cannot read {path}: {exc}") from exc
    finally:
        if fd is not None:
            os.close(fd)


def _decode_json(data: bytes, path: Path) -> Any:
    try:
        return json.loads(
            data.decode("utf-8"), object_pairs_hook=_strict_object
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CampaignError(f"invalid JSON in {path}: {exc}") from exc


def _load_json(path: Path, *, maximum: int) -> Any:
    return _decode_json(_read_stable_regular_bytes(path, maximum=maximum), path)


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CampaignError(f"{label} must be a JSON object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise CampaignError(f"{label} must be a JSON array")
    return value


def _only_keys(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise CampaignError(f"{label} has unknown field(s): {', '.join(unknown)}")


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise CampaignError(f"{label} must match {_ID_RE.pattern}")
    return value


def _positive_int(value: Any, label: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise CampaignError(f"{label} must be an integer in [1, {maximum}]")
    return value


def _nonnegative_money(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CampaignError(f"{label} must be a non-negative finite number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise CampaignError(f"{label} must be a non-negative finite number")
    return number


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value.lower()):
        raise CampaignError(f"{label} must be a 64-character SHA-256 hex digest")
    return value.lower()


def _protocols(value: Any, label: str) -> tuple[str, ...]:
    raw = _list(value, label)
    result: list[str] = []
    for index, protocol in enumerate(raw):
        if not isinstance(protocol, str) or not _PROTOCOL_RE.fullmatch(protocol):
            raise CampaignError(f"{label}[{index}] is not a valid protocol name")
        if protocol in result:
            raise CampaignError(f"{label} contains duplicate protocol {protocol!r}")
        result.append(protocol)
    if not result:
        raise CampaignError(f"{label} must not be empty")
    return tuple(result)


def _base_url_mapping(value: Any, label: str) -> dict[str, str]:
    raw = _mapping(value, label)
    result: dict[str, str] = {}
    for protocol, url in raw.items():
        if not isinstance(protocol, str) or not _PROTOCOL_RE.fullmatch(protocol):
            raise CampaignError(f"{label} has invalid protocol key {protocol!r}")
        try:
            normalized = _safe_base_url(url)
        except (TypeError, ValueError) as exc:
            raise CampaignError(f"{label}[{protocol!r}]: {exc}") from exc
        if normalized is None:
            raise CampaignError(f"{label}[{protocol!r}] must not be empty")
        result[protocol] = normalized
    return result


@dataclasses.dataclass(frozen=True)
class ModelProfile:
    profile_id: str
    provider: str
    model: str
    build: str | None
    protocols: tuple[str, ...]
    base_url: str | None
    base_url_by_protocol: Mapping[str, str]
    model_by_harness: Mapping[str, str]
    estimated_cost_usd: float | None

    def resolved_model(self, agent_id: str, harness: str) -> str:
        return self.model_by_harness.get(
            agent_id, self.model_by_harness.get(harness, self.model)
        )

    def resolved_base_url(self, protocol: str) -> str | None:
        return self.base_url_by_protocol.get(protocol, self.base_url)

    def public_summary(self) -> dict[str, Any]:
        return {
            "id": self.profile_id,
            "provider": self.provider,
            "model": self.model,
            "build": self.build,
            "protocols": list(self.protocols),
            "base_url_sha256": (
                hashlib.sha256(self.base_url.encode("utf-8")).hexdigest()
                if self.base_url is not None else None
            ),
            "base_url_by_protocol_sha256": {
                protocol: hashlib.sha256(url.encode("utf-8")).hexdigest()
                for protocol, url in sorted(self.base_url_by_protocol.items())
            },
            "model_by_harness": dict(sorted(self.model_by_harness.items())),
            "estimated_cost_usd": self.estimated_cost_usd,
        }


@dataclasses.dataclass(frozen=True)
class AgentProfile:
    profile_id: str
    harness: str
    protocols: tuple[str, ...]
    agent_kwargs: Mapping[str, str]
    keep_task_network_policy: bool
    seed_kwarg: str | None
    integration_path: str
    harbor_agent: str | None
    base_url_kind: str
    credential_env_names: tuple[str, ...]

    def public_summary(self) -> dict[str, Any]:
        return {
            "id": self.profile_id,
            "harness": self.harness,
            "protocols": list(self.protocols),
            "agent_kwargs": dict(sorted(self.agent_kwargs.items())),
            "keep_task_network_policy": self.keep_task_network_policy,
            "seed_kwarg": self.seed_kwarg,
            "integration_path": self.integration_path,
            "harbor_agent": self.harbor_agent,
            "base_url_kind": self.base_url_kind,
            "credential_env_names": list(self.credential_env_names),
        }


@dataclasses.dataclass(frozen=True)
class TaskProfile:
    profile_id: str
    path: Path
    task_tree_sha256: str
    task_sif: Path | None
    task_sif_sha256: str | None

    def public_summary(self) -> dict[str, Any]:
        return {
            "id": self.profile_id,
            "task_tree_sha256": self.task_tree_sha256,
            "task_sif_sha256": self.task_sif_sha256,
        }


@dataclasses.dataclass(frozen=True)
class ExecutionLimits:
    max_workers: int = 1
    max_cells: int | None = None
    budget_usd: float | None = None
    provider_concurrency: Mapping[str, int] = dataclasses.field(default_factory=dict)
    call_timeout: int = 180
    harbor_timeout: int = 1800
    max_tokens: int = 4096

    def public_summary(self) -> dict[str, Any]:
        return {
            "max_workers": self.max_workers,
            "max_cells": self.max_cells,
            "budget_usd": self.budget_usd,
            "provider_concurrency": dict(sorted(self.provider_concurrency.items())),
            "call_timeout": self.call_timeout,
            "harbor_timeout": self.harbor_timeout,
            "max_tokens": self.max_tokens,
        }


@dataclasses.dataclass(frozen=True)
class CampaignDefinition:
    campaign_id: str
    models: tuple[ModelProfile, ...]
    agents: tuple[AgentProfile, ...]
    tasks: tuple[TaskProfile, ...]
    seeds: tuple[int | None, ...]
    limits: ExecutionLimits
    catalog_sources: tuple[Mapping[str, Any], ...] = ()


@dataclasses.dataclass(frozen=True)
class RuntimeCell:
    cell_id: str
    model: ModelProfile
    agent: AgentProfile
    task: TaskProfile
    resolved_model: str
    protocol: str
    seed: int | None
    manifest_record: Mapping[str, Any]


@dataclasses.dataclass(frozen=True)
class CampaignPlan:
    definition: CampaignDefinition
    manifest: Mapping[str, Any]
    runtime_cells: Mapping[str, RuntimeCell]


def _parse_model(raw: Any, index: int) -> ModelProfile:
    value = _mapping(raw, f"models[{index}]")
    _only_keys(
        value,
        {
            "id", "provider", "model", "build", "protocols", "base_url",
            "base_url_by_protocol", "model_by_harness", "estimated_cost_usd",
        },
        f"models[{index}]",
    )
    profile_id = _identifier(value.get("id"), f"models[{index}].id")
    provider = _identifier(value.get("provider", profile_id), f"models[{index}].provider")
    model = value.get("model")
    if not isinstance(model, str) or not model.strip() or len(model) > 512:
        raise CampaignError(f"models[{index}].model must be a non-empty string")
    build = value.get("build")
    if build is not None and (not isinstance(build, str) or not build or len(build) > 256):
        raise CampaignError(f"models[{index}].build must be null or a short string")
    protocols = _protocols(value.get("protocols"), f"models[{index}].protocols")
    try:
        base_url = _safe_base_url(value.get("base_url"))
    except ValueError as exc:
        raise CampaignError(f"models[{index}].base_url: {exc}") from exc
    base_urls = _base_url_mapping(
        value.get("base_url_by_protocol", {}),
        f"models[{index}].base_url_by_protocol",
    )
    unsupported_base_urls = sorted(set(base_urls) - set(protocols))
    if unsupported_base_urls:
        raise CampaignError(
            f"models[{index}].base_url_by_protocol names undeclared protocol(s): "
            + ", ".join(unsupported_base_urls)
        )
    mappings = _mapping(value.get("model_by_harness", {}), f"models[{index}].model_by_harness")
    model_by_harness: dict[str, str] = {}
    for key, mapped in mappings.items():
        _identifier(key, f"models[{index}].model_by_harness key")
        if not isinstance(mapped, str) or not mapped.strip() or len(mapped) > 512:
            raise CampaignError(
                f"models[{index}].model_by_harness[{key!r}] must be non-empty"
            )
        model_by_harness[key] = mapped.strip()
    cost_raw = value.get("estimated_cost_usd")
    cost = (
        None if cost_raw is None
        else _nonnegative_money(cost_raw, f"models[{index}].estimated_cost_usd")
    )
    return ModelProfile(
        profile_id=profile_id,
        provider=provider,
        model=model.strip(),
        build=build,
        protocols=protocols,
        base_url=base_url,
        base_url_by_protocol=base_urls,
        model_by_harness=model_by_harness,
        estimated_cost_usd=cost,
    )


def _string_set(value: Any, label: str) -> set[str]:
    result: set[str] = set()
    for index, item in enumerate(_list(value, label)):
        if not isinstance(item, str) or not item or len(item) > 512:
            raise CampaignError(f"{label}[{index}] must be a non-empty model id")
        if item in result:
            raise CampaignError(f"{label} contains duplicate model id {item!r}")
        result.add(item)
    return result


def _catalog_profile_id(model_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", model_id).strip("-._") or "model"
    if not slug[0].isalnum():
        slug = "model-" + slug
    suffix = hashlib.sha256(model_id.encode("utf-8")).hexdigest()[:10]
    return f"{slug[:110]}-{suffix}"


def _parse_catalog(
    raw: Any, base_dir: Path
) -> tuple[list[ModelProfile], Mapping[str, Any]]:
    value = _mapping(raw, "model_catalog")
    _only_keys(
        value,
        {
            "path", "sha256", "provider", "base_url", "include", "exclude",
            "base_url_by_protocol", "anthropic_messages_allowlist",
            "estimated_cost_usd", "profile_overrides",
        },
        "model_catalog",
    )
    raw_path = value.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raise CampaignError("model_catalog.path must be non-empty")
    path = Path(raw_path)
    if not path.is_absolute():
        path = base_dir / path
    path = path.absolute()
    expected_digest = _sha256(value.get("sha256"), "model_catalog.sha256")
    try:
        catalog_bytes = _read_stable_regular_bytes(path, maximum=_MAX_SPEC_BYTES)
        file_digest = hashlib.sha256(catalog_bytes).hexdigest()
    except (OSError, CampaignError) as exc:
        raise CampaignError(f"cannot verify model catalog {path}: {exc}") from exc
    catalog = _mapping(_decode_json(catalog_bytes, path), "model catalog")
    has_data = isinstance(catalog.get("data"), list)
    has_models = isinstance(catalog.get("models"), list)
    if has_data == has_models:
        raise CampaignError(
            "model catalog must contain exactly one model array: data or models"
        )
    entries = catalog["data"] if has_data else catalog["models"]
    source_shape = "gateway-v1-models" if has_data else "frozen-model-catalog"
    models_digest = _sha256_json(entries)
    if expected_digest not in {file_digest, models_digest}:
        raise CampaignError(
            "model catalog SHA-256 matches neither the file nor canonical model array"
        )
    declared_models_digest = catalog.get("models_sha256")
    if declared_models_digest is not None:
        if (_sha256(declared_models_digest, "model catalog models_sha256")
                != models_digest):
            raise CampaignError("model catalog's declared models_sha256 is invalid")
    if has_models:
        if catalog.get("schema") != FROZEN_CATALOG_SCHEMA:
            raise CampaignError(
                f"frozen model catalog schema must be {FROZEN_CATALOG_SCHEMA!r}"
            )
        if catalog.get("http_status") != 200:
            raise CampaignError("frozen model catalog must bind a successful HTTP 200 fetch")
        for flag in ("credential_values_persisted", "routing_persisted"):
            if catalog.get(flag) is not False:
                raise CampaignError(f"frozen model catalog must declare {flag}=false")
        if declared_models_digest is None:
            raise CampaignError("frozen model catalog must declare models_sha256")
        if catalog.get("model_count") != len(entries):
            raise CampaignError("frozen model catalog model_count is inconsistent")
        chat_count = sum(
            isinstance(entry, dict)
            and isinstance(entry.get("capabilities"), dict)
            and entry["capabilities"].get("chat") is True
            for entry in entries
        )
        responses_count = sum(
            isinstance(entry, dict)
            and isinstance(entry.get("capabilities"), dict)
            and entry["capabilities"].get("responses") is True
            for entry in entries
        )
        if catalog.get("chat_count") != chat_count:
            raise CampaignError("frozen model catalog chat_count is inconsistent")
        if catalog.get("responses_count") != responses_count:
            raise CampaignError("frozen model catalog responses_count is inconsistent")
    provider = _identifier(value.get("provider", "gateway"), "model_catalog.provider")
    try:
        base_url = _safe_base_url(value.get("base_url"))
    except ValueError as exc:
        raise CampaignError(f"model_catalog.base_url: {exc}") from exc
    catalog_base_urls = _base_url_mapping(
        value.get("base_url_by_protocol", {}),
        "model_catalog.base_url_by_protocol",
    )
    include = (
        None if "include" not in value
        else _string_set(value["include"], "model_catalog.include")
    )
    exclude = _string_set(value.get("exclude", []), "model_catalog.exclude")
    anthropic = _string_set(
        value.get("anthropic_messages_allowlist", []),
        "model_catalog.anthropic_messages_allowlist",
    )
    if include is not None and include & exclude:
        raise CampaignError("model_catalog include and exclude overlap")
    default_cost_raw = value.get("estimated_cost_usd")
    default_cost = (
        None if default_cost_raw is None
        else _nonnegative_money(default_cost_raw, "model_catalog.estimated_cost_usd")
    )
    overrides = _mapping(value.get("profile_overrides", {}), "model_catalog.profile_overrides")
    seen: set[str] = set()
    models: list[ModelProfile] = []
    capability_counts = {"chat": 0, "responses": 0, "anthropic_messages": 0}
    for index, raw_entry in enumerate(entries):
        entry = _mapping(raw_entry, f"model catalog entry[{index}]")
        model_id = entry.get("id")
        if (not isinstance(model_id, str) or not model_id.strip()
                or len(model_id) > 512
                or any(ord(character) < 0x20 for character in model_id)):
            raise CampaignError(f"model catalog entry[{index}].id is invalid")
        model_id = model_id.strip()
        if model_id in seen:
            raise CampaignError(f"model catalog contains duplicate id {model_id!r}")
        seen.add(model_id)
        if (include is not None and model_id not in include) or model_id in exclude:
            continue
        caps_raw = entry.get("capabilities", {})
        capabilities = caps_raw if isinstance(caps_raw, dict) else {}
        discovered: list[str] = []
        if (capabilities.get("chat") is True
                or capabilities.get("chat_completions") is True):
            discovered.append("openai-chat-completions")
            capability_counts["chat"] += 1
        if capabilities.get("responses") is True:
            discovered.append("openai-responses")
            capability_counts["responses"] += 1
        # Anthropic support is never inferred from a model name.  The operator's
        # explicit allowlist is the authority; an optional catalog marker is not
        # sufficient by itself.
        if model_id in anthropic:
            discovered.append("anthropic-messages")
            capability_counts["anthropic_messages"] += 1

        override = _mapping(overrides.get(model_id, {}), f"model_catalog.profile_overrides[{model_id!r}]")
        _only_keys(
            override,
            {
                "id", "build", "protocols", "base_url_by_protocol",
                "model_by_harness", "estimated_cost_usd",
            },
            f"model_catalog.profile_overrides[{model_id!r}]",
        )
        protocols = tuple(discovered)
        if "protocols" in override:
            requested = _protocols(
                override["protocols"],
                f"model_catalog.profile_overrides[{model_id!r}].protocols",
            )
            forbidden = [
                protocol for protocol in requested
                if protocol not in discovered
            ]
            if forbidden:
                raise CampaignError(
                    f"model catalog override for {model_id!r} broadens unproven protocol(s): "
                    + ", ".join(forbidden)
                )
            protocols = requested
        base_urls = dict(catalog_base_urls)
        base_urls.update(_base_url_mapping(
            override.get("base_url_by_protocol", {}),
            f"model catalog override base_url_by_protocol for {model_id!r}",
        ))
        base_urls = {
            protocol: url for protocol, url in base_urls.items()
            if protocol in protocols
        }
        profile_id = _identifier(
            override.get("id", _catalog_profile_id(model_id)),
            f"model catalog profile id for {model_id!r}",
        )
        build = override.get("build")
        if build is None:
            raw_build = entry.get("build", entry.get("version"))
            build = raw_build if isinstance(raw_build, str) and raw_build else f"catalog:{models_digest[:16]}"
        if not isinstance(build, str) or not build or len(build) > 256:
            raise CampaignError(f"model catalog build for {model_id!r} is invalid")
        mapping_raw = _mapping(
            override.get("model_by_harness", {}),
            f"model catalog override model_by_harness for {model_id!r}",
        )
        mappings: dict[str, str] = {}
        for key, mapped in mapping_raw.items():
            _identifier(key, f"model catalog model_by_harness key for {model_id!r}")
            if not isinstance(mapped, str) or not mapped.strip() or len(mapped) > 512:
                raise CampaignError(f"invalid model mapping for {model_id!r}")
            mappings[key] = mapped.strip()
        cost_raw = override.get("estimated_cost_usd", default_cost)
        cost = (
            None if cost_raw is None
            else _nonnegative_money(cost_raw, f"model catalog cost for {model_id!r}")
        )
        models.append(ModelProfile(
            profile_id=profile_id,
            provider=provider,
            model=model_id,
            build=build,
            protocols=protocols,
            base_url=base_url,
            base_url_by_protocol=base_urls,
            model_by_harness=mappings,
            estimated_cost_usd=cost,
        ))

    missing_include = sorted((include or set()) - seen)
    missing_anthropic = sorted(anthropic - seen)
    missing_overrides = sorted(set(overrides) - seen)
    if missing_include:
        raise CampaignError(
            "model_catalog.include references missing id(s): " + ", ".join(missing_include)
        )
    if missing_anthropic:
        raise CampaignError(
            "anthropic_messages_allowlist references missing id(s): "
            + ", ".join(missing_anthropic)
        )
    if missing_overrides:
        raise CampaignError(
            "model_catalog.profile_overrides references missing id(s): "
            + ", ".join(missing_overrides)
        )
    source = {
        "file_sha256": file_digest,
        "models_sha256": models_digest,
        "pinned_digest_kind": (
            "file" if expected_digest == file_digest else "canonical-models"
        ),
        "shape": source_shape,
        "provider": provider,
        "source_model_count": len(entries),
        "selected_model_count": len(models),
        "capability_counts": capability_counts,
        "anthropic_messages_allowlist_sha256": _sha256_json(sorted(anthropic)),
    }
    return models, source


def _parse_agent(raw: Any, index: int) -> AgentProfile:
    value = _mapping(raw, f"agents[{index}]")
    _only_keys(
        value,
        {"id", "harness", "protocols", "agent_kwargs", "keep_task_network_policy", "seed_kwarg"},
        f"agents[{index}]",
    )
    profile_id = _identifier(value.get("id"), f"agents[{index}].id")
    harness = value.get("harness")
    if not isinstance(harness, str) or not harness.strip():
        raise CampaignError(f"agents[{index}].harness must be non-empty")
    try:
        adapter = create_adapter(harness)
    except ValueError as exc:
        raise CampaignError(f"agents[{index}].harness: {exc}") from exc
    declared = tuple(adapter.supported_protocols)
    protocols = (
        declared
        if "protocols" not in value
        else _protocols(value["protocols"], f"agents[{index}].protocols")
    )
    extra = sorted(set(protocols) - set(declared))
    if extra:
        raise CampaignError(
            f"agents[{index}] broadens {adapter.name!r} beyond its adapter contract: "
            + ", ".join(extra)
        )
    raw_kwargs = _mapping(value.get("agent_kwargs", {}), f"agents[{index}].agent_kwargs")
    try:
        kwargs = _safe_agent_kwargs(raw_kwargs)
    except ValueError as exc:
        raise CampaignError(f"agents[{index}].agent_kwargs: {exc}") from exc
    if adapter.integration_path != "harbor-agent" and kwargs:
        raise CampaignError(
            f"agents[{index}].agent_kwargs require a Harbor-native agent"
        )
    keep = value.get("keep_task_network_policy", False)
    if not isinstance(keep, bool):
        raise CampaignError(
            f"agents[{index}].keep_task_network_policy must be boolean"
        )
    seed_kwarg = value.get("seed_kwarg")
    if seed_kwarg is not None:
        if adapter.integration_path != "harbor-agent":
            raise CampaignError(f"agents[{index}].seed_kwarg is only for Harbor agents")
        try:
            _safe_agent_kwargs({seed_kwarg: "0"})
        except (TypeError, ValueError) as exc:
            raise CampaignError(f"agents[{index}].seed_kwarg: {exc}") from exc
    return AgentProfile(
        profile_id=profile_id,
        harness=adapter.name,
        protocols=protocols,
        agent_kwargs=kwargs,
        keep_task_network_policy=keep,
        seed_kwarg=seed_kwarg,
        integration_path=adapter.integration_path,
        harbor_agent=adapter.metadata().get("harbor_agent"),
        base_url_kind=adapter.base_url_kind,
        credential_env_names=tuple(
            adapter.metadata().get("credential_env_options", ())
        ),
    )


def _hash_task_tree(root: Path) -> str:
    """Hash path, mode, and bytes for a stable, symlink-free task identity."""
    try:
        root_facts = root.lstat()
    except OSError as exc:
        raise CampaignError(f"cannot stat task directory {root}: {exc}") from exc
    if root.is_symlink() or not stat.S_ISDIR(root_facts.st_mode):
        raise CampaignError(f"task path must be a non-symlink directory: {root}")
    for required in ("task.toml", "instruction.md", "tests", "environment"):
        if not (root / required).exists():
            raise CampaignError(f"task {root} is missing {required}")

    digest = hashlib.sha256(b"tdb-task-tree-v1\0")
    count = 0
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        directories.sort()
        files.sort()
        current_path = Path(current)
        for name in directories:
            child = current_path / name
            facts = child.lstat()
            if child.is_symlink() or not stat.S_ISDIR(facts.st_mode):
                raise CampaignError(f"task tree contains a non-directory/symlink: {child}")
        for name in files:
            count += 1
            if count > _MAX_TASK_FILES:
                raise CampaignError(f"task tree exceeds {_MAX_TASK_FILES} files: {root}")
            path = current_path / name
            before_path = path.lstat()
            if path.is_symlink() or not stat.S_ISREG(before_path.st_mode):
                raise CampaignError(f"task tree contains a non-regular/symlink file: {path}")
            relative = path.relative_to(root).as_posix().encode("utf-8")
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            digest.update(stat.S_IMODE(before_path.st_mode).to_bytes(4, "big"))
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
            fd = None
            try:
                fd = os.open(path, flags)
                before = os.fstat(fd)
                if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                        or (before.st_dev, before.st_ino)
                        != (before_path.st_dev, before_path.st_ino)):
                    raise CampaignError(f"unstable or hard-linked task file: {path}")
                digest.update(before.st_size.to_bytes(8, "big"))
                while True:
                    chunk = os.read(fd, 1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                after = os.fstat(fd)
                stable = ("st_dev", "st_ino", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
                if any(getattr(before, field) != getattr(after, field) for field in stable):
                    raise CampaignError(f"task file changed while hashing: {path}")
            except OSError as exc:
                raise CampaignError(f"cannot hash task file {path}: {exc}") from exc
            finally:
                if fd is not None:
                    os.close(fd)
    return digest.hexdigest()


def _parse_task(raw: Any, index: int, base_dir: Path) -> TaskProfile:
    value = _mapping(raw, f"tasks[{index}]")
    _only_keys(
        value,
        {"id", "path", "task_tree_sha256", "task_sif", "task_sif_sha256"},
        f"tasks[{index}]",
    )
    raw_path = value.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raise CampaignError(f"tasks[{index}].path must be non-empty")
    path = Path(raw_path)
    if not path.is_absolute():
        path = base_dir / path
    path = path.absolute()
    profile_id = _identifier(
        value.get("id", path.name), f"tasks[{index}].id"
    )
    actual_tree = _hash_task_tree(path)
    if value.get("task_tree_sha256") is not None:
        expected_tree = _sha256(
            value["task_tree_sha256"], f"tasks[{index}].task_tree_sha256"
        )
        if actual_tree != expected_tree:
            raise CampaignError(f"tasks[{index}] task tree digest mismatch")

    raw_sif = value.get("task_sif")
    raw_sif_digest = value.get("task_sif_sha256")
    if (raw_sif is None) != (raw_sif_digest is None):
        raise CampaignError(
            f"tasks[{index}].task_sif and task_sif_sha256 must be provided together"
        )
    task_sif: Path | None = None
    sif_digest: str | None = None
    if raw_sif is not None:
        if not isinstance(raw_sif, str) or not raw_sif:
            raise CampaignError(f"tasks[{index}].task_sif must be a path string")
        task_sif = Path(raw_sif)
        if not task_sif.is_absolute():
            task_sif = base_dir / task_sif
        task_sif = task_sif.absolute()
        sif_digest = _sha256(raw_sif_digest, f"tasks[{index}].task_sif_sha256")
    return TaskProfile(profile_id, path, actual_tree, task_sif, sif_digest)


def _parse_limits(raw: Any) -> ExecutionLimits:
    value = _mapping(raw if raw is not None else {}, "execution")
    _only_keys(
        value,
        {
            "max_workers", "max_cells", "budget_usd", "provider_concurrency",
            "call_timeout", "harbor_timeout", "max_tokens",
        },
        "execution",
    )
    max_workers = _positive_int(value.get("max_workers", 1), "execution.max_workers", maximum=64)
    max_cells_raw = value.get("max_cells")
    max_cells = (
        None if max_cells_raw is None
        else _positive_int(max_cells_raw, "execution.max_cells", maximum=10_000_000)
    )
    budget_raw = value.get("budget_usd")
    budget = None if budget_raw is None else _nonnegative_money(budget_raw, "execution.budget_usd")
    provider_raw = _mapping(value.get("provider_concurrency", {}), "execution.provider_concurrency")
    provider: dict[str, int] = {}
    for name, concurrency in provider_raw.items():
        name = _identifier(name, "execution.provider_concurrency key")
        provider[name] = _positive_int(
            concurrency, f"execution.provider_concurrency[{name!r}]", maximum=64
        )
    return ExecutionLimits(
        max_workers=max_workers,
        max_cells=max_cells,
        budget_usd=budget,
        provider_concurrency=provider,
        call_timeout=_positive_int(value.get("call_timeout", 180), "execution.call_timeout", maximum=86_400),
        harbor_timeout=_positive_int(value.get("harbor_timeout", 1800), "execution.harbor_timeout", maximum=604_800),
        max_tokens=_positive_int(value.get("max_tokens", 4096), "execution.max_tokens", maximum=10_000_000),
    )


def load_definition(path: str | os.PathLike[str]) -> CampaignDefinition:
    source_path = Path(path).absolute()
    raw = _mapping(_load_json(source_path, maximum=_MAX_SPEC_BYTES), "campaign")
    _only_keys(
        raw,
        {
            "schema_version", "campaign_id", "models", "model_catalog",
            "agents", "tasks", "seeds", "execution",
        },
        "campaign",
    )
    if raw.get("schema_version") != SPEC_SCHEMA:
        raise CampaignError(f"campaign.schema_version must be {SPEC_SCHEMA!r}")
    campaign_id = _identifier(raw.get("campaign_id"), "campaign.campaign_id")
    explicit_raw = raw.get("models", [])
    models_list = [
        _parse_model(value, index)
        for index, value in enumerate(_list(explicit_raw, "models"))
    ]
    catalog_sources: list[Mapping[str, Any]] = []
    if "model_catalog" in raw:
        catalog_models, catalog_source = _parse_catalog(
            raw["model_catalog"], source_path.parent
        )
        models_list.extend(catalog_models)
        catalog_sources.append(catalog_source)
    models = tuple(models_list)
    agents = tuple(_parse_agent(value, index) for index, value in enumerate(_list(raw.get("agents"), "agents")))
    tasks = tuple(
        _parse_task(value, index, source_path.parent)
        for index, value in enumerate(_list(raw.get("tasks"), "tasks"))
    )
    if not models or not agents or not tasks:
        raise CampaignError("campaign models, agents, and tasks must all be non-empty")
    for label, values in (
        ("model", [item.profile_id for item in models]),
        ("agent", [item.profile_id for item in agents]),
        ("task", [item.profile_id for item in tasks]),
    ):
        duplicates = sorted({item for item in values if values.count(item) > 1})
        if duplicates:
            raise CampaignError(f"duplicate {label} profile id(s): {', '.join(duplicates)}")
    raw_seeds = _list(raw.get("seeds", [None]), "seeds")
    if not raw_seeds:
        raise CampaignError("seeds must not be empty")
    seeds: list[int | None] = []
    for index, seed in enumerate(raw_seeds):
        if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
            raise CampaignError(f"seeds[{index}] must be an integer or null")
        if seed in seeds:
            raise CampaignError(f"duplicate seed: {seed!r}")
        seeds.append(seed)
    return CampaignDefinition(
        campaign_id,
        models,
        agents,
        tasks,
        tuple(seeds),
        _parse_limits(raw.get("execution")),
        tuple(catalog_sources),
    )


def build_plan(definition: CampaignDefinition) -> CampaignPlan:
    models = {item.profile_id: item for item in definition.models}
    agents = {item.profile_id: item for item in definition.agents}
    tasks = {item.profile_id: item for item in definition.tasks}
    cells: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    runtime: dict[str, RuntimeCell] = {}

    for task in definition.tasks:
        for model in definition.models:
            for agent in definition.agents:
                for seed in definition.seeds:
                    common = [p for p in agent.protocols if p in model.protocols]
                    protocol = common[0] if common else None
                    resolved_model = model.resolved_model(agent.profile_id, agent.harness)
                    reason: str | None = None
                    if protocol is None:
                        reason = "SKIPPED_INCOMPATIBLE_PROTOCOL"
                    elif not agent.protocols:
                        reason = "SKIPPED_CLIENT_MODEL_CONSTRAINT"
                    elif agent.harness == "terminus-2" and "/" not in resolved_model:
                        reason = "SKIPPED_CLIENT_MODEL_CONSTRAINT"
                    elif seed is not None and agent.integration_path == "harbor-agent" and not agent.seed_kwarg:
                        reason = "SKIPPED_CLIENT_MODEL_CONSTRAINT"
                    identity = {
                        "schema_version": "tdb-campaign-cell/v1",
                        "model_profile": model.public_summary(),
                        "agent_profile": agent.public_summary(),
                        "task_profile": task.public_summary(),
                        "resolved_model": resolved_model,
                        "protocol": protocol,
                        "seed": seed,
                        "execution": {
                            "call_timeout": definition.limits.call_timeout,
                            "harbor_timeout": definition.limits.harbor_timeout,
                            "max_tokens": definition.limits.max_tokens,
                        },
                    }
                    cell_id = "cell-" + _sha256_json(identity)[:32]
                    record = {
                        "cell_id": cell_id,
                        "model_profile_id": model.profile_id,
                        "agent_profile_id": agent.profile_id,
                        "task_profile_id": task.profile_id,
                        "matrix_column_id": f"{model.profile_id}::{agent.profile_id}",
                        "resolved_model": resolved_model,
                        "protocol": protocol,
                        "seed": seed,
                        "estimated_cost_usd": model.estimated_cost_usd,
                    }
                    if reason is not None:
                        excluded.append({**record, "status": BLOCKED, "classification": reason})
                        continue
                    cells.append(record)
                    runtime[cell_id] = RuntimeCell(
                        cell_id, model, agent, task, resolved_model, protocol, seed, record
                    )

    cells.sort(key=lambda value: value["cell_id"])
    excluded.sort(key=lambda value: value["cell_id"])
    core = {
        "schema_version": MANIFEST_SCHEMA,
        "runner": {
            "package": "terminal-daily-bench",
            "version": __version__,
        },
        "model_catalogs": list(definition.catalog_sources),
        "campaign_id": definition.campaign_id,
        "models": [models[key].public_summary() for key in sorted(models)],
        "agents": [agents[key].public_summary() for key in sorted(agents)],
        "tasks": [tasks[key].public_summary() for key in sorted(tasks)],
        "seeds": list(definition.seeds),
        "execution": definition.limits.public_summary(),
        "cells": cells,
        "excluded_cells": excluded,
    }
    fingerprint = _sha256_json(core)
    manifest = {**core, "campaign_fingerprint": fingerprint, "created_at": _utc_now()}
    return CampaignPlan(definition, manifest, runtime)


def plan_campaign(path: str | os.PathLike[str]) -> CampaignPlan:
    return build_plan(load_definition(path))


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{threading.get_ident()}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(temporary, flags, 0o600)
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(fd, data[offset:])
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_json(path: Path, value: Any) -> None:
    _atomic_write(path, json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(
        _read_stable_regular_bytes(path, maximum=_MAX_STATE_BYTES)
    ).hexdigest()


class CampaignStore:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root).absolute()
        if self.root.exists() and self.root.is_symlink():
            raise CampaignError(f"campaign state directory must not be a symlink: {self.root}")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.manifest_path = self.root / "manifest.json"
        self.checkpoint_path = self.root / "checkpoint.json"
        self.results_root = self.root / "attempts"
        self.export_path = self.root / "results.jsonl"
        self.lock_path = self.root / ".campaign.lock"
        self._lock_file = None

    @contextlib.contextmanager
    def lock(self):
        self._lock_file = self.lock_path.open("a+", encoding="utf-8")
        os.chmod(self.lock_path, 0o600)
        try:
            try:
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise CampaignBusyError(
                    f"campaign state is already locked: {self.root}"
                ) from exc
            yield
        finally:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
            self._lock_file.close()
            self._lock_file = None

    @staticmethod
    def _manifest_core(manifest: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: value for key, value in manifest.items()
            if key not in {"campaign_fingerprint", "created_at"}
        }

    def _verify_manifest(self, manifest: Mapping[str, Any]) -> None:
        if manifest.get("schema_version") != MANIFEST_SCHEMA:
            raise CampaignError("persisted manifest schema is not supported")
        actual = _sha256_json(self._manifest_core(manifest))
        if manifest.get("campaign_fingerprint") != actual:
            raise CampaignError("persisted manifest fingerprint does not match its contents")

    def initialize(self, plan: CampaignPlan, *, resume: bool) -> dict[str, Any]:
        expected = plan.manifest
        if self.manifest_path.exists():
            if not resume:
                raise CampaignError(
                    f"campaign state already exists; pass --resume: {self.root}"
                )
            current = _mapping(
                _load_json(self.manifest_path, maximum=_MAX_STATE_BYTES), "manifest"
            )
            self._verify_manifest(current)
            if current.get("campaign_fingerprint") != expected.get("campaign_fingerprint"):
                raise CampaignError("campaign definition does not match frozen manifest")
        else:
            if resume:
                raise CampaignError(f"cannot resume; manifest does not exist: {self.root}")
            _atomic_json(self.manifest_path, expected)

        all_records = list(expected["cells"]) + list(expected["excluded_cells"])
        if self.checkpoint_path.exists():
            state = _mapping(
                _load_json(self.checkpoint_path, maximum=_MAX_STATE_BYTES), "checkpoint"
            )
            self._validate_checkpoint(state, expected)
            self._recover_interrupted(state)
        else:
            state = {
                "schema_version": CHECKPOINT_SCHEMA,
                "campaign_id": expected["campaign_id"],
                "campaign_fingerprint": expected["campaign_fingerprint"],
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
                "runs": [],
                "cells": {},
            }
            excluded_ids = {item["cell_id"]: item for item in expected["excluded_cells"]}
            for record in all_records:
                excluded = excluded_ids.get(record["cell_id"])
                state["cells"][record["cell_id"]] = {
                    "status": BLOCKED if excluded else NOT_RUN,
                    "classification": (
                        excluded["classification"] if excluded else "NOT_RUN_PENDING"
                    ),
                    "attempts": [],
                    "result_path": None,
                    "result_sha256": None,
                    "updated_at": _utc_now(),
                }
            self.checkpoint(state)
        self._verify_success_results(state)
        return state

    def _validate_checkpoint(
        self, state: Mapping[str, Any], manifest: Mapping[str, Any]
    ) -> None:
        if state.get("schema_version") != CHECKPOINT_SCHEMA:
            raise CampaignError("persisted checkpoint schema is not supported")
        if state.get("campaign_fingerprint") != manifest.get("campaign_fingerprint"):
            raise CampaignError("checkpoint does not belong to frozen manifest")
        cells = _mapping(state.get("cells"), "checkpoint.cells")
        expected_ids = {
            item["cell_id"]
            for item in list(manifest["cells"]) + list(manifest["excluded_cells"])
        }
        if set(cells) != expected_ids:
            raise CampaignError("checkpoint cell set does not match frozen manifest")
        for cell_id, cell in cells.items():
            record = _mapping(cell, f"checkpoint.cells[{cell_id!r}]")
            if record.get("status") not in STATUSES:
                raise CampaignError(f"checkpoint has invalid status for {cell_id}")
            if not isinstance(record.get("attempts"), list):
                raise CampaignError(f"checkpoint attempts are invalid for {cell_id}")

    def _recover_interrupted(self, state: dict[str, Any]) -> None:
        changed = False
        for record in state["cells"].values():
            running = [a for a in record["attempts"] if a.get("state") == "RUNNING"]
            if not running:
                continue
            for attempt in running:
                attempt["state"] = "INTERRUPTED"
                attempt["finished_at"] = _utc_now()
            record.update({
                "status": NOT_RUN,
                "classification": "NOT_RUN_INTERRUPTED",
                "updated_at": _utc_now(),
            })
            changed = True
        if changed:
            self.checkpoint(state)

    def _verify_success_results(self, state: Mapping[str, Any]) -> None:
        for cell_id, record in state["cells"].items():
            if record.get("status") != SUCCESS:
                continue
            relative = record.get("result_path")
            expected = record.get("result_sha256")
            if not isinstance(relative, str) or not isinstance(expected, str):
                raise CampaignError(f"successful cell lacks result binding: {cell_id}")
            path = (self.root / relative).absolute()
            if not path.is_relative_to(self.root) or not path.exists():
                raise CampaignError(f"successful cell result is missing: {cell_id}")
            if _file_sha256(path) != expected:
                raise CampaignError(f"successful cell result digest changed: {cell_id}")

    def checkpoint(self, state: dict[str, Any]) -> None:
        state["updated_at"] = _utc_now()
        _atomic_json(self.checkpoint_path, state)

    def attempt_path(self, cell_id: str, attempt_number: int) -> Path:
        path = self.results_root / cell_id / f"attempt-{attempt_number:04d}.json"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)
        return path

    def export_successes(
        self, plan: CampaignPlan, state: Mapping[str, Any]
    ) -> None:
        rows: list[bytes] = []
        for cell_id in sorted(plan.runtime_cells):
            status = state["cells"][cell_id]
            if status["status"] != SUCCESS:
                continue
            path = self.root / status["result_path"]
            raw = _mapping(_load_json(path, maximum=_MAX_STATE_BYTES), "cell result")
            cell = plan.runtime_cells[cell_id]
            merged = {
                **raw,
                "campaign_id": plan.definition.campaign_id,
                "campaign_cell_id": cell_id,
                "model_profile_id": cell.model.profile_id,
                "agent_profile_id": cell.agent.profile_id,
                "task_profile_id": cell.task.profile_id,
                "matrix_column_id": cell.manifest_record["matrix_column_id"],
                "model_protocol": cell.protocol,
                "seed": cell.seed,
            }
            rows.append(_canonical_json(merged) + b"\n")
        _atomic_write(self.export_path, b"".join(rows))


CellRunner = Callable[[RuntimeCell, Path, int, CampaignStore, ExecutionLimits], int]


def _default_cell_runner(
    cell: RuntimeCell,
    output: Path,
    attempt_number: int,
    store: CampaignStore,
    limits: ExecutionLimits,
) -> int:
    work = store.root / "work" / cell.cell_id / f"attempt-{attempt_number:04d}"
    command = [
        sys.executable, "-m", "terminal_daily_bench.eval",
        "--model", cell.resolved_model,
        "--task", str(cell.task.path),
        "--out", str(output),
        "--work", str(work),
        "--harness", cell.agent.harness,
        "--model-protocol", cell.protocol,
        "--call-timeout", str(limits.call_timeout),
        "--harbor-timeout", str(limits.harbor_timeout),
        "--max-tokens", str(limits.max_tokens),
    ]
    resolved_base_url = cell.model.resolved_base_url(cell.protocol)
    if resolved_base_url is not None:
        command += ["--harness-base-url", resolved_base_url]
    if cell.seed is not None:
        if cell.agent.integration_path == "external-diff":
            command += ["--seed", str(cell.seed)]
        elif cell.agent.seed_kwarg:
            command += ["--agent-kwarg", f"{cell.agent.seed_kwarg}={cell.seed}"]
    for key, value in sorted(cell.agent.agent_kwargs.items()):
        command += ["--agent-kwarg", f"{key}={value}"]
    if cell.agent.keep_task_network_policy:
        command.append("--keep-task-network-policy")
    if cell.task.task_sif is not None:
        command += [
            "--task-sif", str(cell.task.task_sif),
            "--task-sif-sha256", str(cell.task.task_sif_sha256),
        ]
    completed = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode


def _validate_success_result(cell: RuntimeCell, result: Mapping[str, Any]) -> str:
    if result.get("dry_run") is not False:
        raise CampaignError("cell result is not a scored run")
    if result.get("model") != cell.resolved_model:
        raise CampaignError("cell result model does not match the frozen cell")
    if result.get("task") != cell.task.path.name:
        raise CampaignError("cell result task does not match the frozen cell")
    if result.get("model_protocol") != cell.protocol:
        raise CampaignError("cell result protocol does not match the frozen cell")
    if result.get("seed") != cell.seed:
        raise CampaignError("cell result seed does not match the frozen cell")
    if result.get("error") is not None:
        raise CampaignError("cell result reports an execution error")
    reward = result.get("reward")
    if isinstance(reward, bool) or not isinstance(reward, (int, float)) or not math.isfinite(float(reward)):
        raise CampaignError("cell result does not contain a finite reward")
    if cell.task.task_sif_sha256 is not None:
        if result.get("task_sif_post_sha256") != cell.task.task_sif_sha256:
            raise CampaignError("cell result lacks the post-Harbor SIF proof")
    harness_result = result.get("harness")
    aggregate_digest = (
        harness_result.get("harbor_result_sha256")
        if isinstance(harness_result, dict) else None
    )
    if not isinstance(aggregate_digest, str) or not _SHA256_RE.fullmatch(aggregate_digest):
        raise CampaignError("cell result lacks the authoritative aggregate digest")
    if cell.agent.integration_path == "harbor-agent":
        harness = harness_result
        if not isinstance(harness, dict) or harness.get("score_accepted") is not True:
            raise CampaignError("Harbor agent result lacks aggregate authority acceptance")
        if result.get("agent_completed") is not True:
            raise CampaignError("Harbor agent did not complete cleanly")
    else:
        proof = result.get("false_accept_check")
        if (not isinstance(proof, dict)
                or proof.get("protected_tests_relaid_by_harbor") is not True
                or proof.get("model_is_judge") is not False):
            raise CampaignError("external-diff result lacks protected replay proof")
    return "CLEAN_SCORED_SOLVED" if float(reward) >= 0.999 else "CLEAN_SCORED_UNSOLVED"


def _failure_outcome(
    cell: RuntimeCell, returncode: int | None, result: Mapping[str, Any] | None, error: str | None
) -> tuple[str, str, str]:
    detail = error or (str(result.get("error")) if result and result.get("error") else "cell runner failed")
    lower = detail.lower()
    harness = result.get("harness") if isinstance(result, dict) else None
    if "requires one of these environment variables" in lower or "credential" in lower and "unset" in lower:
        return BLOCKED, "SKIPPED_UNSUPPORTED_AUTH", detail
    if (isinstance(harness, dict) and harness.get("timed_out") is True) or "timed out" in lower:
        return FAILED, "FAILED_TIMEOUT", detail
    if "staged task sif" in lower or "sif" in lower and ("digest" in lower or "changed" in lower):
        return FAILED, "FAILED_SIF_DRIFT", detail
    if isinstance(harness, dict) and harness.get("stop_reason") == "scored_agent_error":
        return FAILED, "FAILED_AGENT_ERROR", detail
    if ("aggregate" in lower or "reward parsed" in lower or "authority" in lower
            or "protected replay proof" in lower):
        return FAILED, "FAILED_AGGREGATE_AUTHORITY", detail
    if "harbor exited" in lower or (returncode is not None and returncode != 0 and result):
        return FAILED, "FAILED_HARBOR", detail
    if "requires" in lower or "not on path" in lower or "configuration" in lower:
        return FAILED, "FAILED_AGENT_SETUP", detail
    return FAILED, "FAILED_AGENT_ERROR", detail


def _effective_limit(configured: int | float | None, override: int | float | None):
    if override is None:
        return configured
    if configured is None:
        return override
    return min(configured, override)


def _summary(state: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    counts = {status: 0 for status in (SUCCESS, FAILED, NOT_RUN, BLOCKED)}
    for record in state["cells"].values():
        counts[record["status"]] += 1
    return {
        "campaign_id": manifest["campaign_id"],
        "campaign_fingerprint": manifest["campaign_fingerprint"],
        "eligible_cells": len(manifest["cells"]),
        "excluded_cells": len(manifest["excluded_cells"]),
        "status_counts": counts,
    }


def run_campaign(
    spec_path: str | os.PathLike[str],
    state_dir: str | os.PathLike[str],
    *,
    resume: bool = False,
    retry_failed: bool = False,
    retry_blocked: bool = False,
    dry_run: bool = False,
    max_workers: int | None = None,
    max_cells: int | None = None,
    budget_usd: float | None = None,
    runner: CellRunner | None = None,
) -> tuple[int, dict[str, Any]]:
    plan = plan_campaign(spec_path)
    limits = plan.definition.limits
    effective_workers = int(_effective_limit(limits.max_workers, max_workers))
    effective_cells = _effective_limit(limits.max_cells, max_cells)
    effective_budget = _effective_limit(limits.budget_usd, budget_usd)
    if effective_workers < 1:
        raise CampaignError("max_workers override must be positive")
    if effective_cells is not None and effective_cells < 1:
        raise CampaignError("max_cells override must be positive")
    if effective_budget is not None:
        effective_budget = _nonnegative_money(effective_budget, "budget override")
    cell_runner = runner or _default_cell_runner
    store = CampaignStore(state_dir)

    with store.lock():
        state = store.initialize(plan, resume=resume)
        if dry_run:
            store.export_successes(plan, state)
            return 0, _summary(state, plan.manifest)

        state_guard = threading.Lock()
        previous_estimate = sum(
            float(attempt.get("estimated_cost_usd", 0.0) or 0.0)
            for record in state["cells"].values()
            for attempt in record["attempts"]
            if attempt.get("state") in {"RUNNING", "INTERRUPTED", "FINISHED"}
        )
        remaining_budget = (
            None if effective_budget is None else max(0.0, effective_budget - previous_estimate)
        )
        candidates: list[RuntimeCell] = []
        for cell_id in sorted(plan.runtime_cells):
            record = state["cells"][cell_id]
            if record["status"] == SUCCESS:
                continue
            if record["status"] == FAILED and not retry_failed:
                continue
            if record["status"] == BLOCKED and not retry_blocked:
                continue
            candidates.append(plan.runtime_cells[cell_id])

        selected: list[tuple[RuntimeCell, int]] = []
        for index, cell in enumerate(candidates):
            record = state["cells"][cell.cell_id]
            if effective_cells is not None and len(selected) >= effective_cells:
                if record["status"] == NOT_RUN:
                    record.update({
                        "classification": "NOT_RUN_CELL_LIMIT",
                        "updated_at": _utc_now(),
                    })
                continue
            estimate = cell.model.estimated_cost_usd
            if remaining_budget is not None and estimate is None:
                record.update({
                    "status": BLOCKED,
                    "classification": "BLOCKED_COST_UNKNOWN",
                    "updated_at": _utc_now(),
                })
                continue
            if remaining_budget is not None and float(estimate or 0.0) > remaining_budget + 1e-12:
                record.update({
                    "status": BLOCKED,
                    "classification": "BLOCKED_BUDGET",
                    "updated_at": _utc_now(),
                })
                continue
            if remaining_budget is not None:
                remaining_budget -= float(estimate or 0.0)
            attempt_number = len(record["attempts"]) + 1
            record["attempts"].append({
                "attempt": attempt_number,
                "state": "RUNNING",
                "started_at": _utc_now(),
                "estimated_cost_usd": estimate,
            })
            record.update({
                "status": NOT_RUN,
                "classification": "NOT_RUN_IN_PROGRESS",
                "updated_at": _utc_now(),
            })
            selected.append((cell, attempt_number))
        state["runs"].append({
            "started_at": _utc_now(),
            "max_workers": effective_workers,
            "max_cells": effective_cells,
            "budget_usd": effective_budget,
            "selected_cells": len(selected),
        })
        store.checkpoint(state)

        semaphores = {
            provider: threading.BoundedSemaphore(concurrency)
            for provider, concurrency in limits.provider_concurrency.items()
        }

        def execute(item: tuple[RuntimeCell, int]) -> None:
            cell, attempt_number = item
            output = store.attempt_path(cell.cell_id, attempt_number)
            semaphore = semaphores.get(cell.model.provider)
            returncode: int | None = None
            result: Mapping[str, Any] | None = None
            runner_error: str | None = None
            try:
                context = semaphore if semaphore is not None else contextlib.nullcontext()
                with context:
                    returncode = cell_runner(cell, output, attempt_number, store, limits)
                if output.exists():
                    result = _mapping(
                        _load_json(output, maximum=_MAX_STATE_BYTES), "cell result"
                    )
                if returncode == 0 and result is not None:
                    classification = _validate_success_result(cell, result)
                    status = SUCCESS
                    detail = None
                else:
                    status, classification, detail = _failure_outcome(
                        cell, returncode, result, None
                    )
            except Exception as exc:  # noqa: BLE001 -- checkpoint the failure, never fake success
                runner_error = f"{type(exc).__name__}: {exc}"
                status, classification, detail = _failure_outcome(
                    cell, returncode, result, runner_error
                )
            try:
                digest = _file_sha256(output) if output.exists() else None
                relative = (
                    output.relative_to(store.root).as_posix() if output.exists() else None
                )
            except Exception as exc:  # A malformed result path can never become SUCCESS.
                digest = None
                relative = None
                status = FAILED
                classification = "FAILED_RESULT_INTEGRITY"
                detail = f"{type(exc).__name__}: {exc}"
            with state_guard:
                record = state["cells"][cell.cell_id]
                attempt = record["attempts"][attempt_number - 1]
                attempt.update({
                    "state": "FINISHED",
                    "finished_at": _utc_now(),
                    "runner_returncode": returncode,
                    "status": status,
                    "classification": classification,
                    "result_path": relative,
                    "result_sha256": digest,
                })
                record.update({
                    "status": status,
                    "classification": classification,
                    "result_path": relative if status == SUCCESS else None,
                    "result_sha256": digest if status == SUCCESS else None,
                    "updated_at": _utc_now(),
                })
                store.checkpoint(state)

        with concurrent.futures.ThreadPoolExecutor(max_workers=effective_workers) as pool:
            futures = [pool.submit(execute, item) for item in selected]
            for future in concurrent.futures.as_completed(futures):
                future.result()

        state["runs"][-1]["finished_at"] = _utc_now()
        store.checkpoint(state)
        store.export_successes(plan, state)
        summary = _summary(state, plan.manifest)
        incomplete = any(
            state["cells"][cell_id]["status"] != SUCCESS
            for cell_id in plan.runtime_cells
        )
        return (1 if incomplete else 0), summary


__all__ = [
    "BLOCKED", "CHECKPOINT_SCHEMA", "CampaignBusyError", "CampaignDefinition",
    "CampaignError", "CampaignPlan", "CampaignStore", "FAILED", "MANIFEST_SCHEMA",
    "NOT_RUN", "SPEC_SCHEMA", "SUCCESS", "build_plan", "load_definition",
    "plan_campaign", "run_campaign",
]
