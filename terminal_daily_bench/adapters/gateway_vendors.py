"""Pending-smoke Harbor adapters for gateway-routed coding agents.

These adapters intentionally support only a localhost authentication bridge.
The supervised process receives the bridge's short-lived local token; upstream
gateway credentials and routing headers remain in the bridge supervisor.  A
remote base URL is rejected so accidentally inherited vendor credentials cannot
be forwarded directly to an installed agent.

The classes live in a separate module so their pending-smoke status remains
explicit. Importing this module alone does not register an adapter; the package
registry does so centrally without implying runtime compatibility.
"""
from __future__ import annotations

import base64
import ipaddress
import re
from dataclasses import replace
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit

from .base import HarborRunSpec
from .vendor import (
    HarborVendorAdapter,
    VendorConfigurationError,
    VendorHarnessSpec,
    _safe_agent_kwargs,
    _safe_base_url,
)


PENDING_SMOKE = "pending_smoke"
MISSING_PUBLIC_CLIENT = "missing_public_client"
REGISTERED_PENDING_SMOKE = "registered_pending_smoke"

_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+@/-]{0,511}\Z")
_PI_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+/-]{0,255}\Z")
_OPENAI_CHAT = "openai-chat-completions"
_OPENAI_RESPONSES = "openai-responses"
_ANTHROPIC_MESSAGES = "anthropic-messages"


def _canonical_model(model: str, adapter_name: str) -> str:
    """Return a bounded model identifier without silently normalizing it."""
    if not isinstance(model, str) or _MODEL_ID.fullmatch(model) is None:
        raise VendorConfigurationError(
            f"{adapter_name} requires a canonical gateway model identifier"
        )
    if "//" in model or any(part in {"", ".", ".."} for part in model.split("/")):
        raise VendorConfigurationError(
            f"{adapter_name} requires a canonical gateway model identifier"
        )
    return model


def _openai_prefixed_model(model: str, adapter_name: str) -> str:
    model = _canonical_model(model, adapter_name)
    provider, separator, suffix = model.partition("/")
    if provider != "openai" or separator != "/" or not suffix:
        raise VendorConfigurationError(
            f"{adapter_name} requires an openai/provider-prefixed model name"
        )
    return model


def _openai_colon_prefixed_model(model: str, adapter_name: str) -> str:
    model = _canonical_model(model, adapter_name)
    provider, separator, suffix = model.partition(":")
    if provider != "openai" or separator != ":" or not suffix:
        raise VendorConfigurationError(
            f"{adapter_name} requires an openai:<gateway-model> name"
        )
    _raw_gateway_model(suffix, adapter_name)
    return model


def _raw_gateway_model(model: str, adapter_name: str) -> str:
    model = _canonical_model(model, adapter_name)
    if model.startswith(("openai/", "anthropic/")):
        raise VendorConfigurationError(
            f"{adapter_name} requires the raw gateway catalog model id, "
            "without a provider transport prefix"
        )
    return model


def _loopback_base_url(value: str | None) -> str:
    """Accept only an explicit HTTP(S) URL whose host is local loopback."""
    if value is not None and not isinstance(value, str):
        raise VendorConfigurationError(
            "gateway vendor adapter base URL must be a string"
        )
    resolved = _safe_base_url(value)
    if resolved is None:
        raise VendorConfigurationError(
            "gateway vendor adapter requires a localhost auth bridge URL"
        )
    hostname = urlsplit(resolved).hostname
    is_loopback = hostname is not None and hostname.lower() == "localhost"
    if hostname is not None and not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback:
        raise VendorConfigurationError(
            "gateway vendor adapter base URL must use localhost loopback"
        )
    return resolved


