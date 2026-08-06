"""Credential-free command-boundary tests for vendor harness adapters."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from terminal_daily_bench import cli as tdb_cli
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


def test_codex_auth_json_path_uses_secret_template_without_reading_file(tmp_path):
    auth = tmp_path / "auth.json"
    auth.write_text("opaque-test-auth-bytes")
    adapter = create_adapter("codex")
    spec = adapter.harbor_run_spec(
        "gpt-test", environ={"CODEX_AUTH_JSON_PATH": str(auth)}
    )
    command = ev.build_harbor_agent_command("/task", "/jobs", spec, [])
    persisted = json.dumps({"command": command, "spec": spec.public_summary()})

    assert str(auth) not in persisted
    assert "CODEX_AUTH_JSON_PATH=${CODEX_AUTH_JSON_PATH}" in command
    assert spec.process_env["CODEX_AUTH_JSON_PATH"] == str(auth)
    assert spec.credential_env_names == ("CODEX_AUTH_JSON_PATH",)


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

    with pytest.raises(VendorConfigurationError, match="invalid port") as exc_info:
        adapter.harbor_run_spec(
            "claude-test",
            environ={"ANTHROPIC_API_KEY": "unit-test-value"},
            base_url="https://proxy.example:private-port-value/v1",
        )
    assert "private-port-value" not in str(exc_info.value)


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

    credential = "selected-private-credential-value"
    with pytest.raises(VendorConfigurationError, match="must not contain"):
        adapter.harbor_run_spec(
            "gpt-test",
            environ={"OPENAI_API_KEY": credential},
            agent_kwargs={"reasoning_effort": "prefix-" + credential + "-suffix"},
        )


def test_selected_credential_cannot_enter_base_url_path():
    adapter = create_adapter("codex")
    credential = "selected-private-credential-value"

    with pytest.raises(VendorConfigurationError, match="base URL must not contain"):
        adapter.harbor_run_spec(
            "gpt-test",
            environ={"OPENAI_API_KEY": credential},
            base_url="https://proxy.example/v1/" + credential,
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


def test_atif_telemetry_is_strictly_bounded_and_drops_nested_data(tmp_path):
    sentinel = "trajectory-private-sentinel"
    trajectory = tmp_path / "trial" / "agent" / "trajectory.json"
    trajectory.parent.mkdir(parents=True)
    trajectory.write_text(json.dumps({
        "agent": {
            "version": "v" * 129,
            "model_name": sentinel,
            "nested": {"secret": sentinel},
        },
        "steps": [{
            "llm_call_count": 1,
            "tool_calls": [{"arguments": {"secret": sentinel}}],
            "nested": {"secret": sentinel},
        }],
        "final_metrics": {
            "total_prompt_tokens": True,
            "total_completion_tokens": 4,
            "total_cached_tokens": -1,
            "total_cost_usd": float("nan"),
            "total_steps": 1,
            "extra": {"total_tokens": sentinel, "nested": {"secret": sentinel}},
        },
        "nested": {"secret": sentinel},
    }))

    telemetry = ev.read_harness_telemetry(str(tmp_path))
    persisted = json.dumps(telemetry)

    assert persisted.count(sentinel) == 1
    assert "version" not in telemetry
    assert telemetry["trajectory_model"] == sentinel  # redacted by the caller boundary
    assert "prompt_tokens" not in telemetry
    assert telemetry["completion_tokens"] == 4
    assert "cached_tokens" not in telemetry
    assert "cost_usd" not in telemetry
    assert "total_tokens" not in telemetry
    assert set(telemetry) <= {
        "trajectory_model", "n_turns", "n_llm_calls", "n_tool_calls",
        "completion_tokens", "trajectory_path",
    }


def test_recursive_credential_redaction_covers_nested_keys_and_auth_path(tmp_path):
    auth_path = str(tmp_path / "private-auth.json")
    spec = create_adapter("codex").harbor_run_spec(
        "gpt-test", environ={"CODEX_AUTH_JSON_PATH": auth_path}
    )
    payload = {
        "version": auth_path,
        f"key:{auth_path}": [
            {"deep": f"prefix:{auth_path}:suffix"},
            (auth_path,),
        ],
    }

    redacted = ev._redact_credentials(payload, spec)

    assert auth_path not in json.dumps(redacted)
    assert "<redacted:CODEX_AUTH_JSON_PATH>" in json.dumps(redacted)


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


def test_cli_basename_out_is_resolved_without_empty_dirname(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        tdb_cli._eval, "main", lambda argv: captured.setdefault("argv", argv) and 0
    )
    args = SimpleNamespace(
        model="gpt-test",
        task="tasks/archive/td-test",
        out="result.json",
        harness="codex",
        harness_base_url=None,
        agent_kwarg=[],
        dry_run=True,
        keep_task_network_policy=False,
        task_sif=None,
        task_sif_sha256=None,
        harbor_timeout=None,
    )

    assert tdb_cli._cmd_run(args) == 0

    out = captured["argv"][captured["argv"].index("--out") + 1]
    assert out == str((tmp_path / "result.json").resolve())


def test_doctor_never_prints_configured_base_url(tmp_path, monkeypatch, capsys):
    secret_url = "https://user:port-secret@example.invalid/v1?token=query-secret#fragment"
    monkeypatch.setenv("OPENAI_BASE_URL", secret_url)
    monkeypatch.setenv("OPENAI_API_KEY", "configured-key-value")
    monkeypatch.setattr(tdb_cli.shutil, "which", lambda _: None)

    rc = tdb_cli._cmd_doctor(SimpleNamespace(
        harness="codex", oracle_only=True, task=None
    ))
    output = capsys.readouterr().out

    assert rc == 1  # Harbor/runtime are intentionally absent in this fixture.
    assert "<configured, redacted>" in output
    assert secret_url not in output
    assert "port-secret" not in output
    assert "query-secret" not in output


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


def test_dry_run_pins_prebuilt_sif_only_on_disposable_copy(tmp_path, monkeypatch):
    task = _write_minimal_task(tmp_path)
    source_toml = (task / "task.toml").read_text()
    sif = tmp_path / "task-image.sif"
    sif.write_bytes(b"test-only-sif-bytes")
    digest = hashlib.sha256(sif.read_bytes()).hexdigest()
    out = tmp_path / "dry-sif.json"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    rc = ev.main([
        "--model", "gpt-test",
        "--task", str(task),
        "--out", str(out),
        "--work", str(tmp_path / "work-sif"),
        "--harness", "codex",
        "--dry-run",
        "--task-sif", str(sif.resolve()),
        "--task-sif-sha256", digest,
    ])
    result = json.loads(out.read_text())
    with (Path(result["plan"]["run_task"]) / "task.toml").open("rb") as fh:
        run_config = tomllib.load(fh)

    assert rc == 0
    effective = Path(result["effective_image"])
    assert effective != sif.resolve()
    assert effective.is_relative_to(tmp_path / "work-sif")
    assert effective.read_bytes() == sif.read_bytes()
    assert stat.S_IMODE(effective.stat().st_mode) == 0o400
    assert result["task_sif_source"] == str(sif.resolve())
    assert result["task_sif_sha256"] == digest
    assert run_config["environment"]["docker_image"] == str(effective)
    assert (task / "task.toml").read_text() == source_toml


def test_task_sif_staging_rejects_symlink_and_digest_mismatch(tmp_path):
    source = tmp_path / "source.sif"
    source.write_bytes(b"source-sif")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    symlink = tmp_path / "symlink.sif"
    symlink.symlink_to(source)

    with pytest.raises(ValueError, match="symbolic link"):
        ev._stage_pinned_task_sif(
            str(symlink.absolute()),
            digest,
            str(tmp_path / "symlink-run"),
        )
    (tmp_path / "mismatch-run").mkdir()
    with pytest.raises(ValueError, match="digest mismatch"):
        ev._stage_pinned_task_sif(
            str(source.resolve()), "0" * 64, str(tmp_path / "mismatch-run")
        )
    assert not (tmp_path / "mismatch-run" / "pinned-image" / "task.sif").exists()


def test_task_sif_staging_rejects_source_mutation(tmp_path, monkeypatch):
    source = tmp_path / "source.sif"
    source.write_bytes(b"a" * (1024 * 1024 + 32))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    run_root = tmp_path / "mutation-run"
    run_root.mkdir()
    original_read = ev.os.read
    mutated = False

    def mutate_after_first_read(fd, size):
        nonlocal mutated
        chunk = original_read(fd, size)
        if chunk and not mutated:
            mutated = True
            with source.open("ab") as fh:
                fh.write(b"changed")
        return chunk

    monkeypatch.setattr(ev.os, "read", mutate_after_first_read)
    with pytest.raises(ValueError, match="changed while it was staged"):
        ev._stage_pinned_task_sif(str(source.resolve()), digest, str(run_root))
    assert mutated is True


def test_post_harbor_sif_mutation_resets_score_acceptance(tmp_path, monkeypatch):
    task = _write_minimal_task(tmp_path)
    source_sif = tmp_path / "source-task.sif"
    source_sif.write_bytes(b"pinned-source-sif")
    digest = hashlib.sha256(source_sif.read_bytes()).hexdigest()
    bin_dir = tmp_path / "bin-sif-mutation"
    bin_dir.mkdir()
    fake = bin_dir / "harbor"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "out = pathlib.Path(args[args.index('-o') + 1])\n"
        "run = out / 'clean-run'\n"
        "run.mkdir(parents=True)\n"
        "trial = 'fixture-trial'\n"
        "(run / 'result.json').write_text(json.dumps({\n"
        "  'n_total_trials': 1,\n"
        "  'stats': {\n"
        "    'n_completed_trials': 1, 'n_errored_trials': 0,\n"
        "    'n_running_trials': 0, 'n_pending_trials': 0,\n"
        "    'n_cancelled_trials': 0, 'n_retries': 0,\n"
        "    'evals': {'codex__fixture': {\n"
        "      'n_trials': 1, 'n_errors': 0,\n"
        "      'metrics': [{'mean': 1.0}],\n"
        "      'reward_stats': {'reward': {'1.0': [trial]}},\n"
        "      'exception_stats': {}\n"
        "    }}\n"
        "  }\n"
        "}))\n"
        "sif = out.parent / 'pinned-image' / 'task.sif'\n"
        "os.chmod(sif, 0o600)\n"
        "sif.write_bytes(b'mutated-by-fake-harbor')\n"
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-private-value")
    out = tmp_path / "sif-mutation-result.json"

    rc = ev.main([
        "--model", "gpt-test",
        "--task", str(task),
        "--out", str(out),
        "--work", str(tmp_path / "sif-mutation-work"),
        "--harness", "codex",
        "--task-sif", str(source_sif.resolve()),
        "--task-sif-sha256", digest,
        "--harbor-timeout", "10",
    ])
    result = json.loads(out.read_text())

    assert rc == 1
    assert result["reward"] == 0.0
    assert result["solved"] is False
    assert result["agent_completed"] is False
    assert result["harness"]["score_accepted"] is False
    assert result["harness"]["stop_reason"] == "error"
    assert "staged task SIF" in result["error"]
    assert "task_sif_post_sha256" not in result


def test_fake_harbor_command_boundary_uses_allowlist_and_redacts_trace(
    tmp_path, monkeypatch, capsys
):
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
        "  'n_total_trials': 1,\n"
        "  'stats': {\n"
        "    'n_completed_trials': 1, 'n_errored_trials': 0,\n"
        "    'n_running_trials': 0, 'n_pending_trials': 0,\n"
        "    'n_cancelled_trials': 0, 'n_retries': 0,\n"
        "    'evals': {'vendor__fake': {\n"
        "      'n_trials': 1, 'n_errors': 0,\n"
        "      'metrics': [{'mean': 1.0}],\n"
        "      'reward_stats': {'reward': {'1.0': ['fixture-trial']}},\n"
        "      'exception_stats': {}\n"
        "    }}\n"
        "  }\n"
        "}))\n"
        "secret = os.environ['OPENAI_API_KEY']\n"
        "agent = trial / 'agent'\n"
        "agent.mkdir()\n"
        "(agent / 'trajectory.json').write_text(json.dumps({\n"
        "  'agent': {'version': secret, 'model_name': 'model:' + secret},\n"
        "  'steps': [{'llm_call_count': 1, 'tool_calls': [\n"
        "    {'arguments': {'nested_secret': secret}}\n"
        "  ], 'nested': {'secret': secret}}],\n"
        "  'final_metrics': {\n"
        "    'total_prompt_tokens': 1, 'total_completion_tokens': 2,\n"
        "    'total_cached_tokens': 0, 'total_cost_usd': 0.01,\n"
        "    'total_steps': 1,\n"
        "    'extra': {'total_tokens': 3, 'nested': {'secret': secret}}\n"
        "  },\n"
        "  'nested': {'secret': secret}\n"
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
    captured = capsys.readouterr()
    result = json.loads(out.read_text())
    child_args = json.loads(args_path.read_text())
    child_env = json.loads(env_path.read_text())
    trace_path = Path(result["harness"]["trace_path"])
    trace = trace_path.read_text()
    command_path = trace_path.with_name("harbor_cmd.txt")

    assert rc == 0
    assert result["reward"] == 1.0
    assert result["solved"] is True
    assert result["harness"]["harbor_executable"] == str(fake.resolve())
    assert result["plan"]["command"][0] == str(fake.resolve())
    assert result["patch_applied"] is None
    # A fabricated result exercises parsing, not verifier semantics or replay.
    assert result["false_accept_check"]["semantic_false_accept"] is None
    assert child_env["OPENAI_API_KEY"] == credential
    assert not set(ambient_credentials).intersection(child_env)
    assert Path(child_env["HOME"]).is_relative_to(tmp_path / "work")
    assert stat.S_IMODE(Path(child_env["HOME"]).stat().st_mode) == 0o700
    assert stat.S_IMODE(Path(child_env["HOME"]).parent.stat().st_mode) == 0o700
    assert credential not in json.dumps(result)
    assert credential not in out.read_text()
    assert credential not in captured.out
    assert credential not in captured.err
    assert credential not in json.dumps(child_args)
    assert credential not in trace
    assert "<redacted:OPENAI_API_KEY>" in trace
    assert result["harness"]["version"] == "<redacted:OPENAI_API_KEY>"
    assert result["harness"]["trajectory_model"] == (
        "model:<redacted:OPENAI_API_KEY>"
    )
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


def test_auth_path_from_malicious_trajectory_is_redacted_everywhere(
    tmp_path, monkeypatch, capsys
):
    task = _write_minimal_task(tmp_path)
    bin_dir = tmp_path / "bin-auth-path"
    bin_dir.mkdir()
    fake = bin_dir / "harbor"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "out = pathlib.Path(args[args.index('-o') + 1])\n"
        "run = out / 'clean-run'\n"
        "agent = run / 'agent'\n"
        "agent.mkdir(parents=True)\n"
        "trial = 'fixture-trial'\n"
        "(run / 'result.json').write_text(json.dumps({\n"
        "  'n_total_trials': 1,\n"
        "  'stats': {\n"
        "    'n_completed_trials': 1, 'n_errored_trials': 0,\n"
        "    'n_running_trials': 0, 'n_pending_trials': 0,\n"
        "    'n_cancelled_trials': 0, 'n_retries': 0,\n"
        "    'evals': {'codex__fixture': {\n"
        "      'n_trials': 1, 'n_errors': 0,\n"
        "      'metrics': [{'mean': 1.0}],\n"
        "      'reward_stats': {'reward': {'1.0': [trial]}},\n"
        "      'exception_stats': {}\n"
        "    }}\n"
        "  }\n"
        "}))\n"
        "secret = os.environ['CODEX_AUTH_JSON_PATH']\n"
        "(agent / 'trajectory.json').write_text(json.dumps({\n"
        "  'agent': {'version': secret, 'model_name': 'model:' + secret},\n"
        "  'steps': [{'llm_call_count': 1, 'tool_calls': [\n"
        "    {'arguments': {'secret': secret}}\n"
        "  ], 'nested': {secret: {'secret': secret}}}],\n"
        "  'final_metrics': {\n"
        "    'total_prompt_tokens': secret, 'total_completion_tokens': 2,\n"
        "    'total_cached_tokens': 0, 'total_cost_usd': 0.01,\n"
        "    'total_steps': 1,\n"
        "    'extra': {'total_tokens': secret, 'nested': {'secret': secret}}\n"
        "  },\n"
        "  'nested': {secret: {'secret': secret}}\n"
        "}))\n"
        "print(secret)\n"
    )
    fake.chmod(0o755)
    auth_path = str(tmp_path / "node-local-private-auth.json")
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_AUTH_JSON_PATH", auth_path)
    out = tmp_path / "auth-path-result.json"

    rc = ev.main([
        "--model", "gpt-test",
        "--task", str(task),
        "--out", str(out),
        "--work", str(tmp_path / "auth-path-work"),
        "--harness", "codex",
        "--harbor-timeout", "10",
    ])
    captured = capsys.readouterr()
    result = json.loads(out.read_text())
    trace = Path(result["harness"]["trace_path"]).read_text()
    command = Path(result["harness"]["trace_path"]).with_name("harbor_cmd.txt").read_text()

    assert rc == 0
    assert result["reward"] == 1.0
    assert result["agent_completed"] is True
    assert auth_path not in out.read_text()
    assert auth_path not in captured.out
    assert auth_path not in captured.err
    assert auth_path not in trace
    assert auth_path not in command
    assert result["harness"]["version"] == "<redacted:CODEX_AUTH_JSON_PATH>"
    assert result["harness"]["trajectory_model"] == (
        "model:<redacted:CODEX_AUTH_JSON_PATH>"
    )
    assert "prompt_tokens" not in result["harness"]
    assert "total_tokens" not in result["harness"]


def test_agent_error_aggregate_is_diagnostic_not_clean_score(tmp_path, monkeypatch):
    task = _write_minimal_task(tmp_path)
    bin_dir = tmp_path / "bin-agent-error"
    bin_dir.mkdir()
    fake = bin_dir / "harbor"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "out = pathlib.Path(args[args.index('-o') + 1])\n"
        "run = out / 'errored-run'\n"
        "run.mkdir(parents=True)\n"
        "trial = 'task__errored'\n"
        "(run / 'result.json').write_text(json.dumps({\n"
        "  'n_total_trials': 1,\n"
        "  'stats': {\n"
        "    'n_completed_trials': 1, 'n_errored_trials': 1,\n"
        "    'n_running_trials': 0, 'n_pending_trials': 0,\n"
        "    'n_cancelled_trials': 0, 'n_retries': 0,\n"
        "    'evals': {'claude-code__fixture': {\n"
        "      'n_trials': 1, 'n_errors': 1,\n"
        "      'metrics': [{'mean': 0.0}],\n"
        "      'reward_stats': {'reward': {'0.0': [trial]}},\n"
        "      'exception_stats': {'NonZeroAgentExitCodeError': [trial]}\n"
        "    }}\n"
        "  }\n"
        "}))\n"
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-private-value")
    out = tmp_path / "agent-error-result.json"

    rc = ev.main([
        "--model", "gpt-test",
        "--task", str(task),
        "--out", str(out),
        "--work", str(tmp_path / "agent-error-work"),
        "--harness", "codex",
        "--harbor-timeout", "10",
    ])
    result = json.loads(out.read_text())

    assert ev._read_harbor_reward(result["jobs_dir"]) is None
    assert rc == 1
    assert result["reward"] == 0.0
    assert result["solved"] is False
    assert result["agent_completed"] is False
    assert result["error"] == "harbor aggregate reports agent/trial errors"
    assert result["harness"]["stop_reason"] == "scored_agent_error"
    assert result["harness"]["score_accepted"] is False
    assert result["harness"]["harbor_diagnostic_reward"] == 0.0
    assert result["harness"]["aggregate_status"]["n_errored_trials"] == 1
    assert result["harness"]["aggregate_status"]["eval_n_errors"] == 1


def _write_nonzero_harbor(path: Path, exit_code: int) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "out = pathlib.Path(args[args.index('-o') + 1])\n"
        "run = out / 'fresh-run'\n"
        "run.mkdir(parents=True, exist_ok=True)\n"
        "(run / 'result.json').write_text(json.dumps({\n"
        "  'n_total_trials': 1,\n"
        "  'stats': {\n"
        "    'n_completed_trials': 1, 'n_errored_trials': 0,\n"
        "    'n_running_trials': 0, 'n_pending_trials': 0,\n"
        "    'n_cancelled_trials': 0, 'n_retries': 0,\n"
        "    'evals': {'fixture__adhoc': {\n"
        "      'n_trials': 1, 'n_errors': 0,\n"
        "      'metrics': [{'mean': 1.0}],\n"
        "      'reward_stats': {'reward': {'1.0': ['fixture-trial']}},\n"
        "      'exception_stats': {}\n"
        "    }}\n"
        "  }\n"
        "}))\n"
        f"raise SystemExit({exit_code})\n"
    )
    path.chmod(0o755)


def test_vendor_nonzero_harbor_exit_rejects_fresh_aggregate(tmp_path, monkeypatch):
    task = _write_minimal_task(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "harbor"
    _write_nonzero_harbor(fake, 7)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-private-value")
    out = tmp_path / "vendor-result.json"

    rc = ev.main([
        "--model", "gpt-test",
        "--task", str(task),
        "--out", str(out),
        "--work", str(tmp_path / "vendor-work"),
        "--harness", "codex",
        "--harbor-timeout", "10",
    ])
    result = json.loads(out.read_text())

    # The aggregate is structurally valid, but a non-zero Harbor process status
    # is authoritative and must prevent it from becoming an accepted score.
    assert ev._read_harbor_reward(result["jobs_dir"]) == 1.0
    assert rc == 1
    assert result["reward"] == 0.0
    assert result["solved"] is False
    assert result["error"] == "harbor exited with status 7"
    assert result["agent_completed"] is False
    assert result["harness"]["harbor_returncode"] == 7
    assert result["harness"]["stop_reason"] == "error"


def test_oracle_nonzero_harbor_exit_rejects_fresh_aggregate(tmp_path, monkeypatch):
    task = _write_minimal_task(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "harbor"
    _write_nonzero_harbor(fake, 9)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    out = tmp_path / "oracle-result.json"

    rc = ev.main([
        "--model", "oracle",
        "--task", str(task),
        "--out", str(out),
        "--work", str(tmp_path / "oracle-work"),
        "--harbor-timeout", "10",
    ])
    result = json.loads(out.read_text())

    assert ev._read_harbor_reward(result["jobs_dir"]) == 1.0
    assert rc == 1
    assert result["reward"] == 0.0
    assert result["solved"] is False
    assert result["error"] == "harbor exited with status 9"
    assert result["patch_applied"] is False
    assert result["harbor_returncode"] == 9


def test_oracle_harbor_child_receives_minimal_private_environment(tmp_path, monkeypatch):
    task = _write_minimal_task(tmp_path)
    bin_dir = tmp_path / "bin-oracle-env"
    bin_dir.mkdir()
    fake = bin_dir / "harbor"
    env_path = tmp_path / "oracle-child-env.json"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "out = pathlib.Path(args[args.index('-o') + 1])\n"
        "run = out / 'clean-oracle-run'\n"
        "run.mkdir(parents=True)\n"
        "trial = 'oracle-trial'\n"
        "(run / 'result.json').write_text(json.dumps({\n"
        "  'n_total_trials': 1,\n"
        "  'stats': {\n"
        "    'n_completed_trials': 1, 'n_errored_trials': 0,\n"
        "    'n_running_trials': 0, 'n_pending_trials': 0,\n"
        "    'n_cancelled_trials': 0, 'n_retries': 0,\n"
        "    'evals': {'oracle__adhoc': {\n"
        "      'n_trials': 1, 'n_errors': 0,\n"
        "      'metrics': [{'mean': 1.0}],\n"
        "      'reward_stats': {'reward': {'1.0': [trial]}},\n"
        "      'exception_stats': {}\n"
        "    }}\n"
        "  }\n"
        "}))\n"
        f"pathlib.Path({str(env_path)!r}).write_text(json.dumps(dict(os.environ)))\n"
    )
    fake.chmod(0o755)
    ambient = {
        "OPENAI_API_KEY": "ambient-openai-value",
        "ANTHROPIC_API_KEY": "ambient-anthropic-value",
        "AWS_ACCESS_KEY_ID": "ambient-aws-value",
        "AWS_SECRET_ACCESS_KEY": "ambient-aws-secret",
        "SSH_AUTH_SOCK": "/private/ambient-ssh.sock",
        "AMDGW_" + "KEY": "ambient-amd-value",
    }
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    for name, value in ambient.items():
        monkeypatch.setenv(name, value)
    out = tmp_path / "oracle-env-result.json"

    rc = ev.main([
        "--model", "oracle",
        "--task", str(task),
        "--out", str(out),
        "--work", str(tmp_path / "oracle-env-work"),
        "--harbor-timeout", "10",
    ])
    result = json.loads(out.read_text())
    child_env = json.loads(env_path.read_text())

    assert rc == 0
    assert result["reward"] == 1.0
    assert not set(ambient).intersection(child_env)
    assert Path(child_env["HOME"]).is_relative_to(tmp_path / "oracle-env-work")
    assert stat.S_IMODE(Path(child_env["HOME"]).stat().st_mode) == 0o700
    assert stat.S_IMODE(Path(child_env["HOME"]).parent.stat().st_mode) == 0o700
    node_tmp = Path(child_env["TMPDIR"])
    assert node_tmp.parent == Path("/tmp")
    assert node_tmp.name.startswith("tdb-oracle-")
    assert len(str(node_tmp / "singularity_staging_12345678" / "hbexec.sock")) < 108
    assert child_env["TMP"] == child_env["TEMP"] == str(node_tmp)
    assert not node_tmp.exists()


def test_oracle_node_tmp_is_cleaned_when_harbor_launcher_is_missing(
    tmp_path, monkeypatch
):
    node_tmp = tmp_path / "exact-node-tmp"
    adjacent = tmp_path / "must-survive"
    adjacent.mkdir()

    def fake_mkdtemp(*, prefix, dir):
        assert prefix == "tdb-oracle-"
        assert dir == "/tmp"
        node_tmp.mkdir(mode=0o700)
        return str(node_tmp)

    monkeypatch.setattr(ev.tempfile, "mkdtemp", fake_mkdtemp)
    monkeypatch.setattr(
        ev, "_require_harbor",
        lambda: (_ for _ in ()).throw(RuntimeError("fixture launcher missing")),
    )

    with pytest.raises(RuntimeError, match="fixture launcher missing"):
        ev.run_harbor_oracle(
            str(tmp_path / "task"), str(tmp_path / "run" / "jobs"), [], 10
        )

    assert not node_tmp.exists()
    assert adjacent.is_dir()


def test_oracle_node_tmp_cleanup_failure_is_fail_closed(tmp_path, monkeypatch):
    node_tmp = tmp_path / "uncleanable-node-tmp"

    def fake_mkdtemp(*, prefix, dir):
        node_tmp.mkdir(mode=0o700)
        return str(node_tmp)

    monkeypatch.setattr(ev.tempfile, "mkdtemp", fake_mkdtemp)
    monkeypatch.setattr(ev.shutil, "rmtree", lambda path: None)
    monkeypatch.setattr(ev, "_require_harbor", lambda: "/fixture/harbor")
    monkeypatch.setattr(ev, "_run_process_group", lambda *args, **kwargs: (0, ""))

    with pytest.raises(RuntimeError, match="failed to remove private oracle"):
        ev.run_harbor_oracle(
            str(tmp_path / "task"), str(tmp_path / "run" / "jobs"), [], 10
        )

    assert node_tmp.is_dir()
