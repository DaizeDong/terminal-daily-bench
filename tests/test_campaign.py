"""Credential-free tests for sparse campaign planning and checkpointing."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from terminal_daily_bench import cli
from terminal_daily_bench import campaign as campaign_module
from terminal_daily_bench.adapters import create_adapter
from terminal_daily_bench.campaign import (
    BLOCKED,
    FAILED,
    NOT_RUN,
    SUCCESS,
    CampaignError,
    plan_campaign,
    run_campaign,
)


def _task(root: Path, name: str = "td-campaign-fixture") -> Path:
    task = root / name
    (task / "tests").mkdir(parents=True)
    (task / "environment").mkdir()
    (task / "tests" / "test.sh").write_text("#!/bin/sh\nexit 0\n")
    (task / "environment" / "Dockerfile").write_text("FROM scratch\n")
    (task / "instruction.md").write_text("Repair the fixture.\n")
    (task / "task.toml").write_text(
        "[task]\nname = 'campaign-fixture'\n"
        "[environment]\ndocker_image = 'environment/Dockerfile'\n"
    )
    return task


def _write_spec(
    path: Path,
    task: Path,
    *,
    models: list[dict],
    agents: list[dict],
    execution: dict | None = None,
    seeds: list[int | None] | None = None,
) -> Path:
    path.write_text(json.dumps({
        "schema_version": "tdb-campaign/v1",
        "campaign_id": "unit-campaign",
        "models": models,
        "agents": agents,
        "tasks": [{"id": "fixture-task", "path": str(task)}],
        "seeds": [None] if seeds is None else seeds,
        "execution": execution or {},
    }))
    return path


def _canonical_digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _model(
    profile_id: str,
    protocol: str = "openai-chat-completions",
    *,
    provider: str = "fixture-provider",
    cost: float | None = 0.1,
) -> dict:
    value = {
        "id": profile_id,
        "provider": provider,
        "model": f"openai/{profile_id}",
        "build": "immutable-test-build",
        "protocols": [protocol],
        "base_url": "https://gateway.example/v1",
    }
    if cost is not None:
        value["estimated_cost_usd"] = cost
    return value


def _clean_result(cell, reward: float = 0.0) -> dict:
    common = {
        "model": cell.resolved_model,
        "task": cell.task.path.name,
        "model_protocol": cell.protocol,
        "seed": cell.seed,
        "dry_run": False,
        "error": None,
        "reward": reward,
        "solved": reward >= 0.999,
        "harness": {"harbor_result_sha256": "a" * 64},
    }
    if cell.agent.integration_path == "harbor-agent":
        return {
            **common,
            "agent_completed": True,
            "harness": {
                **common["harness"],
                "score_accepted": True,
                "stop_reason": "completed",
            },
        }
    return {
        **common,
        "false_accept_check": {
            "protected_tests_relaid_by_harbor": True,
            "model_is_judge": False,
        },
    }


def test_sparse_plan_is_protocol_aware_stable_and_base_url_secret_safe(tmp_path):
    task = _task(tmp_path / "source")
    models = [
        _model("chat", "openai-chat-completions"),
        {
            **_model("responses", "openai-responses"),
            "model_by_harness": {"codex": "gpt-test-responses"},
        },
    ]
    agents = [
        {"id": "one-shot", "harness": "single_shot"},
        {"id": "codex", "harness": "codex"},
        {"id": "claude", "harness": "claude-code"},
    ]
    first = plan_campaign(_write_spec(tmp_path / "first.json", task, models=models, agents=agents))

    copied = _task(tmp_path / "copy")
    second = plan_campaign(_write_spec(tmp_path / "second.json", copied, models=models, agents=agents))

    assert len(first.manifest["cells"]) == 2
    assert len(first.manifest["excluded_cells"]) == 4
    assert {
        cell["protocol"] for cell in first.manifest["cells"]
    } == {"openai-chat-completions", "openai-responses"}
    assert {
        cell["classification"] for cell in first.manifest["excluded_cells"]
    } == {"SKIPPED_INCOMPATIBLE_PROTOCOL"}
    assert first.manifest["campaign_fingerprint"] == second.manifest["campaign_fingerprint"]
    assert [c["cell_id"] for c in first.manifest["cells"]] == [
        c["cell_id"] for c in second.manifest["cells"]
    ]
    persisted = json.dumps(first.manifest)
    assert "gateway.example" not in persisted
    assert "base_url_sha256" in persisted


def test_gateway_catalog_imports_capabilities_with_explicit_anthropic_allowlist(tmp_path):
    task = _task(tmp_path)
    entries = [
        {"id": "looks-like-claude", "capabilities": {"chat": True, "responses": False}},
        {"id": "response-model", "capabilities": {"chat": False, "responses": True}},
        {"id": "all-openai", "capabilities": {"chat": True, "responses": True}},
        {"id": "no-supported-api", "capabilities": {"chat": False, "responses": False}},
    ]
    catalog = tmp_path / "models.json"
    catalog.write_text(json.dumps({"object": "list", "data": entries}))
    spec = tmp_path / "campaign.json"
    spec.write_text(json.dumps({
        "schema_version": "tdb-campaign/v1",
        "campaign_id": "catalog-campaign",
        "model_catalog": {
            "path": str(catalog),
            "sha256": _canonical_digest(entries),
            "provider": "gateway",
            "base_url": "https://gateway.example/v1",
            "anthropic_messages_allowlist": ["response-model"],
        },
        "agents": [
            {"id": "one-shot", "harness": "single_shot"},
            {"id": "codex", "harness": "codex"},
            {"id": "claude", "harness": "claude-code"},
        ],
        "tasks": [{"id": "fixture-task", "path": str(task)}],
    }))

    plan = plan_campaign(spec)
    eligible = {
        (cell["resolved_model"], cell["agent_profile_id"])
        for cell in plan.manifest["cells"]
    }

    assert ("looks-like-claude", "one-shot") in eligible
    assert ("looks-like-claude", "claude") not in eligible
    assert ("response-model", "codex") in eligible
    assert ("response-model", "claude") in eligible
    assert ("all-openai", "one-shot") in eligible
    assert ("all-openai", "codex") in eligible
    assert not any(model == "no-supported-api" for model, _ in eligible)
    assert plan.manifest["model_catalogs"][0]["models_sha256"] == _canonical_digest(entries)
    assert "models.json" not in json.dumps(plan.manifest)


def test_frozen_catalog_wrapper_requires_credential_and_routing_safety_markers(tmp_path):
    task = _task(tmp_path)
    entries = [{"id": "safe-model", "capabilities": {"chat": True, "responses": False}}]
    digest = _canonical_digest(entries)
    wrapper = {
        "schema": "terminal-daily-gateway-model-catalog-v1",
        "http_status": 200,
        "models": entries,
        "models_sha256": digest,
        "model_count": 1,
        "chat_count": 1,
        "responses_count": 0,
        "credential_values_persisted": False,
        "routing_persisted": False,
    }
    catalog = tmp_path / "frozen.json"
    catalog.write_text(json.dumps(wrapper))
    spec = tmp_path / "campaign.json"
    spec.write_text(json.dumps({
        "schema_version": "tdb-campaign/v1",
        "campaign_id": "frozen-catalog",
        "model_catalog": {
            "path": str(catalog),
            "sha256": digest,
            "provider": "gateway",
        },
        "agents": [{"id": "one-shot", "harness": "single_shot"}],
        "tasks": [{"id": "fixture-task", "path": str(task)}],
    }))

    assert len(plan_campaign(spec).manifest["cells"]) == 1

    wrapper["routing_persisted"] = True
    catalog.write_text(json.dumps(wrapper))
    with pytest.raises(CampaignError, match="routing_persisted=false"):
        plan_campaign(spec)


@pytest.mark.skipif(
    not os.environ.get("TDB_LIVE_MODEL_CATALOG"),
    reason="operator-only frozen gateway catalog is not configured",
)
def test_operator_frozen_gateway_catalog_plans_expected_sparse_cells(tmp_path):
    """Planner-only check; never contacts the gateway or reads a credential."""
    task = _task(tmp_path)
    spec = tmp_path / "campaign.json"
    spec.write_text(json.dumps({
        "schema_version": "tdb-campaign/v1",
        "campaign_id": "operator-catalog-check",
        "model_catalog": {
            "path": os.environ["TDB_LIVE_MODEL_CATALOG"],
            "sha256": os.environ["TDB_LIVE_MODEL_CATALOG_SHA256"],
            "provider": "gateway",
            "base_url": "https://gateway.invalid/v1",
        },
        "agents": [
            {"id": "one-shot", "harness": "single_shot"},
            {"id": "codex", "harness": "codex"},
        ],
        "tasks": [{"id": "fixture-task", "path": str(task)}],
    }))

    plan = plan_campaign(spec)

    assert len(plan.definition.models) == 73
    assert len(plan.manifest["cells"]) == 65 + 35
    source = plan.manifest["model_catalogs"][0]
    assert source["capability_counts"]["chat"] == 65
    assert source["capability_counts"]["responses"] == 35


def test_dry_run_freezes_manifest_without_invoking_runner(tmp_path):
    task = _task(tmp_path)
    spec = _write_spec(
        tmp_path / "campaign.json",
        task,
        models=[_model("chat")],
        agents=[
            {"id": "one-shot", "harness": "single_shot"},
            {"id": "codex", "harness": "codex"},
        ],
    )
    called = False

    def forbidden(*_args):
        nonlocal called
        called = True
        raise AssertionError("dry-run invoked a cell")

    rc, summary = run_campaign(spec, tmp_path / "state", dry_run=True, runner=forbidden)
    checkpoint = json.loads((tmp_path / "state" / "checkpoint.json").read_text())

    assert rc == 0
    assert called is False
    assert summary["eligible_cells"] == 1
    assert summary["excluded_cells"] == 1
    assert {cell["status"] for cell in checkpoint["cells"].values()} == {NOT_RUN, BLOCKED}
    assert not list((tmp_path / "state" / "attempts").glob("**/*.json"))


def test_budget_blocks_then_resume_runs_only_remaining_cell(tmp_path):
    task = _task(tmp_path)
    spec = _write_spec(
        tmp_path / "campaign.json",
        task,
        models=[_model("first", cost=0.6), _model("second", cost=0.6)],
        agents=[{"id": "one-shot", "harness": "single_shot"}],
        execution={"max_workers": 2},
    )
    calls: list[str] = []

    def runner(cell, output, *_args):
        calls.append(cell.cell_id)
        output.write_text(json.dumps(_clean_result(cell)))
        return 0

    rc, summary = run_campaign(
        spec, tmp_path / "state", budget_usd=0.6, runner=runner
    )
    checkpoint = json.loads((tmp_path / "state" / "checkpoint.json").read_text())
    assert rc == 1
    assert len(calls) == 1
    assert summary["status_counts"][SUCCESS] == 1
    assert summary["status_counts"][BLOCKED] == 1
    assert "BLOCKED_BUDGET" in {
        value["classification"] for value in checkpoint["cells"].values()
    }

    rc, summary = run_campaign(
        spec,
        tmp_path / "state",
        resume=True,
        retry_blocked=True,
        budget_usd=2.0,
        runner=runner,
    )
    rows = [json.loads(line) for line in (tmp_path / "state" / "results.jsonl").read_text().splitlines()]
    assert rc == 0
    assert len(calls) == 2
    assert summary["status_counts"][SUCCESS] == 2
    assert {row["matrix_column_id"] for row in rows} == {
        "first::one-shot", "second::one-shot"
    }


def test_failed_cell_requires_explicit_retry_and_preserves_attempt_history(tmp_path):
    task = _task(tmp_path)
    spec = _write_spec(
        tmp_path / "campaign.json",
        task,
        models=[_model("chat")],
        agents=[{"id": "one-shot", "harness": "single_shot"}],
    )
    calls = 0

    def runner(cell, output, *_args):
        nonlocal calls
        calls += 1
        if calls == 1:
            output.write_text(json.dumps({
                **_clean_result(cell),
                "error": "no reward parsed (aggregate authority rejected)",
                "reward": 0.0,
            }))
            return 1
        output.write_text(json.dumps(_clean_result(cell, reward=1.0)))
        return 0

    rc, summary = run_campaign(spec, tmp_path / "state", runner=runner)
    assert rc == 1
    assert summary["status_counts"][FAILED] == 1
    assert calls == 1

    rc, _ = run_campaign(spec, tmp_path / "state", resume=True, runner=runner)
    assert rc == 1
    assert calls == 1

    rc, summary = run_campaign(
        spec, tmp_path / "state", resume=True, retry_failed=True, runner=runner
    )
    checkpoint = json.loads((tmp_path / "state" / "checkpoint.json").read_text())
    only = next(iter(checkpoint["cells"].values()))
    assert rc == 0
    assert summary["status_counts"][SUCCESS] == 1
    assert calls == 2
    assert [attempt["classification"] for attempt in only["attempts"]] == [
        "FAILED_AGENT_ERROR", "CLEAN_SCORED_SOLVED"
    ]


@pytest.mark.parametrize(
    ("classification", "expected_status"),
    [
        ("BLOCKED_BRIDGE_STARTUP", BLOCKED),
        ("BLOCKED_BRIDGE_UNREACHABLE", BLOCKED),
        ("BLOCKED_NO_NETWORK_NAMESPACE", BLOCKED),
        ("BLOCKED_SHARED_RATE_LIMIT", BLOCKED),
        ("FAILED_BRIDGE_AUTH", FAILED),
        ("FAILED_BRIDGE_INTERNAL", FAILED),
        ("FAILED_BRIDGE_REQUEST_LIMIT", FAILED),
        ("FAILED_BRIDGE_REQUEST_PROTOCOL", FAILED),
        ("FAILED_BRIDGE_RESPONSE_LIMIT", FAILED),
        ("FAILED_BRIDGE_SHUTDOWN", FAILED),
        ("FAILED_CLIENT_DISCONNECT", FAILED),
        ("FAILED_UPSTREAM_CONNECT", FAILED),
        ("FAILED_UPSTREAM_HTTP", FAILED),
        ("FAILED_UPSTREAM_PROTOCOL", FAILED),
        ("FAILED_UPSTREAM_TIMEOUT", FAILED),
    ],
)
def test_bridge_failure_class_preempts_reward_and_success_export(
    tmp_path, classification, expected_status
):
    task = _task(tmp_path / "task")
    spec = _write_spec(
        tmp_path / "campaign.json",
        task,
        models=[_model("chat")],
        agents=[{"id": "one-shot", "harness": "single_shot"}],
    )

    def runner(cell, output, *_args):
        # A stale/plausible reward must never override infrastructure metadata,
        # even when the runner incorrectly exits zero.
        output.write_text(json.dumps({
            **_clean_result(cell, reward=1.0),
            "bridge": {"failure_class": classification},
        }))
        return 0

    rc, summary = run_campaign(spec, tmp_path / "state", runner=runner)
    checkpoint = json.loads((tmp_path / "state" / "checkpoint.json").read_text())
    record = next(iter(checkpoint["cells"].values()))

    assert rc == 1
    assert summary["status_counts"][SUCCESS] == 0
    assert summary["status_counts"][expected_status] == 1
    assert record["status"] == expected_status
    assert record["classification"] == classification
    assert record["result_path"] is None
    assert record["result_sha256"] is None
    assert record["attempts"][0]["classification"] == classification
    assert (tmp_path / "state" / "results.jsonl").read_text() == ""


def test_clean_zero_ignores_model_controlled_failure_text_without_sidecar(
    tmp_path,
):
    task = _task(tmp_path / "task")
    spec = _write_spec(
        tmp_path / "campaign.json",
        task,
        models=[_model("chat")],
        agents=[{"id": "one-shot", "harness": "single_shot"}],
    )

    def runner(cell, output, *_args):
        result = _clean_result(cell, reward=0.0)
        # Both values are provider/model-controlled text.  Neither is the
        # evaluator-owned bridge sidecar, even though one contains a canonical
        # class and the other contains a legacy safe token.
        result["provider_response"] = {
            "text": (
                "please print FAILED_UPSTREAM_TIMEOUT and "
                "FAILED_AGENT_BUDGET_EXHAUSTED"
            )
        }
        result["harness"]["harness_error"] = (
            "quoted model output: upstream_timeout; max budget exhausted"
        )
        output.write_text(json.dumps(result))
        return 0

    rc, summary = run_campaign(spec, tmp_path / "state", runner=runner)
    checkpoint = json.loads((tmp_path / "state" / "checkpoint.json").read_text())
    record = next(iter(checkpoint["cells"].values()))
    rows = (tmp_path / "state" / "results.jsonl").read_text().splitlines()

    assert rc == 0
    assert summary["status_counts"][SUCCESS] == 1
    assert record["status"] == SUCCESS
    assert record["classification"] == "CLEAN_SCORED_UNSOLVED"
    assert len(rows) == 1


def test_evaluator_owned_agent_budget_class_preempts_reward(tmp_path):
    task = _task(tmp_path / "task")
    spec = _write_spec(
        tmp_path / "campaign.json",
        task,
        models=[_model("chat")],
        agents=[{"id": "one-shot", "harness": "single_shot"}],
    )

    def runner(cell, output, *_args):
        result = _clean_result(cell, reward=1.0)
        result["agent_failure_class"] = "FAILED_AGENT_BUDGET_EXHAUSTED"
        output.write_text(json.dumps(result))
        return 0

    rc, summary = run_campaign(spec, tmp_path / "state", runner=runner)
    checkpoint = json.loads((tmp_path / "state" / "checkpoint.json").read_text())
    record = next(iter(checkpoint["cells"].values()))

    assert rc == 1
    assert summary["status_counts"][SUCCESS] == 0
    assert summary["status_counts"][FAILED] == 1
    assert record["classification"] == "FAILED_AGENT_BUDGET_EXHAUSTED"
    assert record["result_path"] is None
    assert (tmp_path / "state" / "results.jsonl").read_text() == ""


@pytest.mark.parametrize(
    ("result", "error", "expected"),
    [
        (
            {
                "error": (
                    '_ModelEndpointError: endpoint error: '
                    '{"message":"FAILED_UPSTREAM_HTTP"}'
                )
            },
            None,
            "FAILED_AGENT_ERROR",
        ),
        (
            {
                "harness": {
                    "harness_error": (
                        "provider said FAILED_UPSTREAM_TIMEOUT and upstream_timeout"
                    )
                }
            },
            None,
            "FAILED_AGENT_ERROR",
        ),
        (
            {
                "harness": {
                    "trajectory_model": "FAILED_BRIDGE_AUTH",
                    "bridge": {"failure_class": "FAILED_UPSTREAM_HTTP"},
                }
            },
            None,
            "FAILED_AGENT_ERROR",
        ),
        (None, "FAILED_UPSTREAM_PROTOCOL", "FAILED_AGENT_ERROR"),
        (
            {"failure_class": "FAILED_UPSTREAM_CONNECT"},
            None,
            "FAILED_AGENT_ERROR",
        ),
        (
            {
                "error": (
                    "credential unset; request timed out; staged task SIF digest "
                    "changed; aggregate authority rejected"
                )
            },
            None,
            "FAILED_AGENT_ERROR",
        ),
    ],
)
def test_nonzero_text_and_legacy_fields_have_no_infrastructure_authority(
    result, error, expected
):
    status, classification, _ = campaign_module._failure_outcome(
        SimpleNamespace(), 1, result, error
    )

    assert status == FAILED
    assert classification == expected


@pytest.mark.parametrize(
    "result",
    [
        {"bridge": {"failure_class": "FAILED_UPSTREAM_HTTP"}},
    ],
)
def test_bridge_namespaced_failure_metadata_is_whitelisted(result):
    status, classification, _ = campaign_module._failure_outcome(
        SimpleNamespace(), 1, result, None
    )

    assert status == FAILED
    assert classification == "FAILED_UPSTREAM_HTTP"


@pytest.mark.parametrize(
    "result",
    [
        {"harness": {"failure_class": "FAILED_UPSTREAM_HTTP"}},
        {"harness": {"bridge": {"failure_class": "FAILED_UPSTREAM_HTTP"}}},
        {"bridge": {"failure_classes": {"FAILED_UPSTREAM_HTTP": 2}}},
        {"bridge": {"classification": "FAILED_UPSTREAM_HTTP"}},
        {"infrastructure_failure_class": "FAILED_UPSTREAM_HTTP"},
    ],
)
def test_only_singular_top_level_bridge_machine_field_is_authoritative(result):
    status, classification, _ = campaign_module._failure_outcome(
        SimpleNamespace(), 1, result, None
    )

    assert status == FAILED
    assert classification == "FAILED_AGENT_ERROR"


@pytest.mark.parametrize(
    ("classification", "expected_status"),
    [
        ("SKIPPED_UNSUPPORTED_AUTH", BLOCKED),
        ("FAILED_TIMEOUT", FAILED),
        ("FAILED_SIF_DRIFT", FAILED),
        ("FAILED_AGGREGATE_AUTHORITY", FAILED),
        ("FAILED_AGENT_SETUP", FAILED),
        ("FAILED_HARBOR", FAILED),
    ],
)
def test_evaluator_machine_failure_class_is_exact_authority(
    classification, expected_status
):
    status, actual, _ = campaign_module._failure_outcome(
        SimpleNamespace(),
        1,
        {
            "error": "model-controlled text must not matter",
            "evaluator_failure_class": classification,
        },
        None,
    )

    assert status == expected_status
    assert actual == classification


def test_quality_denominator_contains_only_successful_campaign_cells(tmp_path):
    task = _task(tmp_path / "task")
    spec = _write_spec(
        tmp_path / "campaign.json",
        task,
        models=[_model("clean"), _model("infrastructure")],
        agents=[{"id": "one-shot", "harness": "single_shot"}],
    )

    def runner(cell, output, *_args):
        result = _clean_result(cell, reward=0.0)
        if cell.model.profile_id == "infrastructure":
            # A claimed solve demonstrates that filtering is status-based, not
            # an accidental consequence of reward being zero.
            result.update({"reward": 1.0, "solved": True})
            result["bridge"] = {"failure_class": "FAILED_UPSTREAM_CONNECT"}
        output.write_text(json.dumps(result))
        return 0

    rc, summary = run_campaign(spec, tmp_path / "state", runner=runner)
    exported = tmp_path / "state" / "results.jsonl"
    rows = [json.loads(line) for line in exported.read_text().splitlines()]
    tasks, columns, matrix = cli._load_matrix(str(exported))

    assert rc == 1
    assert summary["status_counts"][SUCCESS] == 1
    assert summary["status_counts"][FAILED] == 1
    assert len(rows) == 1
    assert rows[0]["model_profile_id"] == "clean"
    assert tasks == ["fixture-task"]
    assert columns == ["clean::one-shot"]
    assert matrix == [[0]]


def test_resume_rejects_tampered_success_result(tmp_path):
    task = _task(tmp_path)
    spec = _write_spec(
        tmp_path / "campaign.json",
        task,
        models=[_model("chat")],
        agents=[{"id": "one-shot", "harness": "single_shot"}],
    )

    def runner(cell, output, *_args):
        output.write_text(json.dumps(_clean_result(cell)))
        return 0

    assert run_campaign(spec, tmp_path / "state", runner=runner)[0] == 0
    checkpoint = json.loads((tmp_path / "state" / "checkpoint.json").read_text())
    result = tmp_path / "state" / next(iter(checkpoint["cells"].values()))["result_path"]
    result.write_text("{}")

    with pytest.raises(CampaignError, match="digest changed"):
        run_campaign(spec, tmp_path / "state", resume=True, runner=runner)


def test_provider_concurrency_limit_is_enforced(tmp_path):
    task = _task(tmp_path)
    spec = _write_spec(
        tmp_path / "campaign.json",
        task,
        models=[_model(f"model-{index}", provider="shared") for index in range(3)],
        agents=[{"id": "one-shot", "harness": "single_shot"}],
        execution={"max_workers": 3, "provider_concurrency": {"shared": 1}},
    )
    active = 0
    maximum = 0
    guard = threading.Lock()

    def runner(cell, output, *_args):
        nonlocal active, maximum
        with guard:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.03)
        output.write_text(json.dumps(_clean_result(cell)))
        with guard:
            active -= 1
        return 0

    rc, summary = run_campaign(spec, tmp_path / "state", runner=runner)
    assert rc == 0
    assert summary["status_counts"][SUCCESS] == 3
    assert maximum == 1


def test_default_runner_uses_negotiated_protocol_endpoint_without_credentials(
    tmp_path, monkeypatch
):
    task = _task(tmp_path)
    model = _model("dual", "openai-chat-completions")
    model["protocols"] = ["openai-chat-completions", "openai-responses"]
    model["base_url_by_protocol"] = {
        "openai-chat-completions": "https://chat.example/v1",
        "openai-responses": "https://responses.example/v1",
    }
    spec = _write_spec(
        tmp_path / "campaign.json",
        task,
        models=[model],
        agents=[
            {"id": "one-shot", "harness": "single_shot"},
            {"id": "codex", "harness": "codex"},
        ],
        execution={"max_workers": 1},
    )
    commands: list[list[str]] = []

    def fake_subprocess(command, **kwargs):
        commands.append(command)
        output = Path(command[command.index("--out") + 1])
        harness = command[command.index("--harness") + 1]
        protocol = command[command.index("--model-protocol") + 1]
        result = {
            "model": command[command.index("--model") + 1],
            "task": task.name,
            "model_protocol": protocol,
            "seed": None,
            "dry_run": False,
            "error": None,
            "reward": 0.0,
            "harness": {"harbor_result_sha256": "b" * 64},
        }
        if harness == "codex":
            result.update({"agent_completed": True})
            result["harness"]["score_accepted"] = True
        else:
            result["false_accept_check"] = {
                "protected_tests_relaid_by_harbor": True,
                "model_is_judge": False,
            }
        output.write_text(json.dumps(result))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(campaign_module.subprocess, "run", fake_subprocess)
    rc, _ = run_campaign(spec, tmp_path / "state")

    assert rc == 0
    by_protocol = {
        command[command.index("--model-protocol") + 1]: command
        for command in commands
    }
    assert by_protocol["openai-chat-completions"][
        by_protocol["openai-chat-completions"].index("--harness-base-url") + 1
    ] == "https://chat.example/v1"
    assert by_protocol["openai-responses"][
        by_protocol["openai-responses"].index("--harness-base-url") + 1
    ] == "https://responses.example/v1"
    assert "API_KEY" not in json.dumps(commands)


def test_terminus2_adapter_maps_protocol_and_never_needs_key_for_dry_plan():
    adapter = create_adapter("terminus-2")
    spec = adapter.harbor_run_spec(
        "openai/gpt-test",
        base_url="https://gateway.example/v1",
        protocol="openai-responses",
        environ={},
        require_credentials=False,
    )

    assert spec.agent == "terminus-2"
    assert spec.protocol == "openai-responses"
    assert spec.agent_env["OPENAI_API_KEY"] == "${OPENAI_API_KEY}"
    assert spec.agent_kwargs["api_base"] == "https://gateway.example/v1"
    assert spec.agent_kwargs["use_responses_api"] == "true"

    with pytest.raises(ValueError, match="must not contain credentials"):
        adapter.harbor_run_spec(
            "openai/gpt-test",
            protocol="openai-chat-completions",
            agent_kwargs={"api_base": "https://user:password@gateway.example/v1"},
            environ={},
            require_credentials=False,
        )


def test_campaign_cli_dry_run_is_credential_free(tmp_path, capsys):
    task = _task(tmp_path)
    spec = _write_spec(
        tmp_path / "campaign.json",
        task,
        models=[_model("chat")],
        agents=[{"id": "one-shot", "harness": "single_shot"}],
    )

    rc = cli.main([
        "campaign", str(spec), "--state", str(tmp_path / "state"), "--dry-run"
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert "no cells were executed" in captured.out
    assert captured.err == ""


def test_quality_matrix_keeps_agent_profiles_and_seeds_distinct(tmp_path):
    results = tmp_path / "results.jsonl"
    rows = [
        {
            "task": "td-one",
            "model": "same-runtime-name",
            "matrix_column_id": "profile::codex",
            "campaign_cell_id": "cell-a",
            "seed": 1,
            "reward": 1.0,
        },
        {
            "task": "td-one",
            "model": "same-runtime-name",
            "matrix_column_id": "profile::claude",
            "campaign_cell_id": "cell-b",
            "seed": 1,
            "reward": 0.0,
        },
        {
            "task": "td-one",
            "model": "same-runtime-name",
            "matrix_column_id": "profile::codex",
            "campaign_cell_id": "cell-c",
            "seed": 2,
            "reward": 0.0,
        },
    ]
    results.write_text("".join(json.dumps(row) + "\n" for row in rows))

    tasks, columns, matrix = cli._load_matrix(str(results))

    assert tasks == ["td-one"]
    assert columns == [
        "profile::codex::seed=1",
        "profile::claude::seed=1",
        "profile::codex::seed=2",
    ]
    assert matrix == [[1, 0, 0]]
