"""Credential-free command-boundary tests for vendor harness adapters."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from terminal_daily_bench import eval as ev
from terminal_daily_bench.adapters import REGISTRY, create_adapter
from terminal_daily_bench.adapters.base import HarborRunSpec
from terminal_daily_bench.adapters.vendor import VendorConfigurationError


def test_registry_exposes_first_party_vendor_harnesses():
    assert {"single_shot", "claude-code", "codex"} <= set(REGISTRY)
    assert create_adapter("claude").name == "claude-code"
    assert create_adapter("codex-cli").name == "codex"


def test_codex_run_spec_keeps_credential_out_of_argv_and_metadata():
    credential = "unit-test-credential-value"
    adapter = create_adapter("codex")
    spec = adapter.harbor_run_spec(
        "gpt-test",
        environ={
            "OPENAI_API_KEY": credential,
            "OPENAI_BASE_URL": "https://proxy.example/v1",
        },
        agent_kwargs={"reasoning_effort": "high"},
    )
    command = ev.build_harbor_agent_command("/task", "/jobs", spec, [])
    persisted = json.dumps({"command": command, "spec": spec.public_summary()})

    assert credential not in persisted
    assert "OPENAI_API_KEY=${OPENAI_API_KEY}" in command
    assert spec.process_env["OPENAI_API_KEY"] == credential
    assert spec.agent_kwargs == {"reasoning_effort": "high"}


def test_claude_code_uses_anthropic_shape_and_rejects_credentialed_url():
    adapter = create_adapter("claude-code")
    spec = adapter.harbor_run_spec(
        "claude-test",
        environ={"ANTHROPIC_AUTH_TOKEN": "unit-test-token"},
        base_url="http://127.0.0.1:8765",
    )

    assert spec.agent == "claude-code"
    assert spec.model == "claude-test"
    assert spec.base_url_kind == "anthropic"
    assert spec.agent_env["ANTHROPIC_AUTH_TOKEN"] == "${ANTHROPIC_AUTH_TOKEN}"
    assert spec.agent_env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:8765"

    with pytest.raises(VendorConfigurationError, match="must not contain credentials"):
        adapter.harbor_run_spec(
            "claude-test",
            environ={"ANTHROPIC_API_KEY": "unit-test-value"},
            base_url="https://user:password@proxy.example/v1",
        )


def test_vendor_spec_selects_one_credential_and_trace_redacts_every_selected_secret():
    adapter = create_adapter("claude-code")
    spec = adapter.harbor_run_spec(
        "claude-test",
        environ={
            "ANTHROPIC_API_KEY": "selected-first-value",
            "ANTHROPIC_AUTH_TOKEN": "unselected-second-value",
        },
    )
    assert dict(spec.process_env) == {"ANTHROPIC_API_KEY": "selected-first-value"}

    multi = HarborRunSpec(
        agent="fixture",
        model="fixture",
        agent_env={
            "FIRST_TOKEN": "${FIRST_TOKEN}",
            "SECOND_SECRET": "${SECOND_SECRET}",
        },
        process_env={
            "FIRST_TOKEN": "shared-private-prefix",
            "SECOND_SECRET": "shared-private-prefix-with-suffix",
        },
        credential_env_names=("FIRST_TOKEN", "SECOND_SECRET"),
    )
    trace = ev._redact_trace(
        "shared-private-prefix / shared-private-prefix-with-suffix", multi
    )
    assert trace == "<redacted:FIRST_TOKEN> / <redacted:SECOND_SECRET>"


def test_sensitive_agent_kwarg_is_rejected():
    adapter = create_adapter("codex")
    with pytest.raises(VendorConfigurationError, match="pass credentials via environment"):
        adapter.harbor_run_spec(
            "gpt-test",
            environ={"OPENAI_API_KEY": "unit-test-value"},
            agent_kwargs={"api_token": "must-not-enter-argv"},
        )


def test_atif_telemetry_is_additive_and_best_effort(tmp_path):
    trajectory = tmp_path / "trial" / "agent" / "trajectory.json"
    trajectory.parent.mkdir(parents=True)
    trajectory.write_text(json.dumps({
        "schema_version": "ATIF-v1.7",
        "agent": {"name": "codex", "version": "1.2.3", "model_name": "gpt-test"},
        "steps": [
            {"llm_call_count": 1, "tool_calls": [{"function_name": "shell"}]},
            {"llm_call_count": 1, "tool_calls": []},
        ],
        "final_metrics": {
            "total_prompt_tokens": 10,
            "total_completion_tokens": 4,
            "total_cached_tokens": 3,
            "total_cost_usd": 0.01,
            "total_steps": 2,
            "extra": {"total_tokens": 14},
        },
    }))

    telemetry = ev.read_harness_telemetry(str(tmp_path))

    assert telemetry["version"] == "1.2.3"
    assert telemetry["n_turns"] == 2
    assert telemetry["n_llm_calls"] == 2
    assert telemetry["n_tool_calls"] == 1
    assert telemetry["total_tokens"] == 14


def test_network_override_is_scoped_to_environment_section(tmp_path):
    config = tmp_path / "task.toml"
    config.write_text(
        "[agent]\nnetwork_mode = \"no-network\"\n"
        "[environment]\nnetwork_mode = \"no-network\" # baseline\n"
        "[verifier]\nnetwork_mode = \"no-network\"\n"
    )

    assert ev._set_task_allow_internet(str(config), True) is True

    text = config.read_text()
    assert "[environment]\nnetwork_mode = \"public\" # baseline" in text
    assert text.count('network_mode = "no-network"') == 2


def _write_minimal_task(root: Path) -> Path:
    task = root / "td-test"
    (task / "tests").mkdir(parents=True)
    (task / "environment").mkdir()
    (task / "instruction.md").write_text("Repair the sample program.\n")
    (task / "task.toml").write_text(
        "[task]\nname = \"test/vendor\"\n"
        "[environment]\n"
        "docker_image = \"environment/Dockerfile\"\n"
        "allow_internet = false\n"
    )
    return task


def test_codex_dry_run_is_unscored_and_needs_no_credential(tmp_path, monkeypatch):
    task = _write_minimal_task(tmp_path)
    out = tmp_path / "dry.json"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    rc = ev.main([
        "--model", "gpt-test",
        "--task", str(task),
        "--out", str(out),
        "--work", str(tmp_path / "work"),
        "--harness", "codex",
        "--dry-run",
    ])
    result = json.loads(out.read_text())

    assert rc == 0
    assert result["dry_run"] is True
    assert result["reward"] is None
    assert result["false_accept_check"] is None
    assert result["harness"]["stop_reason"] == "dry_run"
    assert "OPENAI_API_KEY=${OPENAI_API_KEY}" in result["plan"]["command"]
    assert "allow_internet = false" in (task / "task.toml").read_text()
    run_copy = Path(result["plan"]["run_task"]) / "task.toml"
    assert "allow_internet = true" in run_copy.read_text()


def test_fake_harbor_command_boundary_uses_allowlist_and_redacts_trace(tmp_path, monkeypatch):
    """Test process isolation only; this fake does not prove protected replay."""
    task = _write_minimal_task(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "harbor"
    args_path = tmp_path / "args.json"
    env_path = tmp_path / "child-env.json"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "out = pathlib.Path(args[args.index('-o') + 1])\n"
        "trial = out / 'fake-trial'\n"
        "trial.mkdir(parents=True, exist_ok=True)\n"
        "(trial / 'result.json').write_text(json.dumps({\n"
        "  'stats': {'evals': {'vendor__fake': {'metrics': [{'mean': 1.0}]}}}\n"
        "}))\n"
        f"pathlib.Path({str(args_path)!r}).write_text(json.dumps(args))\n"
        f"pathlib.Path({str(env_path)!r}).write_text(json.dumps(dict(os.environ), sort_keys=True))\n"
        "print(json.dumps(dict(os.environ), sort_keys=True))\n"
    )
    fake.chmod(0o755)

    credential = "unit-test-private-value"
    ambient_credentials = {
        "ANTHROPIC_API_KEY": "unselected-anthropic-private-value",
        "ANTHROPIC_AUTH_TOKEN": "unselected-anthropic-token-private-value",
        "AWS_ACCESS_KEY_ID": "unselected-aws-id-private-value",
        "AWS_SECRET_ACCESS_KEY": "unselected-aws-secret-private-value",
        "GOOGLE_API_KEY": "unselected-google-private-value",
        "GOOGLE_APPLICATION_CREDENTIALS": "/private/gcp-credential.json",
        "SSH_AUTH_SOCK": "/private/ssh-agent.sock",
        "UNRELATED_CREDENTIAL": "unrelated-private-value",
    }
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("OPENAI_API_KEY", credential)
    for name, value in ambient_credentials.items():
        monkeypatch.setenv(name, value)
    out = tmp_path / "result.json"

    rc = ev.main([
        "--model", "gpt-test",
        "--task", str(task),
        "--out", str(out),
        "--work", str(tmp_path / "work"),
        "--harness", "codex",
        "--harbor-timeout", "10",
    ])
    result = json.loads(out.read_text())
    child_args = json.loads(args_path.read_text())
    child_env = json.loads(env_path.read_text())
    trace_path = Path(result["harness"]["trace_path"])
    trace = trace_path.read_text()
    command_path = trace_path.with_name("harbor_cmd.txt")

    assert rc == 0
    assert result["reward"] == 1.0
    assert result["solved"] is True
    assert result["patch_applied"] is None
    # A fabricated result exercises parsing, not verifier semantics or replay.
    assert result["false_accept_check"]["semantic_false_accept"] is None
    assert child_env["OPENAI_API_KEY"] == credential
    assert not set(ambient_credentials).intersection(child_env)
    assert Path(child_env["HOME"]).is_relative_to(tmp_path / "work")
    assert stat.S_IMODE(Path(child_env["HOME"]).stat().st_mode) == 0o700
    assert stat.S_IMODE(Path(child_env["HOME"]).parent.stat().st_mode) == 0o700
    assert credential not in json.dumps(result)
    assert credential not in json.dumps(child_args)
    assert credential not in trace
    assert "<redacted:OPENAI_API_KEY>" in trace
    assert "OPENAI_API_KEY=${OPENAI_API_KEY}" in child_args
    for value in ambient_credentials.values():
        assert value not in json.dumps(child_args)
        assert value not in json.dumps(result)
        assert value not in trace
    for name in ambient_credentials:
        assert name not in json.dumps(child_args)
        assert name not in json.dumps(result)
        assert name not in trace
    assert stat.S_IMODE(trace_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(command_path.stat().st_mode) == 0o600
