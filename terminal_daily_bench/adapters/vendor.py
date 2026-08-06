"""Harbor-native adapters for first-party coding-agent CLIs.

The current Harbor integration already owns installation, the interactive agent
loop, workspace mutation, trajectory collection, and protected-test re-lay for
Claude Code and Codex.  These adapters deliberately reuse that boundary: they
only construct a secret-safe ``harbor run`` specification and never read reward
files themselves.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit

from .base import HarborRunSpec, HarnessAdapter


_SENSITIVE_NAME = re.compile(r"(?:key|secret|token|password|credential|auth)", re.I)
_KWARG_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


class VendorConfigurationError(ValueError):
    """A vendor harness cannot be configured safely or completely."""


@dataclass(frozen=True)
class VendorHarnessSpec:
    name: str
    harbor_agent: str
    base_url_env: str
    credential_env_options: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    base_url_kind: str = "native"


def _safe_base_url(value: str | None) -> str | None:
    """Validate a base URL before it can appear in argv or result metadata."""
    if value is None or not value.strip():
        return None
    value = value.strip().rstrip("/")
    if any(ord(character) < 0x20 for character in value):
        raise VendorConfigurationError("harness base URL contains a control character")
    try:
        parsed = urlsplit(value)
        _ = parsed.port  # Force validation without persisting urllib's raw error.
    except ValueError:
        raise VendorConfigurationError("harness base URL has an invalid port") from None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise VendorConfigurationError("harness base URL must be an http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise VendorConfigurationError(
            "harness base URL must not contain credentials, a query, or a fragment"
        )
    return value


def _safe_agent_kwargs(values: Mapping[str, Any] | None) -> dict[str, str]:
    """Normalize Harbor agent kwargs while keeping credentials out of process argv."""
    result: dict[str, str] = {}
    for raw_key, raw_value in (values or {}).items():
        key = str(raw_key).strip()
        if not _KWARG_NAME.fullmatch(key):
            raise VendorConfigurationError(f"invalid agent kwarg name: {key!r}")
        if _SENSITIVE_NAME.search(key):
            raise VendorConfigurationError(
                f"agent kwarg {key!r} looks sensitive; pass credentials via environment"
            )
        value = str(raw_value)
        if "\x00" in value or "\n" in value or "\r" in value:
            raise VendorConfigurationError(
                f"agent kwarg {key!r} contains a forbidden control character"
            )
        result[key] = value
    return result


class HarborVendorAdapter(HarnessAdapter):
    """Generic installed-agent adapter configured by ``VendorHarnessSpec``."""

    integration_path = "harbor-agent"
    model_agnostic = True
    spec: VendorHarnessSpec

    def __init__(self, spec: VendorHarnessSpec | None = None) -> None:
        if spec is not None:
            self.spec = spec
        if not hasattr(self, "spec"):
            raise TypeError("HarborVendorAdapter requires a VendorHarnessSpec")
        self.name = self.spec.name
        self.base_url_kind = self.spec.base_url_kind

    def harbor_run_spec(
        self,
        model: str,
        *,
        base_url: str | None = None,
        environ: Mapping[str, str] | None = None,
        agent_kwargs: Mapping[str, Any] | None = None,
        require_credentials: bool = True,
        **_: Any,
    ) -> HarborRunSpec:
        """Create a Harbor invocation with env templates instead of secret values."""
        model = model.strip()
        if not model:
            raise VendorConfigurationError("model must not be empty")

        source_env = dict(os.environ if environ is None else environ)
        resolved_base = _safe_base_url(base_url or source_env.get(self.spec.base_url_env))
        credential_name = next(
            (name for name in self.spec.credential_env_options if source_env.get(name)),
            None,
        )
        if require_credentials and credential_name is None:
            choices = ", ".join(self.spec.credential_env_options)
            raise VendorConfigurationError(
                f"{self.name} requires one of these environment variables: {choices}"
            )

        agent_env: dict[str, str] = {}
        process_env: dict[str, str] = {}
        selected_credentials: tuple[str, ...] = ()
        if credential_name is not None:
            # subprocess receives the value; argv and persisted job configs receive
            # only the indirection. Harbor resolves ${NAME} from its own host env.
            agent_env[credential_name] = "${" + credential_name + "}"
            process_env[credential_name] = source_env[credential_name]
            selected_credentials = (credential_name,)
        elif not require_credentials:
            # A dry-run still shows the required shape without inventing a key.
            canonical = self.spec.credential_env_options[0]
            agent_env[canonical] = "${" + canonical + "}"

        if resolved_base is not None:
            agent_env[self.spec.base_url_env] = resolved_base
            # Claude Code's upstream adapter currently also consults the Harbor
            # process environment to decide custom-endpoint model-name handling.
            process_env[self.spec.base_url_env] = resolved_base

        safe_agent_kwargs = _safe_agent_kwargs(agent_kwargs)
        if credential_name is not None:
            credential_value = source_env[credential_name]
            if resolved_base is not None and credential_value in resolved_base:
                raise VendorConfigurationError(
                    "harness base URL must not contain the selected credential"
                )
            if any(credential_value in value for value in safe_agent_kwargs.values()):
                raise VendorConfigurationError(
                    "agent kwarg value must not contain the selected credential"
                )

        return HarborRunSpec(
            agent=self.spec.harbor_agent,
            model=model,
            agent_env=agent_env,
            agent_kwargs=safe_agent_kwargs,
            process_env=process_env,
            credential_env_names=selected_credentials,
            base_url_kind=self.spec.base_url_kind,
            requires_public_network=True,
        )

    def metadata(self) -> dict[str, Any]:
        data = super().metadata()
        data.update(
            {
                "harbor_agent": self.spec.harbor_agent,
                "credential_env_options": list(self.spec.credential_env_options),
                "base_url_env": self.spec.base_url_env,
            }
        )
        return data


class ClaudeCodeAdapter(HarborVendorAdapter):
    """First-party Claude Code through Harbor's ``claude-code`` installed agent."""

    spec = VendorHarnessSpec(
        name="claude-code",
        harbor_agent="claude-code",
        base_url_env="ANTHROPIC_BASE_URL",
        credential_env_options=(
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "CLAUDE_CODE_OAUTH_TOKEN",
        ),
        aliases=("claude", "claude_code"),
        base_url_kind="anthropic",
    )


class CodexAdapter(HarborVendorAdapter):
    """OpenAI Codex CLI through Harbor's ``codex`` installed agent."""

    spec = VendorHarnessSpec(
        name="codex",
        harbor_agent="codex",
        base_url_env="OPENAI_BASE_URL",
        # The patched Harbor Codex agent can upload an existing auth.json from
        # this host.  Passing its path through the same secret-template boundary
        # avoids reading or serializing the credential in Terminal Daily.
        credential_env_options=("OPENAI_API_KEY", "CODEX_AUTH_JSON_PATH"),
        aliases=("codex-cli", "codex_cli"),
        base_url_kind="openai",
    )


__all__ = [
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "HarborVendorAdapter",
    "VendorConfigurationError",
    "VendorHarnessSpec",
]