class GatewayBridgeVendorAdapter(HarborVendorAdapter):
    """Common fail-closed boundary for not-yet-smoked gateway clients."""

    model_env: str | None = None
    executable: str | None = None
    model_format = "gateway-model"
    requires_root_install = False
    available_tools: tuple[str, ...] = ()
    bridge_token_persistence = "environment_only"
    bridge_credential_source_envs: tuple[str, ...] = ()
    bridge_base_url_source_envs: tuple[str, ...] = ()
    excluded_protocols: Mapping[str, str] = {}
    protocol_selector: str | None = None

    def _validate_model(self, model: str, protocol: str) -> str:
        del protocol
        return _canonical_model(model, self.name)

    def _route(self, protocol: str) -> tuple[str, str, str]:
        """Return base-url env, credential env, and public base-url kind."""
        del protocol
        return (
            self.spec.base_url_env,
            self.spec.credential_env_options[0],
            self.spec.base_url_kind,
        )

    def harbor_run_spec(
        self,
        model: str,
        *,
        base_url: str | None = None,
        environ: Mapping[str, str] | None = None,
        agent_kwargs: Mapping[str, Any] | None = None,
        protocol: str | None = None,
        require_credentials: bool = True,
        **_: Any,
    ) -> HarborRunSpec:
        """Build a spec containing only the selected bridge-local credential.

        ``environ`` must be the supervisor-sanitized child environment.  This
        method deliberately does not fall back to ``os.environ``: doing so could
        mistake a developer's real vendor key for a bridge-local token.
        """
        if protocol is None:
            if len(self.supported_protocols) != 1:
                raise VendorConfigurationError(
                    f"{self.name} requires an explicit gateway protocol"
                )
            protocol = self.supported_protocols[0]
        if protocol not in self.supported_protocols:
            supported = ", ".join(self.supported_protocols)
            raise VendorConfigurationError(
                f"{self.name} does not support protocol {protocol!r}; "
                f"supported: {supported}"
            )

        canonical_model = self._validate_model(model, protocol)
        base_env, credential_env, base_url_kind = self._route(protocol)
        source_env = {} if environ is None else environ
        candidate_base = base_url
        if candidate_base is None:
            candidate_base = next(
                (
                    source_env.get(name)
                    for name in (base_env, *self.bridge_base_url_source_envs)
                    if source_env.get(name)
                ),
                None,
            )
        resolved_base = _loopback_base_url(candidate_base)
        safe_kwargs = _safe_agent_kwargs(agent_kwargs)

        bridge_token = next(
            (
                source_env.get(name)
                for name in (
                    credential_env,
                    *self.bridge_credential_source_envs,
                )
                if source_env.get(name)
            ),
            None,
        )
        if bridge_token is not None and not isinstance(bridge_token, str):
            raise VendorConfigurationError(
                f"{self.name} bridge credential must be a string"
            )
        if bridge_token and any(char in bridge_token for char in "\x00\r\n"):
            raise VendorConfigurationError(
                f"{self.name} bridge credential contains a control character"
            )
        if require_credentials and not bridge_token:
            raise VendorConfigurationError(
                f"{self.name} requires bridge-local {credential_env}"
            )

        agent_env: dict[str, str] = {
            credential_env: "${" + credential_env + "}",
            base_env: resolved_base,
        }
        if self.model_env is not None:
            agent_env[self.model_env] = canonical_model

        process_env: dict[str, str] = {base_env: resolved_base}
        credential_names: tuple[str, ...] = ()
        if bridge_token:
            if bridge_token in resolved_base or bridge_token in unquote(resolved_base):
                raise VendorConfigurationError(
                    "localhost bridge URL must not contain its local credential"
                )
            if any(
                bridge_token in value or bridge_token in unquote(value)
                for value in safe_kwargs.values()
            ):
                raise VendorConfigurationError(
                    "agent kwarg value must not contain the bridge credential"
                )
            process_env[credential_env] = bridge_token
            credential_names = (credential_env,)

        return HarborRunSpec(
            agent=self.spec.harbor_agent,
            model=canonical_model,
            agent_env=agent_env,
            agent_kwargs=safe_kwargs,
            process_env=process_env,
            credential_env_names=credential_names,
            protocol=protocol,
            base_url_kind=base_url_kind,
            requires_public_network=True,
        )

    def metadata(self) -> dict[str, Any]:
        data = super().metadata()
        data.update(
            {
                "aliases": list(self.spec.aliases),
                "compatibility_status": PENDING_SMOKE,
                "runtime_smoke_status": "not_run",
                # Preserve the pre-integration fact separately from current
                # registry state. Neither value is runtime-smoke evidence.
                "prior_public_inventory_status": MISSING_PUBLIC_CLIENT,
                "registration_side_effect": False,
                "registry_status": "registered",
                "credential_boundary": "localhost_auth_bridge",
                "accepted_credential_kind": "ephemeral_bridge_local_token_only",
                "bridge_credential_source_env_options": list(
                    dict.fromkeys(
                        (
                            *self.spec.credential_env_options,
                            *self.bridge_credential_source_envs,
                        )
                    )
                ),
                "upstream_gateway_credentials_allowed": False,
                "public_client_status": REGISTERED_PENDING_SMOKE,
                "executable": self.executable,
                "model_format": self.model_format,
                "requires_root_install": self.requires_root_install,
                "available_tools": list(self.available_tools),
                "bridge_token_persistence": self.bridge_token_persistence,
                "excluded_protocols": dict(self.excluded_protocols),
                "protocol_selector": self.protocol_selector,
            }
        )
        return data


