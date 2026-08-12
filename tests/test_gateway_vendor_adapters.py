"""Adversarial, credential-free tests for pending gateway vendor adapters."""
from __future__ import annotations

import base64
import json
from urllib.parse import quote

import pytest

from terminal_daily_bench.adapters import REGISTRY, create_adapter
from terminal_daily_bench.adapters.gateway_vendors import (
    ClineCLIAdapter,
    GeminiCLIAdapter,
    GooseAdapter,
    HermesAdapter,
    KimiCLIAdapter,
    OpenHandsAdapter,
    OpenHandsSDKAdapter,
    OpenClawAdapter,
    PiAdapter,
    QwenCodeAdapter,
    SWEAgentAdapter,
    TraeAgentAdapter,
)
from terminal_daily_bench.adapters.vendor import VendorConfigurationError


_BRIDGE = "http://127.0.0.1:18765/v1"
_DUMMY = "unit-test-ephemeral-bridge-token"
_GEMINI_BRIDGE = "http://127.0.0.1:18765"


@pytest.mark.parametrize(
    ("adapter_type", "model", "agent", "credential_env", "base_env", "model_env"),
    [
        (
            ClineCLIAdapter,
            "openai:gpt-test",
            "cline-cli",
            "API_KEY",
            "BASE_URL",
            None,
        ),
        (
            OpenHandsAdapter,
            "openai/gpt-test",
            "openhands",
            "LLM_API_KEY",
            "LLM_BASE_URL",
            "LLM_MODEL",
        ),
        (
            OpenHandsSDKAdapter,
            "openai/gpt-test",
            "openhands-sdk",
            "LLM_API_KEY",
            "LLM_BASE_URL",
            "LLM_MODEL",
        ),
        (
            QwenCodeAdapter,
            "gpt-test",
            "qwen-coder",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
        ),
        (
            SWEAgentAdapter,
            "openai/gpt-test",
            "swe-agent",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            None,
        ),
        (
            HermesAdapter,
            "openai/gpt-test",
            "hermes",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            None,
        ),
        (
            OpenClawAdapter,
            "openai/gpt-test",
            "openclaw",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            None,
        ),
    ],
)
def test_single_route_adapters_emit_only_bridge_local_secret_template(
    adapter_type, model, agent, credential_env, base_env, model_env
):
    adapter = adapter_type()
    spec = adapter.harbor_run_spec(
        model,
        base_url=_BRIDGE,
        environ={
            credential_env: _DUMMY,
            "UNRELATED_GATEWAY_SECRET": "must-never-be-copied",
        },
        protocol="openai-chat-completions",
        agent_kwargs={"max_iterations": 7},
    )
    persisted = json.dumps(
        {"repr": repr(spec), "summary": spec.public_summary()}, sort_keys=True
    )

    assert spec.agent == agent
    assert spec.agent_env[credential_env] == "${" + credential_env + "}"
    assert spec.agent_env[base_env] == _BRIDGE
    assert spec.process_env == {base_env: _BRIDGE, credential_env: _DUMMY}
    assert spec.credential_env_names == (credential_env,)
    assert spec.protocol == "openai-chat-completions"
    assert spec.agent_kwargs == {"max_iterations": "7"}
    if model_env is not None:
        assert spec.agent_env[model_env] == model
    assert _DUMMY not in persisted
    assert "must-never-be-copied" not in persisted
    assert "must-never-be-copied" not in json.dumps(dict(spec.process_env))


@pytest.mark.parametrize(
    "base_url",
    [
        "https://gateway.example/v1",
        "http://0.0.0.0:8765/v1",
        "http://host.docker.internal:8765/v1",
        "http://localhost.example:8765/v1",
        "http://user:password@127.0.0.1:8765/v1",
        "http://127.0.0.1:8765/v1?token=value",
        "http://127.0.0.1:8765/v1#fragment",
        18765,
    ],
)
def test_gateway_adapters_reject_non_loopback_or_decorated_urls(base_url):
    with pytest.raises(VendorConfigurationError):
        QwenCodeAdapter().harbor_run_spec(
            "gpt-test",
            base_url=base_url,
            environ={"OPENAI_API_KEY": _DUMMY},
        )


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:8765/v1/",
        "http://127.0.0.2:8765/v1",
        "http://[::1]:8765/v1",
    ],
)
def test_gateway_adapters_accept_canonical_loopback_variants(base_url):
    spec = QwenCodeAdapter().harbor_run_spec(
        "gpt-test",
        base_url=base_url,
        environ={"OPENAI_API_KEY": _DUMMY},
    )
    assert spec.agent_env["OPENAI_BASE_URL"] == base_url.rstrip("/")


