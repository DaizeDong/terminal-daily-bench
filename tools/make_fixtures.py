"""Generate synthetic input for leaderboard and catalogue behavior checks."""

from datetime import date, timedelta


def detail_content_fixture():
    """Public prose and deliberately unusable synthetic instruction fragments."""
    summary = "The parser returns an empty result when a quoted value contains a comma. Preserve the complete value during parsing."
    invalid = [
        "# Version 1.2.3\n\n(no task description provided)",
        "# Miscellaneous fixes\n\n* amend [redacted-sha]",
        "# Repair parsing\n\nInspect /private/workspace/parser.py and update the parser before running the tests.",
        "# Repair parsing\n\nApply commit abcdef0123456789 to restore the parser and its quoted values.",
        "# Repair parsing\n\n```python\nprint('The parser loses quoted values when they contain a comma.')\n```",
        "# Repair parsing\n\n<!-- This is an automatically generated release-notes comment. -->",
        "# Repair parsing\n\n## Testing\n\nI checked the parser with several quoted values and they all passed.",
        "# Repair parsing\n\n*Please include a summary of the change and which issue is fixed.*",
        "# Update totals\n\nnext_total = prior_total + item_count \u27f9 final_total = next_total",
    ]
    return {
        "summary": summary,
        "literal_comment": "`<!-- example-marker=value -->`",
        "generation_comment": "<!-- instruction: regenerated from diff semantics -->",
        "formula": "The kernel should use `j**2 + 4*j + 3` when computing the covariance values.",
        "invalid": invalid,
        "task": {
            "id": "task-parser", "title": "Preserve quoted values", "status": "live",
            "repo": "example/project", "pr_number": 1,
            "suites": ["2020-01-01", "2020-01-02"],
            "solved_by": None, "n_models": None,
        },
        "package": {"instruction": (
            "# Preserve quoted values\n\n"
            "You are working in a checked-out source repository. The upstream provenance "
            "(origin remote, project name, and commit identifiers) has been removed; solve "
            "the task from the working tree and the description below alone.\n\n"
            "## Context (de-identified)\n\n[redacted-ref].\n\n" + summary + "\n\n"
            "## Goal\n\nMake the change so that the project's regression tests pass. "
            "Do not edit the test files.\n"
        )},
    }


def effort_rows():
    rows = []
    for model, agent, effort, solved, n in (
        ("Model A", "agent-a", "low", 9, 10),
        ("Model A", "agent-a", "high", 7, 10),
        ("Model A", "agent-a", "xhigh", 3, 5),
        ("Model B", "agent-a", None, 4, 10),
        ("Model C", "agent-a", "medium", 5, 10),
        ("Model A", "agent-b", "xhigh", 2, 10),
    ):
        rows.append({"model": model, "agent": agent, "effort": effort,
                     "scaffold": agent + ("@" + effort if effort else ""),
                     "solved": solved, "n": n, "rate": solved / n})
    return rows