class _OpenAIPrefixedGatewayAdapter(GatewayBridgeVendorAdapter):
    model_format = "openai/<gateway-model>"

    def _validate_model(self, model: str, protocol: str) -> str:
        del protocol
        return _openai_prefixed_model(model, self.name)


class OpenHandsAdapter(_OpenAIPrefixedGatewayAdapter):
    """OpenHands through its OpenAI-compatible LiteLLM transport."""

    spec = VendorHarnessSpec(
        name="openhands",
        harbor_agent="openhands",
        base_url_env="LLM_BASE_URL",
        credential_env_options=("LLM_API_KEY",),
        aliases=("open-hands", "open_hands"),
        base_url_kind="openai",
        supported_protocols=(_OPENAI_CHAT,),
    )
    model_env = "LLM_MODEL"
    executable = "openhands"
    # The current bridge supervisor exposes its ephemeral token using the
    # OpenAI-compatible names. Map that already-sanitized local token into the
    # LLM_* names consumed by OpenHands; no upstream key reaches this process.
    bridge_credential_source_envs = ("OPENAI_API_KEY",)
    bridge_base_url_source_envs = ("OPENAI_BASE_URL", "OPENAI_API_BASE")


class OpenHandsSDKAdapter(_OpenAIPrefixedGatewayAdapter):
    """OpenHands Software Agent SDK through Harbor's in-container runner."""

    spec = VendorHarnessSpec(
        name="openhands-sdk",
        harbor_agent="openhands-sdk",
        base_url_env="LLM_BASE_URL",
        credential_env_options=("LLM_API_KEY",),
        aliases=("open-hands-sdk", "openhands_sdk", "open_hands_sdk"),
        base_url_kind="openai",
        supported_protocols=(_OPENAI_CHAT,),
    )
    model_env = "LLM_MODEL"
    available_tools = ("Terminal", "FileEditor", "TaskTracker")
    bridge_credential_source_envs = ("OPENAI_API_KEY",)
    bridge_base_url_source_envs = ("OPENAI_BASE_URL", "OPENAI_API_BASE")