def test_adapter_never_reads_ambient_vendor_credential(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-real-key-must-not-be-read")
    monkeypatch.setenv("OPENAI_BASE_URL", _BRIDGE)

    with pytest.raises(VendorConfigurationError, match="bridge-local"):
        QwenCodeAdapter().harbor_run_spec(
            "gpt-test", base_url=_BRIDGE, environ={}
        )

    dry_run = QwenCodeAdapter().harbor_run_spec(
        "gpt-test",
        base_url=_BRIDGE,
        environ={},
        require_credentials=False,
    )
    assert dict(dry_run.process_env) == {"OPENAI_BASE_URL": _BRIDGE}
    assert "ambient-real-key-must-not-be-read" not in repr(dry_run)


@pytest.mark.parametrize("adapter_type", [OpenHandsAdapter, OpenHandsSDKAdapter])
def test_openhands_maps_supervisor_openai_bridge_names_to_llm_names(adapter_type):
    adapter = adapter_type()
    spec = adapter.harbor_run_spec(
        "openai/gpt-test",
        environ={
            "OPENAI_API_KEY": _DUMMY,
            "OPENAI_BASE_URL": _BRIDGE,
        },
    )

    assert spec.agent_env["LLM_API_KEY"] == "${LLM_API_KEY}"
    assert spec.agent_env["LLM_BASE_URL"] == _BRIDGE
    assert spec.process_env == {
        "LLM_BASE_URL": _BRIDGE,
        "LLM_API_KEY": _DUMMY,
    }
    assert "OPENAI_API_KEY" not in spec.agent_env
    assert "OPENAI_API_KEY" not in spec.process_env


def test_bridge_credential_cannot_be_reflected_into_url_or_kwargs():
    adapter = QwenCodeAdapter()
    with pytest.raises(VendorConfigurationError, match="must not contain"):
        adapter.harbor_run_spec(
            "gpt-test",
            base_url=f"http://127.0.0.1:8765/v1/{_DUMMY}",
            environ={"OPENAI_API_KEY": _DUMMY},
        )
    with pytest.raises(VendorConfigurationError, match="must not contain"):
        adapter.harbor_run_spec(
            "gpt-test",
            base_url=_BRIDGE,
            environ={"OPENAI_API_KEY": _DUMMY},
            agent_kwargs={"reasoning_effort": "prefix-" + _DUMMY},
        )
    with pytest.raises(VendorConfigurationError, match="pass credentials"):
        adapter.harbor_run_spec(
            "gpt-test",
            base_url=_BRIDGE,
            environ={"OPENAI_API_KEY": _DUMMY},
            agent_kwargs={"api_token": "anything"},
        )

    encoded_token = "bridge/local token"
    with pytest.raises(VendorConfigurationError, match="must not contain"):
        adapter.harbor_run_spec(
            "gpt-test",
            base_url=(
                "http://127.0.0.1:8765/v1/"
                + quote(encoded_token, safe="")
            ),
            environ={"OPENAI_API_KEY": encoded_token},
        )
    with pytest.raises(VendorConfigurationError, match="must not contain"):
        adapter.harbor_run_spec(
            "gpt-test",
            base_url=_BRIDGE,
            environ={"OPENAI_API_KEY": encoded_token},
            agent_kwargs={"profile": quote(encoded_token, safe="")},
        )


@pytest.mark.parametrize(
    "adapter_type",
    [
        OpenHandsAdapter,
        OpenHandsSDKAdapter,
        SWEAgentAdapter,
        HermesAdapter,
        OpenClawAdapter,
    ],
)
@pytest.mark.parametrize(
    "model",
    [
        "gpt-test",
        "anthropic/gpt-test",
        "openai/",
        " openai/gpt-test",
        "openai/gpt-test ",
        "openai//gpt-test",
        "openai/../gpt-test",
        "openai/gpt test",
        "openai/gpt-test\n",
    ],
)
def test_litellm_clients_require_canonical_openai_transport_prefix(
    adapter_type, model
):
    credential_env = (
        "LLM_API_KEY"
        if adapter_type in {OpenHandsAdapter, OpenHandsSDKAdapter}
        else "OPENAI_API_KEY"
    )
    with pytest.raises(VendorConfigurationError):
        adapter_type().harbor_run_spec(
            model,
            base_url=_BRIDGE,
            environ={credential_env: _DUMMY},
        )


@pytest.mark.parametrize(
    "model",
    [
        "openai/gpt-test",
        "anthropic/claude-test",
        " gpt-test",
        "gpt-test ",
        "gpt test",
        "../gpt-test",
        "gpt-test\x00",
    ],
)
def test_qwen_code_requires_raw_canonical_gateway_catalog_id(model):
    with pytest.raises(VendorConfigurationError):
        QwenCodeAdapter().harbor_run_spec(
            model,
            base_url=_BRIDGE,
            environ={"OPENAI_API_KEY": _DUMMY},
        )


def test_gemini_cli_binds_exact_slash_model_to_nonsecret_agent_header():
    exact = "catalog/google/gemini-2.5-pro"
    spec = GeminiCLIAdapter().harbor_run_spec(
        "google/" + exact,
        base_url=_GEMINI_BRIDGE,
        environ={"GEMINI_API_KEY": _DUMMY},
        protocol="openai-chat-completions",
        agent_kwargs={"version": "0.55.1"},
    )
    header_name, encoded = spec.agent_env["GEMINI_CLI_CUSTOM_HEADERS"].split(
        ": ", 1
    )
    decoded = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()

    assert spec.agent == "gemini-cli"
    assert spec.model == "google/" + exact
    assert spec.agent_env["GEMINI_API_KEY"] == "${GEMINI_API_KEY}"
    assert spec.agent_env["GOOGLE_GEMINI_BASE_URL"] == _GEMINI_BRIDGE
    assert header_name == "X-Terminal-Daily-Gateway-Model"
    assert decoded == exact
    assert spec.agent_env["GOOGLE_GENAI_API_VERSION"] == "v1beta"
    assert spec.agent_env["GEMINI_API_KEY_AUTH_MECHANISM"] == "x-goog-api-key"
    assert spec.process_env == {
        "GOOGLE_GEMINI_BASE_URL": _GEMINI_BRIDGE,
        "GEMINI_API_KEY": _DUMMY,
    }
    assert "GEMINI_CLI_CUSTOM_HEADERS" not in spec.process_env
    assert spec.agent_kwargs == {"version": "0.55.1"}


@pytest.mark.parametrize(
    "base_url",
    [
        "http://127.0.0.1:18765/",
        "http://127.0.0.1:18765/v1",
        "http://localhost:18765",
        "http://127.0.0.2:18765",
        "https://127.0.0.1:18765",
        "http://user@127.0.0.1:18765",
        "http://127.0.0.1:18765?route=x",
        "https://gateway.example",
    ],
)
def test_gemini_cli_rejects_anything_but_exact_loopback_origin(base_url):
    with pytest.raises(VendorConfigurationError, match="exact loopback origin"):
        GeminiCLIAdapter().harbor_run_spec(
            "google/gemini-test",
            base_url=base_url,
            environ={"GEMINI_API_KEY": _DUMMY},
        )


@pytest.mark.parametrize(
    "model",
    [
        "gemini-test",
        "openai/gemini-test",
        "google/",
        "google//gemini-test",
        "google/../gemini-test",
        "google/gemini test",
        " google/gemini-test",
        "google/gemini-test\n",
    ],
)
def test_gemini_cli_rejects_unbound_or_noncanonical_models(model):
    with pytest.raises(VendorConfigurationError):
        GeminiCLIAdapter().harbor_run_spec(
            model,
            base_url=_GEMINI_BRIDGE,
            environ={"GEMINI_API_KEY": _DUMMY},
        )


def test_gemini_cli_metadata_discloses_both_wires_and_translation():
    metadata = GeminiCLIAdapter().metadata()
    assert metadata["harbor_agent"] == "gemini-cli"
    assert metadata["executable"] == "gemini"
    assert metadata["requires_root_install"] is True
    assert metadata["model_format"] == "google/<exact-gateway-catalog-id>"
    assert metadata["agent_wire"] == "gemini-native"
    assert metadata["upstream_wire"] == "openai-chat-completions"
    assert metadata["translation"] == "localhost-bounded"


@pytest.mark.parametrize(
    "model",
    [
        "gpt-test",
        "openai/gpt-test",
        "anthropic:claude-test",
        "openai:",
        "openai:../gpt-test",
        " openai:gpt-test",
        "openai:gpt-test ",
        "openai:gpt test",
        "openai:gpt-test\n",
    ],
)
def test_cline_requires_canonical_openai_colon_model(model):
    with pytest.raises(VendorConfigurationError):
        ClineCLIAdapter().harbor_run_spec(
            model,
            base_url=_BRIDGE,
            environ={"API_KEY": _DUMMY},
        )


def test_cline_maps_sanitized_openai_bridge_names_and_discloses_auth_state():
    adapter = ClineCLIAdapter()
    spec = adapter.harbor_run_spec(
        "openai:gpt-test",
        environ={
            "OPENAI_API_KEY": _DUMMY,
            "OPENAI_BASE_URL": _BRIDGE,
        },
    )

    assert spec.agent_env == {
        "API_KEY": "${API_KEY}",
        "BASE_URL": _BRIDGE,
    }
    assert spec.process_env == {"BASE_URL": _BRIDGE, "API_KEY": _DUMMY}
    metadata = adapter.metadata()
    assert metadata["bridge_token_persistence"] == (
        "possible_cline_auth_state_under_container_home"
    )
    assert metadata["protocol_selector"] == "openai-colon-provider-prefix"
    assert metadata["requires_root_install"] is True


@pytest.mark.parametrize(
    ("protocol", "model", "credential_env", "base_env", "base_kind"),
    [
        (
            "openai-chat-completions",
            "openai/gpt-test",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "openai",
        ),
        (
            "anthropic-messages",
            "anthropic/claude-test",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_BASE_URL",
            "anthropic",
        ),
    ],
)
def test_trae_protocol_selects_exactly_one_provider_route(
    protocol, model, credential_env, base_env, base_kind
):
    other_credential = (
        "ANTHROPIC_API_KEY"
        if credential_env == "OPENAI_API_KEY"
        else "OPENAI_API_KEY"
    )
    other_base = (
        "ANTHROPIC_BASE_URL"
        if base_env == "OPENAI_BASE_URL"
        else "OPENAI_BASE_URL"
    )
    spec = TraeAgentAdapter().harbor_run_spec(
        model,
        base_url=_BRIDGE,
        environ={
            credential_env: _DUMMY,
            other_credential: "unused-provider-token",
            other_base: "http://127.0.0.1:19999/wrong-provider",
        },
        protocol=protocol,
    )

    assert spec.agent == "trae-agent"
    assert spec.base_url_kind == base_kind
    assert spec.agent_env == {
        credential_env: "${" + credential_env + "}",
        base_env: _BRIDGE,
    }
    assert spec.process_env == {base_env: _BRIDGE, credential_env: _DUMMY}
    assert other_credential not in spec.agent_env
    assert other_credential not in spec.process_env
    assert other_base not in spec.agent_env
    assert other_base not in spec.process_env


@pytest.mark.parametrize(
    ("protocol", "model"),
    [
        ("openai-chat-completions", "anthropic/claude-test"),
        ("anthropic-messages", "openai/gpt-test"),
        ("openai-responses", "openai/gpt-test"),
    ],
)
def test_trae_rejects_cross_provider_or_unsupported_routes(protocol, model):
    with pytest.raises(VendorConfigurationError):
        TraeAgentAdapter().harbor_run_spec(
            model,
            base_url=_BRIDGE,
            environ={
                "OPENAI_API_KEY": _DUMMY,
                "ANTHROPIC_API_KEY": _DUMMY,
            },
            protocol=protocol,
        )


def test_trae_requires_protocol_and_records_key_persistence_risk():
    adapter = TraeAgentAdapter()
    with pytest.raises(VendorConfigurationError, match="explicit gateway protocol"):
        adapter.harbor_run_spec(
            "openai/gpt-test",
            base_url=_BRIDGE,
            environ={"OPENAI_API_KEY": _DUMMY},
        )

    metadata = adapter.metadata()
    assert metadata["compatibility_status"] == "pending_smoke"
    assert metadata["prior_public_inventory_status"] == "missing_public_client"
    assert metadata["bridge_token_persistence"] == (
        "temporary_harbor_yaml_bridge_token_only"
    )
    assert metadata["upstream_gateway_credentials_allowed"] is False
    assert "compatible" not in json.dumps(metadata).lower()


@pytest.mark.parametrize(
    ("protocol", "base_path"),
    [
        ("openai-chat-completions", "v1/chat/completions"),
        ("openai-responses", "v1/responses"),
    ],
)
def test_goose_pins_explicit_wire_protocol_instead_of_model_heuristic(
    protocol, base_path
):
    spec = GooseAdapter().harbor_run_spec(
        "openai/gpt-5-test",
        base_url=_BRIDGE,
        environ={
            "OPENAI_API_KEY": _DUMMY,
            "OPENAI_BASE_PATH": "ambient-must-be-overridden",
            "ANTHROPIC_API_KEY": "unused-provider-token",
        },
        protocol=protocol,
    )

    assert spec.agent == "goose"
    assert spec.agent_env == {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "OPENAI_BASE_URL": _BRIDGE,
        "OPENAI_BASE_PATH": base_path,
    }
    assert spec.process_env == {
        "OPENAI_BASE_URL": _BRIDGE,
        "OPENAI_API_KEY": _DUMMY,
        "OPENAI_BASE_PATH": base_path,
    }
    assert "ANTHROPIC_API_KEY" not in spec.agent_env
    assert "ambient-must-be-overridden" not in json.dumps(spec.public_summary())


def test_goose_requires_protocol_and_openai_provider_prefix():
    adapter = GooseAdapter()
    with pytest.raises(VendorConfigurationError, match="explicit gateway protocol"):
        adapter.harbor_run_spec(
            "openai/gpt-test",
            base_url=_BRIDGE,
            environ={"OPENAI_API_KEY": _DUMMY},
        )
    with pytest.raises(VendorConfigurationError, match="openai/provider-prefixed"):
        adapter.harbor_run_spec(
            "anthropic/claude-test",
            base_url=_BRIDGE,
            environ={"OPENAI_API_KEY": _DUMMY},
            protocol="openai-responses",
        )


@pytest.mark.parametrize(
    ("protocol", "model", "credential_env", "base_env", "base_kind"),
    [
        (
            "openai-chat-completions",
            "openai/gpt-test",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "openai",
        ),
        (
            "anthropic-messages",
            "anthropic/claude-test",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_BASE_URL",
            "anthropic",
        ),
    ],
)
def test_kimi_cli_selects_one_provider_and_injects_matching_local_base_url(
    protocol, model, credential_env, base_env, base_kind
):
    other_credential = (
        "ANTHROPIC_API_KEY"
        if credential_env == "OPENAI_API_KEY"
        else "OPENAI_API_KEY"
    )
    other_base = (
        "ANTHROPIC_BASE_URL"
        if base_env == "OPENAI_BASE_URL"
        else "OPENAI_BASE_URL"
    )
    spec = KimiCLIAdapter().harbor_run_spec(
        model,
        base_url=_BRIDGE,
        environ={
            credential_env: _DUMMY,
            other_credential: "unused-provider-token",
            other_base: "http://127.0.0.1:19999/wrong-provider",
        },
        protocol=protocol,
        agent_kwargs={"max_steps": 12},
    )
    persisted = json.dumps(
        {"repr": repr(spec), "summary": spec.public_summary()}, sort_keys=True
    )

    assert spec.agent == "kimi-cli"
    assert spec.base_url_kind == base_kind
    assert spec.agent_env == {
        credential_env: "${" + credential_env + "}",
        base_env: _BRIDGE,
    }
    assert spec.process_env == {base_env: _BRIDGE, credential_env: _DUMMY}
    assert spec.agent_kwargs == {"max_steps": "12", "base_url": _BRIDGE}
    assert other_credential not in spec.agent_env
    assert other_credential not in spec.process_env
    assert other_base not in spec.agent_env
    assert other_base not in spec.process_env
    assert _DUMMY not in persisted
    assert "unused-provider-token" not in persisted


@pytest.mark.parametrize(
    ("protocol", "model"),
    [
        ("openai-chat-completions", "anthropic/claude-test"),
        ("anthropic-messages", "openai/gpt-test"),
        ("openai-responses", "openai/gpt-test"),
    ],
)
def test_kimi_cli_rejects_cross_provider_or_unsupported_routes(protocol, model):
    with pytest.raises(VendorConfigurationError):
        KimiCLIAdapter().harbor_run_spec(
            model,
            base_url=_BRIDGE,
            environ={
                "OPENAI_API_KEY": _DUMMY,
                "ANTHROPIC_API_KEY": _DUMMY,
            },
            protocol=protocol,
        )


def test_kimi_cli_base_url_kwarg_is_derived_and_cannot_override_route():
    adapter = KimiCLIAdapter()
    common = {
        "base_url": _BRIDGE,
        "environ": {"OPENAI_API_KEY": _DUMMY},
        "protocol": "openai-chat-completions",
    }
    matching = adapter.harbor_run_spec(
        "openai/gpt-test",
        agent_kwargs={"base_url": _BRIDGE + "/"},
        **common,
    )
    assert matching.agent_kwargs["base_url"] == _BRIDGE

    with pytest.raises(VendorConfigurationError, match="must match"):
        adapter.harbor_run_spec(
            "openai/gpt-test",
            agent_kwargs={"base_url": "http://127.0.0.1:19999/v1"},
            **common,
        )
    with pytest.raises(VendorConfigurationError, match="localhost loopback"):
        adapter.harbor_run_spec(
            "openai/gpt-test",
            agent_kwargs={"base_url": "https://gateway.example/v1"},
            **common,
        )
    with pytest.raises(VendorConfigurationError, match="pass credentials"):
        adapter.harbor_run_spec(
            "openai/gpt-test",
            agent_kwargs={"api_key": "must-not-enter-harbor-json"},
            **common,
        )


def test_kimi_cli_does_not_read_ambient_route_or_credentials(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ambient-real-key-must-not-be-read")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", _BRIDGE)
    with pytest.raises(VendorConfigurationError, match="localhost auth bridge URL"):
        KimiCLIAdapter().harbor_run_spec(
            "anthropic/claude-test",
            environ={},
            protocol="anthropic-messages",
        )


@pytest.mark.parametrize(
    ("protocol", "model", "base_url", "credential_env", "base_env", "base_kind"),
    [
        (
            "openai-chat-completions",
            "openai-chat-completions/gpt-test",
            "http://127.0.0.1:18765/v1",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "openai",
        ),
        (
            "openai-responses",
            "openai-responses/gpt-test",
            "http://127.0.0.1:18765/v1",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "openai",
        ),
        (
            "anthropic-messages",
            "anthropic-messages/claude-test",
            "http://127.0.0.1:18765",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_BASE_URL",
            "anthropic",
        ),
    ],
)
def test_pi_binds_each_overlay_protocol_to_exact_loopback_route(
    protocol, model, base_url, credential_env, base_env, base_kind
):
    other_credential = (
        "ANTHROPIC_API_KEY"
        if credential_env == "OPENAI_API_KEY"
        else "OPENAI_API_KEY"
    )
    spec = PiAdapter().harbor_run_spec(
        model,
        base_url=base_url,
        environ={
            credential_env: _DUMMY,
            other_credential: "unused-provider-token",
        },
        protocol=protocol,
    )
    persisted = json.dumps(
        {"repr": repr(spec), "summary": spec.public_summary()}, sort_keys=True
    )

    assert spec.agent == "pi"
    assert spec.model == model
    assert spec.protocol == protocol
    assert spec.base_url_kind == base_kind
    assert spec.agent_env == {
        credential_env: "$" + "{" + credential_env + "}",
        base_env: base_url,
    }
    assert spec.process_env == {base_env: base_url, credential_env: _DUMMY}
    assert spec.credential_env_names == (credential_env,)
    assert other_credential not in spec.agent_env
    assert other_credential not in spec.process_env
    assert _DUMMY not in persisted
    assert "unused-provider-token" not in persisted


@pytest.mark.parametrize(
    ("protocol", "model"),
    [
        ("openai-chat-completions", "openai-responses/gpt-test"),
        ("openai-responses", "openai/gpt-test"),
        ("anthropic-messages", "anthropic/claude-test"),
        ("anthropic-messages", "anthropic-messages/../claude-test"),
        ("openai-responses", "openai-responses/gpt test"),
        ("openai-responses", "openai-responses/gpt-test@latest"),
    ],
)
def test_pi_rejects_mismatched_or_unsafe_overlay_model(protocol, model):
    base_url = (
        "http://127.0.0.1:18765"
        if protocol == "anthropic-messages"
        else _BRIDGE
    )
    credential_env = (
        "ANTHROPIC_API_KEY"
        if protocol == "anthropic-messages"
        else "OPENAI_API_KEY"
    )
    with pytest.raises(VendorConfigurationError):
        PiAdapter().harbor_run_spec(
            model,
            base_url=base_url,
            environ={credential_env: _DUMMY},
            protocol=protocol,
        )


@pytest.mark.parametrize(
    ("protocol", "base_url"),
    [
        ("openai-chat-completions", "http://localhost:18765/v1"),
        ("openai-responses", "https://127.0.0.1:18765/v1"),
        ("openai-responses", "http://127.0.0.1:18765"),
        ("openai-responses", "http://127.0.0.1:18765/v1/"),
        ("anthropic-messages", "http://127.0.0.1:18765/v1"),
        ("anthropic-messages", "http://127.0.0.1:18765/"),
        ("anthropic-messages", "http://127.0.0.2:18765"),
    ],
)
def test_pi_rejects_bridge_url_outside_selected_overlay_contract(
    protocol, base_url
):
    model = f"{protocol}/model-test"
    credential_env = (
        "ANTHROPIC_API_KEY"
        if protocol == "anthropic-messages"
        else "OPENAI_API_KEY"
    )
    with pytest.raises(VendorConfigurationError, match="exactly match"):
        PiAdapter().harbor_run_spec(
            model,
            base_url=base_url,
            environ={credential_env: _DUMMY},
            protocol=protocol,
        )


def test_pi_requires_explicit_protocol_and_stays_pending_runtime_smoke():
    adapter = PiAdapter()
    with pytest.raises(VendorConfigurationError, match="explicit gateway protocol"):
        adapter.harbor_run_spec(
            "openai-responses/gpt-test",
            base_url=_BRIDGE,
            environ={"OPENAI_API_KEY": _DUMMY},
        )

    dry_run = adapter.harbor_run_spec(
        "anthropic-messages/claude-test",
        base_url="http://127.0.0.1:18765",
        environ={},
        protocol="anthropic-messages",
        require_credentials=False,
    )
    assert dry_run.credential_env_names == ()
    assert dry_run.process_env == {
        "ANTHROPIC_BASE_URL": "http://127.0.0.1:18765"
    }

    metadata = adapter.metadata()
    assert metadata["harbor_agent"] == "pi"
    assert metadata["model_format"] == "gateway-protocol/<gateway-model>"
    assert metadata["compatibility_status"] == "pending_smoke"
    assert metadata["runtime_smoke_status"] == "not_run"
    assert metadata["bridge_token_persistence"] == (
        "environment_only_with_ephemeral_config_reference"
    )
    assert metadata["upstream_gateway_credentials_allowed"] is False


def test_hermes_excludes_unpinned_anthropic_route_and_records_reason():
    adapter = HermesAdapter()
    with pytest.raises(VendorConfigurationError, match="does not support protocol"):
        adapter.harbor_run_spec(
            "anthropic/claude-test",
            base_url=_BRIDGE,
            environ={"ANTHROPIC_API_KEY": _DUMMY},
            protocol="anthropic-messages",
        )
    metadata = adapter.metadata()
    assert metadata["supported_protocols"] == ["openai-chat-completions"]
    assert "anthropic-messages" in metadata["excluded_protocols"]
    assert "localhost bridge" in metadata["excluded_protocols"]["anthropic-messages"]


@pytest.mark.parametrize(
    ("adapter_type", "executable"),
    [
        (ClineCLIAdapter, "cline"),
        (GooseAdapter, "goose"),
        (HermesAdapter, "hermes"),
        (KimiCLIAdapter, "kimi"),
        (OpenClawAdapter, "openclaw"),
    ],
)
def test_second_batch_metadata_remains_pending_and_names_real_harbor_agent(
    adapter_type, executable
):
    metadata = adapter_type().metadata()
    assert metadata["harbor_agent"] == adapter_type().name
    assert metadata["executable"] == executable
    assert metadata["requires_root_install"] is True
    assert metadata["compatibility_status"] == "pending_smoke"
    assert metadata["runtime_smoke_status"] == "not_run"
    assert metadata["upstream_gateway_credentials_allowed"] is False


def test_kimi_cli_metadata_discloses_temporary_json_token_persistence():
    metadata = KimiCLIAdapter().metadata()
    assert metadata["bridge_token_persistence"] == (
        "temporary_harbor_json_bridge_token_only"
    )
    assert metadata["protocol_selector"] == (
        "provider-prefix-and-base_url-agent-kwarg"
    )
    assert metadata["bridge_credential_source_env_options"] == [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ]


def test_pending_gateway_adapters_are_registered_without_runtime_claims():
    assert {
        "goose",
        "gemini-cli",
        "cline-cli",
        "hermes",
        "kimi-cli",
        "openclaw",
        "openhands",
        "openhands-sdk",
        "pi",
        "qwen-code",
        "swe-agent",
        "trae-agent",
    } <= set(REGISTRY)
    assert create_adapter("open-hands").name == "openhands"
    assert create_adapter("block-goose").name == "goose"
    assert create_adapter("gemini").name == "gemini-cli"
    assert create_adapter("cline").name == "cline-cli"
    assert create_adapter("hermes-agent").name == "hermes"
    assert create_adapter("kimi").name == "kimi-cli"
    assert create_adapter("open-claw").name == "openclaw"
    assert create_adapter("openhands_sdk").name == "openhands-sdk"
    assert create_adapter("pi-coding-agent").name == "pi"
    assert create_adapter("qwen-coder").name == "qwen-code"
    assert create_adapter("sweagent").name == "swe-agent"
    assert create_adapter("trae").name == "trae-agent"
    for name in (
        "goose",
        "gemini-cli",
        "cline-cli",
        "hermes",
        "kimi-cli",
        "openclaw",
        "openhands",
        "openhands-sdk",
        "pi",
        "qwen-code",
        "swe-agent",
        "trae-agent",
    ):
        metadata = create_adapter(name).metadata()
        assert metadata["registry_status"] == "registered"
        assert metadata["compatibility_status"] == "pending_smoke"
        assert metadata["runtime_smoke_status"] == "not_run"


def test_pending_metadata_is_explicit_and_agent_specific():
    openhands_sdk = OpenHandsSDKAdapter().metadata()
    swe_agent = SWEAgentAdapter().metadata()
    qwen = QwenCodeAdapter().metadata()

    for metadata in (openhands_sdk, swe_agent, qwen):
        assert metadata["compatibility_status"] == "pending_smoke"
        assert metadata["runtime_smoke_status"] == "not_run"
        assert metadata["credential_boundary"] == "localhost_auth_bridge"
        assert metadata["registration_side_effect"] is False
        assert metadata["public_client_status"] == "registered_pending_smoke"
    assert openhands_sdk["available_tools"] == [
        "Terminal",
        "FileEditor",
        "TaskTracker",
    ]
    assert swe_agent["requires_root_install"] is True
    assert qwen["harbor_agent"] == "qwen-coder"
    assert qwen["executable"] == "qwen"