def catalogue_fixture(task_count=2401, suite_count=241):
    """A growing catalogue with overlapping suites and distinct unknown states."""
    first_day = date(2020, 1, 1)
    dated_ids = [(first_day + timedelta(days=i)).isoformat() for i in range(suite_count)]
    suites = [{
        "id": sid,
        "status": "live" if i >= suite_count - 3 else "archive",
        "n_tasks": 0,
        "languages": ["published-language"] if i % 17 == 0 else [],
        "note": f"Synthetic release {i}: generated tasks for catalogue checks.",
    } for i, sid in enumerate(dated_ids)]
    by_suite = {suite["id"]: suite for suite in suites}
    axes = [{
        "code": f"C{i}", "name": f"Category {i}",
        "description": f"Synthetic category {i}", "task_ids": [],
        "declared_unverified": {"task_ids": []},
    } for i in range(1, 6)]
    tasks = []
    for i in range(task_count):
        tid = f"task-{i:05d}"
        memberships = sorted({dated_ids[i % suite_count], dated_ids[(i + 1) % suite_count]})
        for sid in memberships:
            by_suite[sid]["n_tasks"] += 1
        solved, models = ((0, 10) if i % 29 == 0 else
                          ((3, 10) if i % 31 == 0 else (None, None)))
        tasks.append({
            "id": tid, "title": f"Synthetic repair {i}",
            "repo": f"example/project-{i % 17:02d}", "pr_number": i + 1,
            "suite": memberships[-1], "suites": memberships,
            "suite_memberships": [{"suite": sid, "origin": "fresh" if j == 0 else "carried"}
                                  for j, sid in enumerate(memberships)],
            "status": "live" if i % 2 else "archive",
            "language": ("python", "go", "rust", "")[i % 4],
            "declared_difficulty": ("easy", "medium", "hard", "")[i // 4 % 4],
            "difficulty": "", "n_fail_to_pass": None if i % 11 == 0 else i % 5,
            "solved_by": solved, "n_models": models,
        })
        if i % 3 == 0:
            axes[0]["task_ids"].append(tid)
            if i % 5 == 0:
                axes[2]["task_ids"].append(tid)
        elif i % 3 == 1:
            axes[1]["declared_unverified"]["task_ids"].append(tid)
            if i % 5 == 0:
                axes[3]["declared_unverified"]["task_ids"].append(tid)
    suites.extend([
        {"id": "sample", "status": "archive", "n_tasks": None,
         "languages": [], "note": "Synthetic <release> & details " + "continued " * 18},
        {"id": "sample-zero", "status": "archive", "n_tasks": 0,
         "languages": [], "note": ""},
    ])
    if tasks:
        tasks[-1]["title"] = 'Unique terminal fixture <task> & "quoted"'
    declared_n = sum(i % 3 == 1 for i in range(task_count))
    return {
        "site": {"tasks": tasks, "suites": suites},
        "cap": {"axes": axes, "publish_gate": {"min_tasks": 5}, "catalogue": {
            "n_tasks": task_count, "n_tasks_verifiable": task_count - declared_n,
            "n_tasks_unverifiable": declared_n,
        }},
        "unindexed_cap": {"axes": [], "catalogue": {}},
        "score_cases": [
            {"solved_by": None, "n_models": None},
            {"solved_by": 0, "n_models": 10},
            {"solved_by": 3, "n_models": 10},
            {"solved_by": 0, "n_models": 0},
            {"solved_by": -1, "n_models": 10},
            {"solved_by": 11, "n_models": 10},
            {"solved_by": "0", "n_models": 10},
            {"solved_by": float("inf"), "n_models": 10},
            {"solved_by": 0, "n_models": float("inf")},
        ],
    }


def task_matrix_fixture():
    """Small synthetic grids with unequal coverage and deliberately mixed order."""
    from copy import deepcopy

    task_ids = [
        "task-zeta", "task-beta", "task-epsilon", "task-alpha",
        "task-delta", "task-gamma", "task-omega",
    ]
    metadata = [
        ("Parse quoted input", "example/parse"),
        ("Repair build sequence", "example/build"),
        ("Handle binary tokens", "example/parse"),
        ('Inspect <img src=x onerror="alert(1)"> & "quotes"', "example/ui"),
        ("Check error response", "example/build"),
        ("Unobserved path", "example/unobserved"),
    ]
    site_tasks = [
        {"id": task_id, "title": title, "repo": project,
         "solved_by": 999, "n_models": 999, "difficulty": "easy"}
        for task_id, (title, project) in zip(task_ids, metadata)
    ]
    # No metadata for task-omega; metadata order cannot define the grid order.
    site_tasks.reverse()
    site_tasks.extend([
        {"id": "task-unrelated", "title": "Unrelated repair",
         "repo": "example/unrelated", "solved_by": 999, "n_models": 999},
        {"id": "task-next-a", "title": "Next release alpha", "repo": "example/next"},
        {"id": "task-next-b", "title": "Next release beta", "repo": "example/next"},
    ])
    rows = [
        {"model": "model-zero", "g": [0, 0, 0, 0, 0, None, 0]},
        {"model": "model-wide", "g": [1, 1, 1, 0, 0, None, 0]},
        {"model": "model-unrun", "g": [None] * 7},
        {"model": "model-narrow", "g": [None, 1, None, 1, None, None, None]},
        {"model": "model-tie", "g": [0, 1, 1, None, 0, None, 1]},
    ]
    day = {
        "schema": "tdb-day-v1", "date": "2020-01-01",
        "n_tasks": 999, "n_models": 999, "suite": {"n_tasks": 888},
        "leaderboard": [
            {"model": "model-wide", "single_shot": {"solved": 3, "n": 6},
             "single_shot@xhigh": {"solved": 99, "n": 100}},
            {"model": "summary-only", "single_shot@ultra": {"solved": 100, "n": 100}},
        ],
        "matrix": {"scaffold": "single_shot", "tasks": task_ids, "rows": rows},
    }
    next_day = {
        "schema": "tdb-day-v1", "date": "2020-01-02",
        "leaderboard": [],
        "matrix": {
            "scaffold": "agent-test@high",
            "tasks": ["task-next-b", "task-next-a"],
            "rows": [
                {"model": "model-narrow", "g": [0, 1]},
                {"model": "model-fresh", "g": [1, None]},
            ],
        },
    }
    missing_day = deepcopy(day)
    del missing_day["matrix"]
    invalid_days = {}
    duplicate_task = deepcopy(day)
    duplicate_task["matrix"]["tasks"][-1] = task_ids[0]
    invalid_days["duplicate_task"] = duplicate_task
    duplicate_model = deepcopy(day)
    duplicate_model["matrix"]["rows"][1]["model"] = rows[0]["model"]
    invalid_days["duplicate_model"] = duplicate_model
    short_row = deepcopy(day)
    short_row["matrix"]["rows"][0]["g"].pop()
    invalid_days["short_row"] = short_row
    long_row = deepcopy(day)
    long_row["matrix"]["rows"][0]["g"].append(None)
    invalid_days["long_row"] = long_row
    for name, value in [
        ("boolean", True), ("string", "1"), ("fraction", 0.5),
        ("negative", -1), ("outside_binary", 2),
    ]:
        invalid = deepcopy(day)
        invalid["matrix"]["rows"][0]["g"][0] = value
        invalid_days[name] = invalid
    return {
        "day": day, "next_day": next_day, "missing_day": missing_day,
        "site": {"tasks": site_tasks}, "invalid_days": invalid_days,
        "labels": {
            "model-wide": "Display generalist",
            "model-narrow": "Display specialist",
            "model-tie": "Display peer",
            "model-zero": "Display zero",
            "model-unrun": "Display untested",
        },
    }


def community_fixture():
    """Synthetic checked results and distinct pending review states."""
    return {
        "community_verified": [
            {
                "submitter": "user1@example.com", "model": "Model A",
                "scaffold": "single_shot@high", "verified": 4, "n": 4,
                "solved": 3, "false_accept": None,
            },
            {
                "submitter": "AcmeCorp", "model": "Model B",
                "scaffold": "single_shot", "verified": 6, "n": 6,
                "solved": 3, "false_accept": 0,
            },
        ],
        "community_pending": [
            {
                "submitter": "user1@example.com", "model": "Model C",
                "scaffold": "single_shot@medium", "n": 5, "solved": 0,
                "false_accept": None, "pending": 3, "running": 2,
                "error": 0, "rejected": 0,
            },
            {
                "submitter": "AcmeCorp", "model": "Model D",
                "scaffold": "single_shot@low", "n": 3, "solved": 0,
                "false_accept": None, "pending": 0, "running": 0,
                "error": 1, "rejected": 2,
            },
        ],
    }


def site_insights_fixture():
    """Synthetic comparison, profile, cost and release-history observations."""
    tasks = ["task-alpha", "task-beta", "task-gamma", "task-new"]
    matrix = {"scaffold": "single_shot", "tasks": tasks, "rows": [
        {"model": "model-a", "g": [1, 0, 1, None]},
        {"model": "model-b", "g": [0, 1, 1, 0]},
        {"model": "model-empty", "g": [None, None, None, None]},
    ]}
    previous = {"schema": "tdb-day-v1", "date": "2020-01-01", "matrix": {
        "scaffold": "single_shot", "tasks": ["task-alpha", "task-beta", "task-old"],
        "rows": [
            {"model": "model-a", "g": [0, 0, 1]},
            {"model": "model-b", "g": [0, None, 0]},
        ],
    }, "leaderboard": []}
    day = {"schema": "tdb-day-v1", "date": "2020-01-02", "matrix": matrix,
           "leaderboard": [
               {"model": "model-a", "single_shot": {"solved": 2, "n": 3},
                "single_shot@high": {"solved": 3, "n": 4}},
               {"model": "model-b", "single_shot": {"solved": 2, "n": 4}},
           ]}
    records = []
    for model, scaffold, outcomes, costs, durations, commands, tools in (
        ("model-a", "single_shot", [1, 0, 1], [1.0, 2.0, 0.0], [10.0, 20.0, 30.0], [0, 2, 4], [1, 4, 6]),
        ("model-a", "single_shot@high", [1, 1, 1, 0], [2.0, 3.0, 4.0, 5.0], [20.0, 30.0, 40.0, 50.0], [2, 3, 4, 5], [4, 5, 7, 7]),
        ("model-b", "single_shot", [0, 1, 1, 0], [1.5, None, 2.5, None], [12.0, 24.0, None, 48.0], [1, None, 3, None], [2, 5, None, 6]),
    ):
        for i, outcome in enumerate(outcomes):
            records.append({"id": f"run-{len(records) + 1:03d}", "task_id": tasks[i],
                "model": model, "scaffold": scaffold, "outcome": outcome,
                "cost_usd": costs[i], "wall_sec": durations[i],
                "command_count": commands[i], "tool_call_count": tools[i],
                "input_tokens": None, "output_tokens": None, "steps": []})
    run_details = {"schema": "tdb-run-details-v1", "date": day["date"], "runs": records}
    cap = {"publish_gate": {"min_tasks": 1}, "axes": [
        {"code": "C1", "name": "Parsing", "task_ids": ["task-alpha", "task-beta"]},
        {"code": "C2", "name": "Validation", "task_ids": ["task-gamma", "task-new"]},
        {"code": "C3", "name": "Unobserved", "task_ids": ["task-unobserved"]},
    ]}
    site = {"tasks": [{"id": tid, "title": f"Synthetic repair {i}",
             "repo": "example/project", "suites": [day["date"]]}
            for i, tid in enumerate(tasks)]}
    from copy import deepcopy
    multi_day = deepcopy(day)
    multi_day["matrices"] = {"single_shot": deepcopy(matrix), "single_shot@high": {
        "scaffold": "single_shot@high", "tasks": list(reversed(tasks)),
        "rows": [{"model": "model-a", "g": [0, 1, 1, 1]}],
    }}
    attempts = []
    for task_id, outcomes, cell_outcome in (
        ("task-alpha", [1, 1, 0], 1), ("task-beta", [0, 1, 0], 0),
    ):
        for attempt_index, outcome in enumerate(outcomes):
            attempts.append({"id": f"attempt-{task_id}-{attempt_index}",
                "task_id": task_id, "model": "model-a", "scaffold": "single_shot",
                "attempt_index": attempt_index, "trial_count": 3,
                "outcome": outcome, "cell_outcome": cell_outcome,
                "cost_usd": float(attempt_index + 1), "wall_sec": float(10 * (attempt_index + 1)),
                "command_count": 2 * attempt_index, "tool_call_count": 2 * attempt_index + 1,
                "input_tokens": None, "output_tokens": None, "steps": []})
    repeat_day = deepcopy(day)
    repeat_day["aggregation"] = {"method": "strict_majority", "unit": "task", "trials_per_cell": 3}
    for row, trials in zip(repeat_day["matrix"]["rows"], (
        [[1, 0, 1, None], [1, 1, 1, None], [0, 0, 1, None]],
        [[0, 1, 1, 0], [0, 1, 0, 0], [1, 0, 1, 0]],
        [[None] * 4 for _ in range(3)],
    )):
        row["trials"] = trials
    repeat_previous = deepcopy(previous)
    repeat_previous["aggregation"] = deepcopy(repeat_day["aggregation"])
    repeat_previous["matrix"]["rows"][0]["trials"] = [[0, 0, 1], [1, 0, 1], [0, 0, 1]]
    repeat_previous["matrix"]["rows"][1]["trials"] = [[0, None, 0], [0, None, 0], [0, None, 1]]
    multi_day["aggregation"] = deepcopy(repeat_day["aggregation"])
    partial_trials = [[1, 0, None, None], [1, 1, None, None], [0, 0, None, None]]
    multi_day["matrix"]["rows"][0]["trials"] = deepcopy(partial_trials)
    multi_day["matrices"]["single_shot"]["rows"][0]["trials"] = deepcopy(partial_trials)
    outside_day = repeat_score_fixture("outside")["day"]
    outside_day["matrix"]["scaffold"] = "single_shot"
    outside_runs = []
    for row, result in zip(outside_day["matrix"]["rows"], outside_day["leaderboard"]):
        result["single_shot"] = result.pop("agent-test@high")
        for attempt_index, outcomes in enumerate(row["trials"]):
            for index, outcome in enumerate(outcomes):
                if outcome is None:
                    continue
                outside_runs.append({"id": f"outside-{row['model']}-{index}-{attempt_index}",
                    "task_id": outside_day["matrix"]["tasks"][index], "model": row["model"],
                    "scaffold": "single_shot", "attempt_index": attempt_index, "trial_count": 3,
                    "outcome": outcome, "cell_outcome": row["g"][index],
                    "command_count": 2 + index + attempt_index, "tool_call_count": 4 + index + attempt_index,
                    "cost_usd": float(1 + index + attempt_index), "wall_sec": float(10 + index + attempt_index),
                    "input_tokens": None, "output_tokens": None, "steps": []})
    return {"day": day, "previous_day": previous, "site": site, "cap": cap,
            "run_details": run_details, "runs": records, "multi_day": multi_day,
            "repeat_day": repeat_day, "repeat_previous_day": repeat_previous,
            "outside_range_day": outside_day,
            "outside_range_details": {"schema": "tdb-run-details-v1", "date": outside_day["date"],
                                      "runs": outside_runs},
            "multi_attempt_details": {"schema": "tdb-run-details-v1", "date": day["date"],
                                      "runs": attempts}}


def release_insights_fixture():
    """Synthetic first appearance, retention, removal and return across releases."""
    memberships = {
        "2020-01-01": ["task-return", "task-retained", "task-removed"],
        "2020-01-02": ["task-retained", "task-middle"],
        "2020-01-03": ["task-return", "task-retained", "task-new"],
    }
    titles = {"task-return": "Returning parser repair", "task-retained": "Retained build repair",
              "task-removed": "Removed value repair", "task-middle": "Intermediate repair",
              "task-new": "New validation repair"}
    site = {"suites": [{"id": day, "task_ids": ids, "n_tasks": len(ids), "status": "live"}
                       for day, ids in memberships.items()],
            "tasks": [{"id": tid, "title": title, "repo": "example/project",
                       "suites": [day for day, ids in memberships.items() if tid in ids]}
                      for tid, title in titles.items()]}
    days = [{"schema": "tdb-day-v1", "date": day, "suite": {"id": day, "task_ids": ids},
             "matrix": {"scaffold": "single_shot", "tasks": ids,
                        "rows": [{"model": "model-a", "g": [1] + [None] * (len(ids) - 1)},
                                 {"model": "model-b", "g": [0] * len(ids)}]},
             "leaderboard": []}
            for day, ids in memberships.items()]
    return {"site": site, "days": days, "memberships": memberships,
            "latest_day": days[-1], "previous_day": days[-2], "title_cases": [
                ["fix(parser): preserve quoted values ([redacted-ref])", "Preserve quoted values"],
                ["[redacted-repo]: enable structured logging", "Enable structured logging"],
                ["Fix `value**2` for negative inputs", "Fix value**2 for negative inputs"],
                ["Fix parser aaaa1111", "Fix parser"], ["", "Software maintenance task"],
            ]}


def site_share_fixture():
    """Synthetic shared-view values including CSV formula and quoting cases."""
    return {"base": "https://example.com/project/", "snapshot": {
        "date": "2020-01-02", "view": "compare", "title": "Model comparison",
        "columns": [{"key": "model", "label": "Model", "type": "text"},
                    {"key": "rate", "label": "Success rate", "type": "percent"},
                    {"key": "n", "label": "Tasks", "type": "number"}],
        "rows": [{"model": "Model A", "rate": .5, "n": 4},
                 {"model": "=SUM(1,2)", "rate": 0, "n": 4},
                 {"model": 'Model, "B"', "rate": None, "n": 0}],
        "notes": ["Synthetic shared-task results."],
    }}


def run_details_fixture():
    """Complete synthetic repeated trials, including failures and unsafe prose."""
    source = []
    for model, observations in (
        ("model-a@high", ((1, 1, 0), (0, 1, 0))),
        ("model-b@high", ((0, 0, 1), (1, 0, 1))),
    ):
        for task, outcomes in zip(("task-alpha", "task-beta"), observations):
            for trial, passed in enumerate(outcomes):
                source.append({"task_id": task, "model": model, "scaffold": "agent-test",
                    "trial": trial, "passed": bool(passed), "reward": float(passed),
                    "unobserved": False, "cost_s": float(10 * (trial + 1)),
                    "jobs_dir": "/private/example/run", "error": "PRIVATE_LOG_SENTINEL"})
    published = {"schema": "tdb-day-v1", "date": "2020-01-02", "n_tasks": 2,
        "n_models": 2, "n_cells": 4, "suite": {"id": "2020-01-02"},
        "leaderboard": [{"model": model, "agent-test@high": {"n": 2, "solved": 1, "rate": .5}}
                        for model in ("model-a", "model-b")]}
    trajectory = {"steps": [
        {"source": "assistant", "message": "PRIVATE_REASONING_SENTINEL", "tool_calls": [
            {"function_name": "exec_command", "arguments": {
                "cmd": "pytest /private/example/test.py --token TOKEN_FOR_TEST"}}],
         "observation": {"output": "PRIVATE_OUTPUT_SENTINEL"}},
        {"source": "assistant", "tool_calls": [{"function_name": "apply_patch",
            "arguments": {"patch": "PRIVATE_PATCH_SENTINEL"}}]},
        {"source": "assistant", "tool_calls": [{"function_name": "PRIVATE_TOOL_SENTINEL"}]},
    ], "final_metrics": {"total_cost_usd": 9.0}}
    return {"published": published, "board": {"n_trials": 3, "results": source},
            "trajectory": trajectory, "excluded_row": {
                "task_id": "task-alpha", "model": "model-a@max", "scaffold": "agent-test",
                "trial": 0, "passed": False, "reward": 0.0, "unobserved": False, "cost_s": 1.0}}


def site_export_fixture():
    """Synthetic CSV formula prefixes and long visible export text."""
    from copy import deepcopy
    base = site_share_fixture()["snapshot"]
    base["rows"] = [{"model": prefix + "Synthetic formula", "rate": -.25 if i == 0 else .5, "n": 4}
                    for i, prefix in enumerate(("=", "+", "-", "@", "  =", "\t+", "\n@"))]
    base["title"] = "Synthetic export title " * 30
    base["notes"] = ["Synthetic long explanation of measured task coverage. " * 45]
    base["rows"].append({"model": "LongSyntheticModelLabel" * 20, "rate": None, "n": 0})
    efficiency = deepcopy(base)
    efficiency["view"] = "efficiency"
    efficiency_keys = ["model", "agent", "effort", "success_rate_all", "all_n", "all_tasks"]
    for prefix, mean in (("command", "mean_commands"), ("tool", "mean_tool_calls"), ("cost", "mean_cost_usd")):
        efficiency_keys.extend([f"success_rate_{prefix}_subset", f"success_rate_{prefix}_subset_sd",
                                f"success_rate_{prefix}_subset_runs", mean, f"{prefix}_n", f"{prefix}_tasks"])
    efficiency["columns"] = [{"key": key, "label": key.replace("_", " ").title(),
                              "type": "percent" if "rate" in key and not key.endswith("_runs") else "text" if key in ("model", "agent", "effort") else "number"}
                             for key in efficiency_keys]
    efficiency["rows"] = [{"model": "Model A", "agent": "agent-test", "effort": "high",
        "success_rate_all": .5, "success_rate_cost_subset": .75, "success_rate_command_subset": .4,
        "success_rate_tool_subset": .5, "success_rate_command_subset_sd": .1, "success_rate_command_subset_runs": 3,
        "success_rate_tool_subset_sd": .2, "success_rate_tool_subset_runs": 3,
        "success_rate_cost_subset_sd": .3, "success_rate_cost_subset_runs": 3,
        "mean_cost_usd": 2.5, "mean_commands": 3.5, "mean_tool_calls": 5.5,
        "cost_n": 4, "command_n": 5, "tool_n": 6, "all_n": 6,
        "cost_tasks": 2, "command_tasks": 2, "tool_tasks": 2, "all_tasks": 2}]
    profile = deepcopy(base)
    profile["view"] = "profile"
    profile_keys = ["model", "capability", "rate", "rate_sd", "rate_runs", "evaluated", "paired_peer_gap", "peer_pairs", "preliminary"]
    profile["columns"] = [{"key": key, "label": key.replace("_", " ").title(),
                          "type": "percent" if key in ("rate", "rate_sd", "paired_peer_gap") else "number" if key in ("evaluated", "peer_pairs", "rate_runs") else "text"}
                         for key in profile_keys]
    profile["rows"] = [{"model": "Model A", "capability": "Parsing", "rate": .5, "rate_sd": .1, "rate_runs": 3,
                        "evaluated": 4, "paired_peer_gap": -.25, "peer_pairs": 3, "preliminary": True}]
    outside_efficiency, outside_profile = deepcopy(efficiency), deepcopy(profile)
    outside_efficiency["rows"], outside_profile["rows"] = [], []
    for model, center in (("model-a", 1), ("model-b", 0)):
        efficiency_row, profile_row = deepcopy(efficiency["rows"][0]), deepcopy(profile["rows"][0])
        efficiency_row.update(model=model, success_rate_all=center)
        for prefix in ("command", "tool", "cost"):
            key = f"success_rate_{prefix}_subset"
            efficiency_row.update({key: center, key + "_sd": 0})
        profile_row.update(model=model, rate=center, rate_sd=0)
        outside_efficiency["rows"].append(efficiency_row)
        outside_profile["rows"].append(profile_row)
    capability = deepcopy(base)
    capability["view"] = "capability"
    capability["columns"] = [{"key": key, "label": label, "type": kind} for key, label, kind in (
        ("model", "Model", "text"), ("overall", "Overall", "percent"),
        ("overall_sd", "Overall run standard deviation", "percent"), ("overall_runs", "Overall runs", "number"),
        ("cap:C1", "Parsing", "percent"), ("cap:C1_sd", "Parsing run standard deviation", "percent"),
        ("cap:C1_runs", "Parsing runs", "number"), ("cap:C1:n", "Parsing tasks", "number"),
        ("cap:C1:labels", "Parsing labels", "text"), ("preliminary", "Preliminary", "text"))]
    capability["rows"] = [{"model": model, "overall": .5, "overall_sd": .1, "overall_runs": 3,
        "cap:C1": .5, "cap:C1_sd": .1, "cap:C1_runs": 3, "cap:C1:n": 4,
        "cap:C1:labels": "Preliminary" if preliminary else "Verified", "preliminary": preliminary}
        for model, preliminary in (("Model A", False), ("Model B", True))]
    return {"snapshot": base, "efficiency": efficiency, "profile": profile, "capability": capability,
            "outside_range_efficiency": outside_efficiency, "outside_range_profile": outside_profile,
            "prefixes": [row["model"] for row in base["rows"][:-1]]}


def site_routes_fixture():
    """Synthetic legacy routes and query aliases under a project path."""
    return {"base": "https://example.com/project/", "cases": [
        {"path": "registry/index.html", "expected_path": "tasks/index.html", "expected_name": "tasks",
         "html": '<a href="../guide/">Guide</a><script src="../assets/site.js" data-page="registry"></script>'},
        {"path": "guide/index.html", "expected_path": "docs/index.html", "expected_name": "docs",
         "html": '<a href="../registry/">Tasks</a><script src="../assets/site.js" data-page="guide"></script>'},
        {"path": "benchmarks/index.html", "expected_path": "releases/index.html", "expected_name": "releases",
         "html": '<a href="../registry/">Tasks</a><script src="../assets/site.js" data-page="benchmarks"></script>'},
    ], "query_cases": [
        {"url": "https://example.com/project/registry/?d=2020-01-02&q=parser&suite=2020-01-01",
         "expected": "https://example.com/project/tasks/?date=2020-01-02&query=parser&release=2020-01-01"},
        {"url": "https://example.com/project/guide/?lang=python&repo=example%2Fproject",
         "expected": "https://example.com/project/docs/?language=python&project=example%2Fproject"},
    ]}


def site_capability_metadata_fixture():
    """Synthetic declared labels, plus malformed metadata that must be refused."""
    return {"site": site_insights_fixture()["site"],
            "labels": {"task-alpha": ["C1", "C4"], "task-beta": ["C1"]},
            "package_verified": {"task-gamma": ["C2"]},
            "package_unverified": {"task-alpha": ["C1"]},
            "invalid_labels": [None, [], {"": []}, {"task": [None]}, {"task": ["unknown"]}]}


def task_run_view_fixture():
    """Synthetic task-view observations and enough rows to test deep links."""
    fixture = site_insights_fixture()
    return {"day": fixture["multi_day"], "details": fixture["multi_attempt_details"],
            "task": "task-alpha", "legacy_day": fixture["previous_day"],
            "pagination_rows": [{"id": f"page-run-{i:03d}", "model": "model-a" if i < 45 else "model-b",
                                  "scaffold": "single_shot@high", "attempt_index": i}
                                 for i in range(55)]}


def call_telemetry_fixture():
    """Synthetic complete, partial, ambiguous and malformed ATIF call records."""
    from copy import deepcopy
    base = {"agent": {"name": "codex", "version": "1.2.3", "model_name": "model-test"},
            "steps": [{"llm_call_count": 1, "tool_calls": [
                {"function_name": "functions.shell_command", "arguments": {"command": "echo example && echo test"}},
                {"function_name": "apply_patch"}]},
                {"llm_call_count": 1, "tool_calls": [{"function_name": "Bash", "arguments": {"command": "echo example"}}]}],
            "final_metrics": {"total_steps": 2}}
    empty = deepcopy(base)
    empty["steps"] = []
    empty["final_metrics"]["total_steps"] = 0
    unknown = deepcopy(base)
    unknown["steps"][0]["tool_calls"].append({"function_name": "example_unknown_tool"})
    malformed = deepcopy(base)
    malformed["steps"][0]["tool_calls"].append("invalid-call")
    partial = deepcopy(base)
    partial["final_metrics"]["total_steps"] = 3
    continued = deepcopy(base)
    continued["continued_trajectory_ref"] = "trajectory.cont-1.json"
    terminus = deepcopy(base)
    terminus["agent"]["name"] = "terminus-2"
    terminus["steps"] = [{"tool_calls": [{"function_name": "bash_command", "arguments": {"keystrokes": "echo example && echo test\n"}}, {"function_name": "mark_task_complete"}]}]
    terminus["final_metrics"]["total_steps"] = 1
    raw = deepcopy(terminus)
    raw["steps"] = [{}]
    return {"complete": base, "empty": empty, "unknown": unknown, "malformed": malformed,
            "partial": partial, "continued": continued, "terminus": terminus, "raw": raw,
            "invalid_counts": [-1, .5, True, "2", 10**13],
            "harness": {"trajectory_complete": True, "n_command_calls": 2, "n_tool_calls": 3,
                        "prompt_tokens": 8, "completion_tokens": 2, "cost_usd": .25}}


def eval_results_fixture(case="complete"):
    """Persisted clean-pipeline rows with scalar counts and synthetic private certs."""
    from copy import deepcopy
    sample = run_details_fixture()
    rows = []
    for record in sample["board"]["results"]:
        row = {key: deepcopy(record[key]) for key in ("task_id", "model", "scaffold", "trial", "reward", "passed", "cost_s")}
        row.update({"gated_by_exec": True, "cert": {"jobs_dir": "/private/example/run"},
                    "canary_violation": False, "capability_labels": [],
                    "llm_scores": {"advisory": 99}, "harness": deepcopy(call_telemetry_fixture()["harness"])})
        row["harness"]["trajectory_path"] = "/private/example/trajectory.json"
        rows.append(row)
    sample["published"]["matrix"] = {"scaffold": "agent-test@high",
        "tasks": ["task-alpha", "task-beta"], "rows": [
            {"model": "model-a", "g": [1, 0]}, {"model": "model-b", "g": [0, 1]}]}
    if case == "advisory":
        rows[0]["gated_by_exec"] = False
    elif case == "unobserved":
        rows[0]["cert"]["verdict_unobserved"] = "synthetic verifier failure"
    elif case == "unparsed_reward":
        rows[2]["cert"].update(reward_parsed=False, verdict_source="separate_verifier_exec")
        rows[2]["harness"] = {
            "trajectory_complete": False, "n_command_calls": None, "n_tool_calls": None}
    elif case == "unequal":
        rows.pop()
    elif case == "aggregate":
        sample["published"]["leaderboard"][0]["agent-test@high"]["solved"] = 2
    elif case == "cell":
        sample["published"]["matrix"]["rows"][0]["g"] = [0, 1]
    elif case == "duplicate":
        rows[1]["trial"] = 0
    elif case == "missing_trial":
        rows[2]["trial"] = 3
    elif case == "reward_disagrees":
        rows[0]["reward"] = 0.0
    elif case == "harness":
        rows[0]["harness"] = []
    elif case == "certificate":
        rows[0]["cert"] = []
    elif case == "excluded":
        extra = deepcopy(rows[0])
        extra["model"] = "model-a@max"
        extra["gated_by_exec"] = False
        rows.append(extra)
    elif case == "zero_missing":
        rows[0]["harness"].update(n_command_calls=0, n_tool_calls=0)
        rows[1].pop("harness")
        rows[2]["harness"]["trajectory_complete"] = False
    elif case != "complete":
        raise ValueError(f"unknown eval-results fixture case: {case}")
    return {"published": sample["published"], "records": rows}


def repeat_score_fixture(case="complete"):
    """Synthetic complete rounds, including equal totals with different successes."""
    day = {"schema": "tdb-day-v1", "date": "2020-01-02",
        "aggregation": {"method": "strict_majority", "unit": "task", "trials_per_cell": 3},
        "leaderboard": [
            {"model": "model-a", "agent-test@high": {"n": 3, "solved": 2, "rate": 2 / 3}},
            {"model": "model-b", "agent-test@high": {"n": 3, "solved": 0, "rate": 0}},
        ],
        "matrix": {"scaffold": "agent-test@high",
            "tasks": ["task-alpha", "task-beta", "task-gamma", "task-missing"], "rows": [
                {"model": "model-a", "g": [1, 0, 1, None], "trials": [
                    [1, 0, 1, None], [1, 1, 1, None], [0, 0, 1, None]]},
                {"model": "model-b", "g": [0, 0, 0, None], "trials": [
                    [1, 0, 0, None], [0, 1, 0, None], [0, 0, 1, None]]},
            ]}}
    if case == "rank":
        day["matrix"]["rows"][0].update(g=[1, 0, 0, None], trials=[
            [1, 1, 0, None], [1, 0, 1, None], [1, 0, 0, None]])
        day["matrix"]["rows"][1].update(g=[1, 1, 0, None], trials=[
            [1, 1, 0, None], [1, 0, 0, None], [0, 1, 0, None]])
        day["leaderboard"][0]["agent-test@high"].update(solved=1, rate=1 / 3)
        day["leaderboard"][1]["agent-test@high"].update(solved=2, rate=2 / 3)
    elif case == "tie":
        day["matrix"]["rows"][0].update(g=[1, 0, 0, None], trials=[
            [1, 1, 0, None], [1, 0, 1, None], [1, 0, 0, None]])
        day["matrix"]["rows"][1].update(g=[1, 0, 0, None], trials=[
            [1, 0, 0, None], [1, 0, 0, None], [1, 0, 0, None]])
        for result in day["leaderboard"]:
            result["agent-test@high"].update(solved=1, rate=1 / 3)
    elif case == "outside":
        day["matrix"]["rows"][0].update(g=[1, 1, 1, None], trials=[
            [1, 1, 0, None], [1, 0, 1, None], [0, 1, 1, None]])
        day["leaderboard"][0]["agent-test@high"].update(solved=3, rate=1)
    elif case == "sd_bounds":
        day["matrix"]["rows"][0].update(g=[1, 1, 1, None], trials=[
            [1, 1, 1, None], [1, 1, 0, None], [0, 0, 1, None]])
        day["matrix"]["rows"][1].update(g=[0, 0, 0, None], trials=[
            [0, 0, 0, None], [0, 0, 1, None], [1, 1, 0, None]])
        day["leaderboard"][0]["agent-test@high"].update(solved=3, rate=1)
    elif case != "complete":
        raise ValueError(f"unknown repeat-score fixture case: {case}")
    cap = {"publish_gate": {"min_tasks": 2}, "axes": [
        {"code": "C4", "name": "Implementation", "task_ids": ["task-alpha", "task-beta", "task-gamma"]},
        {"code": "C2", "name": "Build", "task_ids": ["task-alpha", "task-beta"]},
        {"code": "C9", "name": "Unmeasured", "task_ids": ["task-missing"]},
    ]}
    return {"day": day, "cap": cap}


def repeat_trials_fixture(case="complete"):
    """Public repeated attempts with synthetic identity and malformed edge cases."""
    from copy import deepcopy
    import hashlib
    import json

    sample = run_details_fixture()
    day = deepcopy(sample["published"])
    day["aggregation"] = {"method": "strict_majority", "unit": "task", "trials_per_cell": 3}
    matrix = {"scaffold": "agent-test@high", "tasks": ["task-alpha", "task-beta", "task-missing"],
        "rows": [{"model": "model-a", "g": [1, 0, None], "note": "synthetic metadata"},
                 {"model": "model-b", "g": [0, 1, None]}]}
    day["matrices"] = {"agent-test@high": deepcopy(matrix)}
    day["matrix"] = deepcopy(matrix)
    day["matrix"]["tasks"] = ["task-beta", "task-missing", "task-alpha"]
    day["matrix"]["rows"][0]["g"] = [0, None, 1]
    day["matrix"]["rows"][1]["g"] = [1, None, 0]
    runs = []
    for source in sample["board"]["results"]:
        model, effort = source["model"].rsplit("@", 1)
        scaffold = source["scaffold"] + "@" + effort
        task, trial = source["task_id"], source["trial"]
        identity = json.dumps([day["date"], task, model, scaffold, trial], separators=(",", ":"))
        runs.append({"id": "run-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
            "task_id": task, "model": model, "scaffold": scaffold, "attempt_index": trial,
            "trial_count": 3, "outcome": int(source["passed"]),
            "cell_outcome": int((model == "model-a") == (task == "task-alpha"))})
    details = {"schema": "tdb-run-details-v1", "date": day["date"], "runs": runs,
        "aggregation": {"unit": "attempt", "published_outcome": "strict_majority", "trials_per_cell": 3}}
    if case == "duplicate":
        runs.append(deepcopy(runs[0]))
    elif case == "truncated":
        runs.pop()
    elif case == "missing_cell":
        del runs[:3]
    elif case == "unobserved":
        runs[0]["unobserved"] = True
    elif case == "invalid_outcome":
        runs[0]["outcome"] = True
    elif case == "invalid_index":
        runs[0]["attempt_index"] = True
    elif case == "wrong_count":
        runs[0]["trial_count"] = 2
    elif case == "wrong_id":
        runs[0]["id"] = "run-synthetic-wrong"
    elif case == "wrong_date":
        details["date"] = "2020-01-03"
    elif case == "wrong_group":
        runs[0]["scaffold"] = "agent-test@low"
    elif case == "wrong_cell":
        runs[0]["cell_outcome"] = 0
    elif case == "wrong_majority":
        runs[0]["outcome"] = 0
    elif case == "aggregate":
        day["leaderboard"][0]["agent-test@high"]["solved"] = 2
    elif case == "conflicting_null":
        day["matrix"]["rows"][0]["g"][2] = None
    elif case == "existing_boolean":
        day["matrix"]["rows"][0]["trials"] = [[0, None, True], [1, None, 1], [0, None, 0]]
    elif case == "invalid_aggregation":
        day["aggregation"] = []
    elif case == "single":
        runs[:] = [r for r in runs if r["attempt_index"] == 0]
        for r in runs:
            r["trial_count"] = 1
        details["aggregation"]["trials_per_cell"] = 1
        day["aggregation"]["trials_per_cell"] = 1
    elif case != "complete":
        raise ValueError(f"unknown repeat fixture case: {case}")
    return {"day": day, "details": details, "board": sample["board"]}
