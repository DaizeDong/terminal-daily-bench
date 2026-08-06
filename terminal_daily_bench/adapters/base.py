"""Contracts shared by patch-producing and Harbor-native harness adapters.

An adapter never interprets a verifier result.  A patch adapter returns a unified
diff; a Harbor-native adapter returns a declarative invocation for an installed
Harbor agent.  The runner remains the only component allowed to invoke the
protected-test gate and read its reward.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional


@dataclass
class AdapterResult:
    """What a harness returns for one (task, model) attempt."""
    patch: str                                  # unified diff the harness produced
    telemetry: Dict[str, Any] = field(default_factory=dict)  # tokens, cost_usd, turns, wall_s
    error: Optional[str] = None


@dataclass(frozen=True)
class HarborRunSpec:
    """Secret-safe description of one installed-agent Harbor invocation.

    ``agent_env`` values are passed to ``harbor --ae``.  Credential values must
    be environment templates such as ``${OPENAI_API_KEY}``, never literal
    credentials.  The corresponding real values live only in ``process_env`` and
    are inherited by the child process; that mapping is excluded from repr.
    """

    agent: str
    model: str
    agent_env: Mapping[str, str] = field(default_factory=dict)
    agent_kwargs: Mapping[str, str] = field(default_factory=dict)
    process_env: Mapping[str, str] = field(default_factory=dict, repr=False)
    credential_env_names: tuple[str, ...] = ()
    protocol: str | None = None
    base_url_kind: str = "native"
    requires_public_network: bool = True

    def public_summary(self) -> Dict[str, Any]:
        """Return audit metadata that contains names/templates, never secrets."""
        return {
            "agent": self.agent,
            "model": self.model,
            "agent_env": dict(self.agent_env),
            "agent_kwargs": dict(self.agent_kwargs),
            "credential_env_names": list(self.credential_env_names),
            "protocol": self.protocol,
            "base_url_kind": self.base_url_kind,
            "requires_public_network": self.requires_public_network,
        }


class HarnessAdapter(abc.ABC):
    """A pluggable scaffold which can produce a diff or configure a Harbor agent."""

    name: str = "base"
    integration_path: str = "external-diff"
    model_agnostic: bool = True
    base_url_kind: str = "openai"
    supported_protocols: tuple[str, ...] = ()
    base_url_env: str | None = None
    credential_env_options: tuple[str, ...] = ()

    def produce_patch(self, task_dir: str, failing_test_ids: List[str],
                      model: str, **kwargs: Any) -> AdapterResult:
        """Drive the harness on ``task_dir`` and return the candidate patch + telemetry.

        MUST NOT read or write the protected tests / the gold solution, and MUST NOT
        compute a reward. Scoring is done afterward by the execution gate.
        """
        raise NotImplementedError(f"{self.name} is not a patch-producing adapter")

    def harbor_run_spec(self, model: str, **kwargs: Any) -> HarborRunSpec:
        """Describe a Harbor-native invocation without starting it or scoring it."""
        raise NotImplementedError(f"{self.name} is not a Harbor-native adapter")

    def metadata(self) -> Dict[str, Any]:
        """Stable, additive metadata for result records and harness discovery."""
        return {
            "name": self.name,
            "integration_path": self.integration_path,
            "model_agnostic": self.model_agnostic,
            "base_url_kind": self.base_url_kind,
            "supported_protocols": list(self.supported_protocols),
            "base_url_env": self.base_url_env,
            "credential_env_options": list(self.credential_env_options),
        }