class PiAdapter(GatewayBridgeVendorAdapter):
    """Pi through Harbor's digest-bound, run-local models.json overlay.

    The Harbor overlay accepts only a gateway protocol as the provider prefix.
    It writes a temporary Pi provider registry whose API-key field names a
    provider-neutral environment variable; the local bridge token itself is
    never serialized into that file.
    """

    spec = VendorHarnessSpec(
        name="pi",
        harbor_agent="pi",
        base_url_env="OPENAI_BASE_URL",
        credential_env_options=("OPENAI_API_KEY", "ANTHROPIC_API_KEY"),
        aliases=("pi-coding-agent", "pi_coding_agent"),
        base_url_kind="multi-provider",
        supported_protocols=(
            _OPENAI_CHAT,
            _OPENAI_RESPONSES,
            _ANTHROPIC_MESSAGES,
        ),
    )
    executable = "pi"
    model_format = "gateway-protocol/<gateway-model>"
    requires_root_install = True
    bridge_token_persistence = "environment_only_with_ephemeral_config_reference"
    protocol_selector = "gateway-protocol-provider-prefix"

    def _route(self, protocol: str) -> tuple[str, str, str]:
        if protocol in {_OPENAI_CHAT, _OPENAI_RESPONSES}:
            return "OPENAI_BASE_URL", "OPENAI_API_KEY", "openai"
        if protocol == _ANTHROPIC_MESSAGES:
            return "ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "anthropic"
        raise VendorConfigurationError(f"unsupported Pi protocol: {protocol!r}")

    def _validate_model(self, model: str, protocol: str) -> str:
        if not isinstance(model, str):
            raise VendorConfigurationError(
                "pi requires a gateway-protocol-prefixed model name"
            )
        selected, separator, model_id = model.partition("/")
        if selected != protocol or separator != "/":
            raise VendorConfigurationError(
                "pi model provider must match the selected gateway protocol"
            )
        if (
            _PI_MODEL_ID.fullmatch(model_id) is None
            or model_id.endswith("/")
            or "//" in model_id
            or any(part in {"", ".", ".."} for part in model_id.split("/"))
        ):
            raise VendorConfigurationError(
                "pi requires a canonical gateway model identifier"
            )
        return model

    @staticmethod
    def _validate_pi_bridge_url(value: str | None, protocol: str) -> str:
        if not isinstance(value, str) or not value:
            raise VendorConfigurationError(
                "pi requires an explicit localhost auth bridge URL"
            )
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError:
            raise VendorConfigurationError(
                "pi localhost bridge URL has an invalid port"
            ) from None
        expected_path = "" if protocol == _ANTHROPIC_MESSAGES else "/v1"
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or port is None
            or not 1 <= port <= 65535
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.netloc != f"127.0.0.1:{port}"
            or parsed.path != expected_path
        ):
            raise VendorConfigurationError(
                "pi bridge URL must exactly match the selected gateway protocol"
            )
        return f"http://127.0.0.1:{port}{expected_path}"

    def harbor_run_spec(
        self,
        model: str,
        *,
        base_url: str | None = None,
        environ: Mapping[str, str] | None = None,
        protocol: str | None = None,
        **kwargs: Any,
    ) -> HarborRunSpec:
        if protocol is None:
            raise VendorConfigurationError("pi requires an explicit gateway protocol")
        if protocol not in self.supported_protocols:
            supported = ", ".join(self.supported_protocols)
            raise VendorConfigurationError(
                f"pi does not support protocol {protocol!r}; supported: {supported}"
            )
        base_env, _, _ = self._route(protocol)
        source_env = {} if environ is None else environ
        candidate_base = base_url or source_env.get(base_env)
        canonical_base = self._validate_pi_bridge_url(candidate_base, protocol)
        return super().harbor_run_spec(
            model,
            base_url=canonical_base,
            environ=source_env,
            protocol=protocol,
            **kwargs,
        )


class QwenCodeAdapter(GatewayBridgeVendorAdapter):
    """Qwen Code using the raw model id exposed by the gateway catalog."""

    spec = VendorHarnessSpec(
        name="qwen-code",
        # Harbor's current AgentName value is qwen-coder even though the class
        # and installed binary are named Qwen Code / qwen.
        harbor_agent="qwen-coder",
        base_url_env="OPENAI_BASE_URL",
        credential_env_options=("OPENAI_API_KEY",),
        aliases=("qwen-coder", "qwen_code", "qwen_coder"),
        base_url_kind="openai",
        supported_protocols=(_OPENAI_CHAT,),
    )
    model_env = "OPENAI_MODEL"
    executable = "qwen"
    model_format = "raw-gateway-catalog-id"

    def _validate_model(self, model: str, protocol: str) -> str:
        del protocol
        return _raw_gateway_model(model, self.name)


class GeminiCLIAdapter(GatewayBridgeVendorAdapter):
    """Official Gemini CLI through the bridge's bounded native translation."""

    spec = VendorHarnessSpec(
        name="gemini-cli",
        harbor_agent="gemini-cli",
        base_url_env="GOOGLE_GEMINI_BASE_URL",
        credential_env_options=("GEMINI_API_KEY",),
        aliases=("gemini", "gemini_cli", "google-gemini-cli"),
        base_url_kind="gemini-native",
        supported_protocols=(_OPENAI_CHAT,),
    )
    executable = "gemini"
    model_format = "google/<exact-gateway-catalog-id>"
    requires_root_install = True

    @staticmethod
    def _exact_origin(value: str | None) -> str:
        if not isinstance(value, str) or not value:
            raise VendorConfigurationError(
                "gemini-cli requires an explicit localhost bridge origin"
            )
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError:
            raise VendorConfigurationError(
                "gemini-cli localhost bridge origin has an invalid port"
            ) from None
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or port is None
            or not 1 <= port <= 65535
            or parsed.netloc != f"127.0.0.1:{port}"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path != ""
            or parsed.query
            or parsed.fragment
        ):
            raise VendorConfigurationError(
                "gemini-cli bridge URL must be an exact loopback origin"
            )
        return f"http://127.0.0.1:{port}"

    def _validate_model(self, model: str, protocol: str) -> str:
        del protocol
        canonical = _canonical_model(model, self.name)
        provider, separator, exact_model = canonical.partition("/")
        if provider != "google" or separator != "/" or not exact_model:
            raise VendorConfigurationError(
                "gemini-cli requires google/<exact-gateway-catalog-id>"
            )
        _canonical_model(exact_model, self.name)
        return canonical

    def harbor_run_spec(
        self,
        model: str,
        *,
        base_url: str | None = None,
        environ: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> HarborRunSpec:
        source_env = {} if environ is None else environ
        selected_base = base_url or source_env.get("GOOGLE_GEMINI_BASE_URL")
        canonical_base = self._exact_origin(selected_base)
        spec = super().harbor_run_spec(
            model,
            base_url=canonical_base,
            environ=source_env,
            **kwargs,
        )
        exact_model = spec.model.partition("/")[2]
        encoded_model = base64.urlsafe_b64encode(exact_model.encode("utf-8")).decode(
            "ascii"
        ).rstrip("=")
        agent_env = dict(spec.agent_env)
        # This is a non-secret route binding and intentionally lives only in
        # Harbor's per-agent environment.  The public process environment
        # continues to contain only the ephemeral local token and origin.
        agent_env["GEMINI_CLI_CUSTOM_HEADERS"] = (
            "X-Terminal-Daily-Gateway-Model: " + encoded_model
        )
        agent_env["GOOGLE_GENAI_API_VERSION"] = "v1beta"
        agent_env["GEMINI_API_KEY_AUTH_MECHANISM"] = "x-goog-api-key"
        return replace(spec, agent_env=agent_env)

    def metadata(self) -> dict[str, Any]:
        data = super().metadata()
        data.update(
            {
                "agent_wire": "gemini-native",
                "upstream_wire": "openai-chat-completions",
                "translation": "localhost-bounded",
            }
        )
        return data


class ClineCLIAdapter(GatewayBridgeVendorAdapter):
    """Cline CLI's explicit OpenAI custom-base route.

    Harbor invokes ``cline auth`` before the run. Cline may copy the supplied
    short-lived bridge token into auth state below ``~/.cline`` inside the task
    container, so this adapter must never receive an upstream gateway key.
    """

    spec = VendorHarnessSpec(
        name="cline-cli",
        harbor_agent="cline-cli",
        base_url_env="BASE_URL",
        credential_env_options=("API_KEY",),
        aliases=("cline", "cline_cli"),
        base_url_kind="openai",
        supported_protocols=(_OPENAI_CHAT,),
    )
    executable = "cline"
    model_format = "openai:<gateway-model>"
    requires_root_install = True
    bridge_credential_source_envs = ("OPENAI_API_KEY",)
    bridge_base_url_source_envs = ("OPENAI_BASE_URL", "OPENAI_API_BASE")
    bridge_token_persistence = "possible_cline_auth_state_under_container_home"
    protocol_selector = "openai-colon-provider-prefix"

    def _validate_model(self, model: str, protocol: str) -> str:
        del protocol
        return _openai_colon_prefixed_model(model, self.name)


class SWEAgentAdapter(_OpenAIPrefixedGatewayAdapter):
    """SWE-agent; Harbor installation currently needs root in the task image."""

    spec = VendorHarnessSpec(
        name="swe-agent",
        harbor_agent="swe-agent",
        base_url_env="OPENAI_BASE_URL",
        credential_env_options=("OPENAI_API_KEY",),
        aliases=("swe_agent", "sweagent"),
        base_url_kind="openai",
        supported_protocols=(_OPENAI_CHAT,),
    )
    executable = "sweagent"
    requires_root_install = True


class TraeAgentAdapter(GatewayBridgeVendorAdapter):
    """Trae Agent with protocol-selected, single-provider credential routing."""

    spec = VendorHarnessSpec(
        name="trae-agent",
        harbor_agent="trae-agent",
        # Discovery metadata needs one stable value. Runtime routing below is
        # dynamic and never injects this OpenAI default on an Anthropic route.
        base_url_env="OPENAI_BASE_URL",
        credential_env_options=("OPENAI_API_KEY", "ANTHROPIC_API_KEY"),
        aliases=("trae", "trae_agent", "trae-cli"),
        base_url_kind="multi-provider",
        supported_protocols=(_OPENAI_CHAT, _ANTHROPIC_MESSAGES),
    )
    executable = "trae-cli"
    model_format = "protocol-provider/<gateway-model>"
    bridge_token_persistence = "temporary_harbor_yaml_bridge_token_only"

    def _route(self, protocol: str) -> tuple[str, str, str]:
        if protocol == _OPENAI_CHAT:
            return "OPENAI_BASE_URL", "OPENAI_API_KEY", "openai"
        if protocol == _ANTHROPIC_MESSAGES:
            return "ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "anthropic"
        raise VendorConfigurationError(f"unsupported Trae protocol: {protocol!r}")

    def _validate_model(self, model: str, protocol: str) -> str:
        model = _canonical_model(model, self.name)
        expected_provider = (
            "openai" if protocol == _OPENAI_CHAT else "anthropic"
        )
        provider, separator, suffix = model.partition("/")
        if provider != expected_provider or separator != "/" or not suffix:
            raise VendorConfigurationError(
                "trae-agent model provider must match the selected protocol"
            )
        return model


class GooseAdapter(_OpenAIPrefixedGatewayAdapter):
    """Block Goose with an explicit OpenAI wire-protocol selector.

    Goose normally infers Chat Completions versus Responses from the model
    family. ``OPENAI_BASE_PATH`` is its audited explicit override, so this
    adapter pins the negotiated wire instead of relying on that heuristic.
    """

    spec = VendorHarnessSpec(
        name="goose",
        harbor_agent="goose",
        base_url_env="OPENAI_BASE_URL",
        credential_env_options=("OPENAI_API_KEY",),
        aliases=("block-goose", "goose-cli", "goose_cli"),
        base_url_kind="openai",
        supported_protocols=(_OPENAI_CHAT, _OPENAI_RESPONSES),
    )
    executable = "goose"
    requires_root_install = True
    protocol_selector = "OPENAI_BASE_PATH"

    def harbor_run_spec(self, model: str, **kwargs: Any) -> HarborRunSpec:
        spec = super().harbor_run_spec(model, **kwargs)
        base_path = {
            _OPENAI_CHAT: "v1/chat/completions",
            _OPENAI_RESPONSES: "v1/responses",
        }[spec.protocol]
        agent_env = dict(spec.agent_env)
        process_env = dict(spec.process_env)
        # Harbor's BaseInstalledAgent merges extra_env into every Goose exec.
        # Pin both views so ambient OPENAI_BASE_PATH cannot alter the wire.
        agent_env["OPENAI_BASE_PATH"] = base_path
        process_env["OPENAI_BASE_PATH"] = base_path
        return replace(spec, agent_env=agent_env, process_env=process_env)


class HermesAdapter(_OpenAIPrefixedGatewayAdapter):
    """Hermes' audited native OpenAI Chat route.

    Native Anthropic is deliberately excluded: Harbor's generated Hermes
    config has no safe base-URL field and current Hermes resolution can fall
    back to the public Anthropic endpoint. A local token must not reach it.
    """

    spec = VendorHarnessSpec(
        name="hermes",
        harbor_agent="hermes",
        base_url_env="OPENAI_BASE_URL",
        credential_env_options=("OPENAI_API_KEY",),
        aliases=("hermes-agent", "hermes_agent", "hermes-cli"),
        base_url_kind="openai",
        supported_protocols=(_OPENAI_CHAT,),
    )
    executable = "hermes"
    requires_root_install = True
    excluded_protocols = {
        _ANTHROPIC_MESSAGES: (
            "Harbor cannot pin generated Hermes native-Anthropic config to "
            "the selected localhost bridge"
        )
    }


class KimiCLIAdapter(GatewayBridgeVendorAdapter):
    """Kimi CLI with protocol-selected provider config and local base URL."""

    spec = VendorHarnessSpec(
        name="kimi-cli",
        harbor_agent="kimi-cli",
        base_url_env="OPENAI_BASE_URL",
        credential_env_options=("OPENAI_API_KEY", "ANTHROPIC_API_KEY"),
        aliases=("kimi", "kimi_cli", "moonshot-kimi-cli"),
        base_url_kind="multi-provider",
        supported_protocols=(_OPENAI_CHAT, _ANTHROPIC_MESSAGES),
    )
    executable = "kimi"
    model_format = "protocol-provider/<gateway-model>"
    requires_root_install = True
    bridge_token_persistence = "temporary_harbor_json_bridge_token_only"
    protocol_selector = "provider-prefix-and-base_url-agent-kwarg"

    def _route(self, protocol: str) -> tuple[str, str, str]:
        if protocol == _OPENAI_CHAT:
            return "OPENAI_BASE_URL", "OPENAI_API_KEY", "openai"
        if protocol == _ANTHROPIC_MESSAGES:
            return "ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "anthropic"
        raise VendorConfigurationError(f"unsupported Kimi CLI protocol: {protocol!r}")

    def _validate_model(self, model: str, protocol: str) -> str:
        model = _canonical_model(model, self.name)
        expected_provider = (
            "openai" if protocol == _OPENAI_CHAT else "anthropic"
        )
        provider, separator, suffix = model.partition("/")
        if provider != expected_provider or separator != "/" or not suffix:
            raise VendorConfigurationError(
                "kimi-cli model provider must match the selected protocol"
            )
        return model

    def harbor_run_spec(self, model: str, **kwargs: Any) -> HarborRunSpec:
        spec = super().harbor_run_spec(model, **kwargs)
        base_env, _, _ = self._route(spec.protocol)
        selected_base = spec.agent_env[base_env]
        agent_kwargs = dict(spec.agent_kwargs)
        configured_base = agent_kwargs.get("base_url")
        if configured_base is not None:
            configured_base = _loopback_base_url(configured_base)
            if configured_base != selected_base:
                raise VendorConfigurationError(
                    "kimi-cli base_url agent kwarg must match the selected "
                    "localhost bridge URL"
                )
        # Kimi's Harbor integration consumes this kwarg and writes the chosen
        # URL plus only the short-lived local token to /tmp/kimi-config.json.
        agent_kwargs["base_url"] = selected_base
        return replace(spec, agent_kwargs=agent_kwargs)


class OpenClawAdapter(_OpenAIPrefixedGatewayAdapter):
    """OpenClaw's audited OpenAI-compatible custom-provider route."""

    spec = VendorHarnessSpec(
        name="openclaw",
        harbor_agent="openclaw",
        base_url_env="OPENAI_BASE_URL",
        credential_env_options=("OPENAI_API_KEY",),
        aliases=("open-claw", "open_claw"),
        base_url_kind="openai",
        supported_protocols=(_OPENAI_CHAT,),
    )
    executable = "openclaw"
    requires_root_install = True
    excluded_protocols = {
        _ANTHROPIC_MESSAGES: (
            "OpenClaw's audited custom-provider schema is OpenAI Chat wire only"
        )
    }


# Compatibility spelling for callers that title-case the upstream project as
# ``SweAgent``. Both names refer to exactly the same adapter class.
SweAgentAdapter = SWEAgentAdapter
OpenHandsSdkAdapter = OpenHandsSDKAdapter
KimiCliAdapter = KimiCLIAdapter


__all__ = [
    "ClineCLIAdapter",
    "GeminiCLIAdapter",
    "GatewayBridgeVendorAdapter",
    "GooseAdapter",
    "HermesAdapter",
    "KimiCLIAdapter",
    "KimiCliAdapter",
    "MISSING_PUBLIC_CLIENT",
    "OpenHandsAdapter",
    "OpenHandsSDKAdapter",
    "OpenHandsSdkAdapter",
    "OpenClawAdapter",
    "PiAdapter",
    "PENDING_SMOKE",
    "QwenCodeAdapter",
    "REGISTERED_PENDING_SMOKE",
    "SWEAgentAdapter",
    "SweAgentAdapter",
    "TraeAgentAdapter",
]
