"""Publish bounded run telemetry after proving parity with a published day.

Raw boards, provider ledgers and trajectories stay outside the public checkout.
The converter accepts an explicitly selected board or persisted evaluation array
and explicit exclusions, proves every published model/scaffold aggregate, and
preserves every included attempt.
``cost_s`` is elapsed seconds; it is never interpreted as dollars. Missing
telemetry stays null. Replay uses fixed descriptions of observed tool calls and
never publishes tool arguments, terminal output or assistant reasoning.
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import shlex


EFFORT_ORDER = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")
TOKEN_LIMIT = 10**12
NUMBER_LIMIT = 10**12
MAX_STEPS = 10_000
COMMAND_TOOLS = frozenset({"terminal", "bash", "shell", "exec_command", "run_command", "shell_command", "bash_command"})
NON_COMMAND_TOOLS = frozenset({"read_file", "list_files", "apply_patch", "write_file", "run_tests",
    "read", "edit", "multiedit", "write", "glob", "grep", "webfetch", "websearch",
    "todowrite", "todoread", "notebookedit", "mark_task_complete", "update_plan"})


class DataError(ValueError):
    """Source data cannot establish the advertised public observation."""


def _number(value, *, integer=False):
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise DataError("telemetry must be a finite nonnegative number or null")
    if value > (TOKEN_LIMIT if integer else NUMBER_LIMIT):
        raise DataError("telemetry exceeds the publication bound")
    if integer and (type(value) is not int):
        raise DataError("counts and attempt indices must be integers")
    return value


def _text(value, label):
    if not isinstance(value, str) or not value or len(value) > 256:
        raise DataError(f"invalid {label}")
    if any(ord(c) < 32 for c in value):
        raise DataError(f"control character in {label}")
    return value


def _date(value):
    import datetime
    try:
        if datetime.date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except (TypeError, ValueError):
        raise DataError("invalid publication date") from None
    return value


def run_id(date, task, model, scaffold, attempt):
    """Stable public identifier derived exclusively from published cell identity."""
    identity = json.dumps([date, task, model, scaffold, attempt], separators=(",", ":"))
    return "run-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def _trajectory_calls(trajectory):
    """Validate all recorded calls before projecting or counting any of them."""
    if trajectory is None:
        return []
    if not isinstance(trajectory, dict) or not isinstance(trajectory.get("steps"), list):
        raise DataError("trajectory requires an explicit steps array")
    if len(trajectory["steps"]) > MAX_STEPS:
        raise DataError("trajectory exceeds the publication step bound")
    if trajectory.get("continued_trajectory_ref") or trajectory.get("subagent_trajectories"):
        raise DataError("linked or nested trajectories require complete external binding")
    final = trajectory.get("final_metrics")
    if isinstance(final, dict) and final.get("total_steps") is not None:
        if _number(final["total_steps"], integer=True) != len(trajectory["steps"]):
            raise DataError("trajectory step total does not match recorded steps")
    result = []
    for step in trajectory["steps"]:
        if not isinstance(step, dict):
            raise DataError("invalid trajectory step")
        calls = step.get("tool_calls", [])
        if not isinstance(calls, list) or any(not isinstance(call, dict) for call in calls):
            raise DataError("tool_calls must be an array of objects")
        result.extend(calls)
        if len(result) > MAX_STEPS:
            raise DataError("trajectory exceeds the publication action bound")
    return result


def _command_tool(call):
    name = call.get("function_name") or call.get("name")
    return isinstance(name, str) and name.rsplit(".", 1)[-1].lower() in COMMAND_TOOLS


def trajectory_counts(trajectory):
    """One shell tool invocation is one command, including compound commands."""
    if trajectory is None:
        return None, None
    calls = _trajectory_calls(trajectory)
    agent = trajectory.get("agent", {})
    if isinstance(agent, dict) and agent.get("name") == "terminus-2" and trajectory["steps"] and not calls:
        # Terminus raw-content exports omit parsed calls entirely.
        return None, None
    names = [call.get("function_name") or call.get("name") for call in calls]
    if any(not isinstance(name, str) or name.rsplit(".", 1)[-1].lower() not in COMMAND_TOOLS | NON_COMMAND_TOOLS for name in names):
        return None, len(calls)
    return sum(_command_tool(call) for call in calls), len(calls)


def _bound_metric(extra, source, field, alias=None, *, integer=False):
    """Accept audited attempt telemetry and the evaluator's finalized ATIF fields."""
    records = [extra]
    for record in (source, source.get("harness"), extra.get("harness")):
        if isinstance(record, dict) and record.get("trajectory_complete") is True:
            records.append(record)
    values = [_number(record[key], integer=integer) for record in records
              for key in (field, alias) if key and record.get(key) is not None]
    if values and any(value != values[0] for value in values):
        raise DataError("conflicting telemetry aliases")
    return values[0] if values else None


def safe_steps(trajectory):
    """Project actual ATIF tool calls to fixed prose without copying free text."""
    calls = _trajectory_calls(trajectory)
    tool_labels = {
        "read_file": ("read", "Read a file", "The agent requested file contents."),
        "list_files": ("read", "Listed files", "The agent requested a file listing."),
        "apply_patch": ("edit", "Submitted a patch", "The agent submitted a source patch."),
        "write_file": ("edit", "Wrote a file", "The agent requested a file write."),
        "run_tests": ("check", "Ran tests", "The agent requested a test run."),
    }
    commands = {
        "ls": ("read", "Listed files"), "cat": ("read", "Read a file"),
        "sed": ("command", "Ran sed"), "rg": ("read", "Searched source text"),
        "grep": ("read", "Searched source text"), "find": ("read", "Located files"),
        "pytest": ("check", "Ran pytest"), "py.test": ("check", "Ran pytest"),
        "git": ("command", "Ran a Git command"), "python": ("command", "Ran Python"),
        "python3": ("command", "Ran Python"), "make": ("command", "Ran make"),
        "npm": ("command", "Ran npm"), "cargo": ("command", "Ran Cargo"),
        "go": ("command", "Ran Go"),
    }
    result = []
    for call in calls:
        name = call.get("function_name") or call.get("name")
        if isinstance(name, str) and name in tool_labels:
            kind, title, detail = tool_labels[name]
        elif _command_tool(call):
            kind, title = "command", "Submitted a terminal command"
            args = call.get("arguments")
            command = args.get("command", args.get("cmd")) if isinstance(args, dict) else None
            if isinstance(command, str) and len(command) < 100_000:
                try:
                    words = shlex.split(command)
                except ValueError:
                    words = []
                if words and words[0] in commands:
                    kind, title = commands[words[0]]
            detail = "The recorded tool call submitted a command to the terminal."
        else:
            # Unknown tool names are not safe display text and supply no
            # trusted classification. Their omission is counted separately.
            continue
        result.append({"kind": kind, "title": title, "detail": detail, "status": "recorded"})
        if len(result) > MAX_STEPS:
            raise DataError("trajectory exceeds the publication action bound")
    return result


def _published_groups(day):
    _date(day.get("date"))
    groups = {}
    rows = day.get("leaderboard")
    if not isinstance(rows, list):
        raise DataError("published day has no leaderboard")
    for row in rows:
        if not isinstance(row, dict):
            raise DataError("invalid leaderboard row")
        model = _text(row.get("model"), "model")
        for scaffold, item in row.items():
            if not isinstance(item, dict) or "n" not in item:
                continue
            n, solved = item.get("n"), item.get("solved")
            if type(n) is not int or type(solved) is not int or not 0 <= solved <= n:
                raise DataError("invalid published count")
            key = (model, _text(scaffold, "scaffold"))
            if key in groups:
                raise DataError("duplicate published model/scaffold")
            groups[key] = (solved, n)
    if not groups:
        raise DataError("published day has no scored groups")
    return groups


def _known_cells(day):
    """Read existing exact public cells, including non-default settings."""
    matrices = day.get("matrices", {})
    if not isinstance(matrices, dict):
        raise DataError("matrices must be an object")
    candidates = list(matrices.values())
    if day.get("matrix") is not None:
        candidates.append(day["matrix"])
    cells = {}
    for mx in candidates:
        if not isinstance(mx, dict):
            raise DataError("invalid matrix")
        scaffold = _text(mx.get("scaffold"), "matrix scaffold")
        tasks = mx.get("tasks")
        if not isinstance(tasks, list) or any(not isinstance(task, str) for task in tasks) or len(set(tasks)) != len(tasks):
            raise DataError("invalid matrix tasks")
        seen_models = set()
        for row in mx.get("rows", []):
            if not isinstance(row, dict) or not isinstance(row.get("model"), str) or row["model"] in seen_models:
                raise DataError("invalid or duplicate matrix model")
            seen_models.add(row["model"])
            grid = row.get("g")
            if not isinstance(grid, list) or len(grid) != len(tasks):
                raise DataError("invalid matrix row")
            for task, outcome in zip(tasks, grid):
                if outcome is None:
                    continue
                if type(outcome) is not int or outcome not in (0, 1):
                    raise DataError("non-binary matrix observation")
                key = (row["model"], scaffold, task)
                if key in cells and cells[key] != outcome:
                    raise DataError("conflicting public matrices")
                cells[key] = outcome
    return cells


def attach_repeat_trials(published_day, details):
    """Attach aligned rounds after exact public identity and score validation.

    Only ``matrix.rows[].trials`` and ``matrices.*.rows[].trials`` are added.
    Every existing score and metadata field is preserved. A round is the same
    recorded attempt index across the matrix's tasks; it does not imply a shared
    random seed. Missing matrix observations remain null in every round.
    """
    expected = _published_groups(published_day)
    known = _known_cells(published_day)
    if (not isinstance(details, dict) or details.get("schema") != "tdb-run-details-v1"
            or details.get("date") != published_day["date"]):
        raise DataError("run details do not identify the published day")
    aggregation = details.get("aggregation")
    if (not isinstance(aggregation, dict) or aggregation.get("unit") != "attempt"
            or aggregation.get("published_outcome") != "strict_majority"):
        raise DataError("run details require the strict-majority attempt contract")
    count = aggregation.get("trials_per_cell")
    if type(count) is not int or not 1 <= count <= MAX_STEPS:
        raise DataError("run details require a bounded positive trial count")
    published_aggregation = published_day.get("aggregation", {})
    if not isinstance(published_aggregation, dict):
        raise DataError("invalid published aggregation metadata")
    declared = published_aggregation.get("trials_per_cell")
    if declared is not None and (type(declared) is not int or declared != count):
        raise DataError("run details disagree with the published trial count")
    runs = details.get("runs")
    if not isinstance(runs, list) or not runs:
        raise DataError("run details require complete observed attempts")
    cells = collections.defaultdict(dict)
    for run in runs:
        if not isinstance(run, dict):
            raise DataError("invalid public attempt")
        if run.get("unobserved", False) is not False or run.get("observed", True) is not True:
            raise DataError("unobserved attempts cannot establish repeat variation")
        key = tuple(_text(run.get(field), field) for field in ("model", "scaffold", "task_id"))
        if key not in known:
            raise DataError("run details include a cell absent from the published matrices")
        index = run.get("attempt_index")
        if (type(index) is not int or not 0 <= index < count
                or type(run.get("trial_count")) is not int or run["trial_count"] != count):
            raise DataError("public attempt has an invalid trial index or count")
        if run.get("id") != run_id(published_day["date"], key[2], key[0], key[1], index):
            raise DataError("public attempt identity does not match its run id")
        if index in cells[key]:
            raise DataError("duplicate public attempt")
        outcome = run.get("outcome")
        if type(outcome) is not int or outcome not in (0, 1):
            raise DataError("public attempt requires a binary observed outcome")
        if type(run.get("cell_outcome")) is not int or run["cell_outcome"] != known[key]:
            raise DataError("public attempt disagrees with its published cell")
        cells[key][index] = outcome
    if cells.keys() != known.keys() or any(set(row) != set(range(count)) for row in cells.values()):
        raise DataError("run details omit published cells or complete trial sequences")
    computed = {key: [0, 0] for key in expected}
    for key, trials in cells.items():
        outcome = int(sum(trials.values()) * 2 > count)
        if outcome != known[key]:
            raise DataError("repeated outcomes disagree with the published matrix majority")
        if key[:2] not in computed:
            raise DataError("published matrix group is absent from the leaderboard")
        computed[key[:2]][0] += outcome
        computed[key[:2]][1] += 1
    if {key: tuple(value) for key, value in computed.items()} != expected:
        raise DataError("run details disagree with the published aggregates")

    day = copy.deepcopy(published_day)
    matrices = list(day.get("matrices", {}).values())
    if day.get("matrix") is not None:
        matrices.append(day["matrix"])
    for matrix in matrices:
        for row in matrix.get("rows", []):
            keys = [(row["model"], matrix["scaffold"], task) for task in matrix["tasks"]]
            if any(value is None and key in known for value, key in zip(row["g"], keys)):
                raise DataError("conflicting missing observations in public matrices")
            trials = [[cells[key][index] if value is not None else None
                       for key, value in zip(keys, row["g"])] for index in range(count)]
            if "trials" in row:
                recorded = row["trials"]
                if (not isinstance(recorded, list)
                        or any(not isinstance(round_, list) or any(
                            value is not None and type(value) is not int for value in round_
                        ) for round_ in recorded) or recorded != trials):
                    raise DataError("existing repeat trials disagree with public attempts")
            row["trials"] = trials
    return day


def board_from_eval_results(records, *, excluded_specs=()):
    """Adapt persisted clean-pipeline eval.json rows without changing outcomes.

    Publication still passes through reconstruct_board's complete-trial and
    exact-score checks. This adapter never turns advisory scores into rewards.
    Explicit exclusions use the same model-spec boundary as board inputs and
    do not determine the included population's trial count.
    """
    if not isinstance(records, list) or not records:
        raise DataError("eval results require a nonempty array")
    rows, cells = [], collections.Counter()
    excluded = set(excluded_specs)
    for record in records:
        if not isinstance(record, dict):
            raise DataError("invalid eval result")
        row = {key: record.get(key) for key in ("task_id", "model", "scaffold", "trial", "reward", "passed", "cost_s")}
        if _text(row["model"], "source model") in excluded:
            rows.append(row)
            continue
        if record.get("gated_by_exec") is not True:
            raise DataError("eval result lacks explicit execution provenance")
        cert = record.get("cert", {})
        if not isinstance(cert, dict):
            raise DataError("eval result certificate must be an object")
        if cert.get("reward_parsed") is False:
            raise DataError("eval result has no parsed execution reward")
        row["unobserved"] = bool(cert.get("verdict_unobserved"))
        harness = record.get("harness", {})
        if not isinstance(harness, dict):
            raise DataError("eval result harness must be an object")
        row["harness"] = {key: harness.get(key) for key in (
            "trajectory_complete", "n_command_calls", "n_tool_calls")}
        identity = tuple(_text(row[key], key) for key in ("task_id", "model", "scaffold"))
        cells[identity] += 1
        rows.append(row)
    counts = set(cells.values())
    if len(counts) != 1:
        raise DataError("included eval results require one nonempty trial count")
    return {"n_trials": counts.pop(), "results": rows}


def reconstruct_board(published_day, board, *, excluded_specs=(), telemetry=None):
    """Recover cells and attempts only when every published aggregate matches.

    ``telemetry`` is keyed by the stable public run id; callers must bind each
    telemetry record to the same source attempt before supplying it. Only final,
    complete telemetry is accepted. A partial gateway snapshot is not a total.
    """
    expected = _published_groups(published_day)
    date = published_day["date"]
    rows = board.get("results") if isinstance(board, dict) else None
    if not isinstance(rows, list) or not rows:
        raise DataError("board requires nonempty results")
    excluded = set(excluded_specs)
    observed_exclusions = collections.Counter()
    cells = collections.defaultdict(list)
    attempts_seen = set()
    for source in rows:
        if not isinstance(source, dict):
            raise DataError("invalid board row")
        spec = _text(source.get("model"), "source model")
        if spec in excluded:
            observed_exclusions[spec] += 1
            continue
        if source.get("unobserved") is not False:
            raise DataError("unobserved or ambiguous attempt cannot become a score")
        model, separator, effort = spec.rpartition("@")
        if not separator:
            model, effort = spec, ""
        agent = _text(source.get("scaffold"), "source scaffold")
        scaffold = agent + ("@" + effort if effort else "")
        if (model, scaffold) not in expected:
            raise DataError("source model/scaffold is not published or explicitly excluded")
        task = _text(source.get("task_id", source.get("task")), "task")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", task):
            raise DataError("task identifiers must be public slugs, not paths or prose")
        attempt = _number(source.get("trial"), integer=True)
        if attempt is None:
            raise DataError("attempt index is required")
        key = (model, scaffold, task)
        if (*key, attempt) in attempts_seen:
            raise DataError("duplicate attempt; retries cannot silently overwrite")
        attempts_seen.add((*key, attempt))
        passed = source.get("passed")
        if type(passed) is not bool:
            raise DataError("attempt requires an explicit boolean outcome")
        reward = source.get("reward")
        if type(reward) not in (int, float) or reward not in (0, 1) or bool(reward) != passed:
            raise DataError("reward and outcome disagree")
        cells[key].append((attempt, source))
    if excluded - observed_exclusions.keys():
        raise DataError("an exclusion was requested but is absent from the source")
    known = _known_cells(published_day)
    computed = collections.defaultdict(lambda: [0, 0])
    cell_outcomes = {}
    trial_counts = set()
    for key, attempts in cells.items():
        indices = sorted(index for index, _ in attempts)
        if indices != list(range(len(attempts))):
            raise DataError("attempt indices must form a complete sequence")
        trial_counts.add(len(attempts))
        outcome = int(sum(int(r["passed"]) for _, r in attempts) * 2 > len(attempts))
        if key in known and known[key] != outcome:
            raise DataError("recovered cell disagrees with the published matrix")
        cell_outcomes[key] = outcome
        computed[key[:2]][0] += outcome
        computed[key[:2]][1] += 1
    if {key: tuple(value) for key, value in computed.items()} != expected:
        raise DataError("source board does not exactly reproduce every published aggregate")
    observed_axes = {"n_cells": len(cells), "n_tasks": len({key[2] for key in cells}),
                     "n_models": len({key[0] for key in cells})}
    for field, actual in observed_axes.items():
        if field in published_day and published_day[field] != actual:
            raise DataError("recovered population disagrees with published dimensions")
    if set(known) - cells.keys():
        raise DataError("source omits published matrix cells")
    declared_trials = board.get("n_trials")
    if type(declared_trials) is not int or trial_counts != {declared_trials}:
        raise DataError("observed trial counts disagree with the source trial count")
    runs = []
    supplied = telemetry or {}
    for (model, scaffold, task), attempts in sorted(cells.items()):
        for attempt, source in sorted(attempts):
            rid = run_id(date, task, model, scaffold, attempt)
            extra = supplied.get(rid, {})
            if not isinstance(extra, dict) or (extra and extra.get("complete") is not True):
                raise DataError("telemetry is not bound to a complete attempt")
            if extra.get("trajectory_complete") is False and any(extra.get(key) is not None for key in (
                    "trajectory", "command_count", "tool_call_count", "n_command_calls", "n_tool_calls")):
                raise DataError("partial trajectory cannot establish call counts")
            wall = _number(source.get("cost_s"))
            steps = safe_steps(extra.get("trajectory"))
            commands, tools = trajectory_counts(extra.get("trajectory"))
            recorded_commands = _bound_metric(extra, source, "command_count", "n_command_calls", integer=True)
            recorded_tools = _bound_metric(extra, source, "tool_call_count", "n_tool_calls", integer=True)
            if extra.get("trajectory") is not None:
                if ((recorded_commands is not None and recorded_commands != commands)
                        or (recorded_tools is not None and recorded_tools != tools)):
                    raise DataError("recorded counts disagree with trajectory")
            else:
                commands, tools = recorded_commands, recorded_tools
            if commands is not None and tools is not None and commands > tools:
                raise DataError("command count exceeds total tool calls")
            run = {"id": rid, "task_id": task, "model": model, "scaffold": scaffold,
                "attempt_index": attempt, "trial_count": declared_trials,
                "outcome": int(source["passed"]), "cell_outcome": cell_outcomes[(model, scaffold, task)],
                "cost_usd": _bound_metric(extra, source, "cost_usd"), "wall_sec": wall,
                "command_count": commands, "tool_call_count": tools,
                "input_tokens": _bound_metric(extra, source, "input_tokens", "prompt_tokens", integer=True),
                "output_tokens": _bound_metric(extra, source, "output_tokens", "completion_tokens", integer=True),
                "steps": steps,
                "replay_status": "available" if steps else "unavailable"}
            runs.append(run)
    if set(supplied) - {r["id"] for r in runs}:
        raise DataError("telemetry includes an unpublished attempt")
    tasks = sorted({key[2] for key in cells})
    matrices = {}
    for scaffold in sorted({key[1] for key in cells}):
        models = sorted({key[0] for key in cells if key[1] == scaffold})
        matrices[scaffold] = {"scaffold": scaffold, "tasks": tasks, "rows": [
            {"model": model, "g": [cell_outcomes.get((model, scaffold, task)) for task in tasks]}
            for model in models]}
    def preferred(scaffold):
        effort = scaffold.rpartition("@")[2]
        rank = EFFORT_ORDER.index(effort) if effort in EFFORT_ORDER else -1
        return (len(matrices[scaffold]["rows"]), rank, scaffold)
    primary = max(matrices, key=preferred)
    day = copy.deepcopy(published_day)
    day.update({"matrices": matrices, "matrix": matrices[primary],
        "aggregation": {"method": "strict_majority", "unit": "task",
                        "trials_per_cell": declared_trials},
        "suite": {**day.get("suite", {}), "id": date, "task_ids": tasks, "n_tasks": len(tasks)}})
    coverage = {"published_cells": len(cells), "matched_runs": len(runs),
        "cost_runs": sum(r["cost_usd"] is not None for r in runs),
        "wall_runs": sum(r["wall_sec"] is not None for r in runs),
        "command_runs": sum(r["command_count"] is not None for r in runs),
        "tool_call_runs": sum(r["tool_call_count"] is not None for r in runs),
        "token_runs": sum(r["input_tokens"] is not None and r["output_tokens"] is not None for r in runs),
        "replay_runs": sum(bool(r["steps"]) for r in runs)}
    details = {"schema": "tdb-run-details-v1", "date": date, "runs": runs,
        "aggregation": {"unit": "attempt", "published_outcome": "strict_majority",
                        "trials_per_cell": declared_trials}, "coverage": coverage,
        "availability": {"cost_usd": "measured" if coverage["cost_runs"] else "unavailable",
                         "wall_sec": "measured" if coverage["wall_runs"] else "unavailable",
                         "command_count": "measured" if coverage["command_runs"] else "unavailable",
                         "tool_call_count": "measured" if coverage["tool_call_runs"] else "unavailable",
                         "tokens": "measured" if coverage["token_runs"] else "unavailable",
                         "replay": "available" if coverage["replay_runs"] else "unavailable"}}
    day = attach_repeat_trials(day, details)
    audit = {"aggregate_groups_verified": len(expected), "cells_verified": len(cells),
             "attempts_preserved": len(runs), "excluded_specs": dict(observed_exclusions),
             "default_scaffold": primary, "coverage": coverage}
    return day, details, audit


def empty_details(day):
    """Explicit unavailable state for a day with no recovered, bound source."""
    return {"schema": "tdb-run-details-v1", "date": _date(day["date"]), "runs": [],
            "coverage": {"published_cells": day.get("n_cells"), "matched_runs": 0,
                         "cost_runs": 0, "wall_runs": 0, "command_runs": 0, "tool_call_runs": 0,
                         "token_runs": 0, "replay_runs": 0},
            "availability": {"cost_usd": "unavailable", "wall_sec": "unavailable",
                             "command_count": "unavailable", "tool_call_count": "unavailable",
                             "tokens": "unavailable", "replay": "unavailable"}}


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")


def publish_details(directory, documents):
    """Write date-wide efficiency data and bounded task-view files together."""
    directory = Path(directory)
    dates = sorted(documents, reverse=True)
    task_files = {}
    for date in dates:
        _date(date)
        details = documents[date]
        if details.get("date") != date or details.get("schema") != "tdb-run-details-v1":
            raise DataError("run-details publication date or schema mismatch")
        by_task = collections.defaultdict(list)
        for run in details.get("runs", []):
            task = run.get("task_id")
            if not isinstance(task, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", task):
                raise DataError("invalid task slug in run-details publication")
            by_task[task].append(run)
        write_json(directory / f"{date}.json", details)
        if by_task:
            task_files[date] = {}
        for task, runs in sorted(by_task.items()):
            relative = f"{date}/tasks/{task}.json"
            task_files[date][task] = relative
            document = {**details, "task_id": task, "runs": runs,
                "coverage": {"published_cells": len({(r["model"], r["scaffold"]) for r in runs}),
                    "matched_runs": len(runs), "cost_runs": sum(r["cost_usd"] is not None for r in runs),
                    "wall_runs": sum(r["wall_sec"] is not None for r in runs),
                    "command_runs": sum(r.get("command_count") is not None for r in runs),
                    "tool_call_runs": sum(r.get("tool_call_count") is not None for r in runs),
                    "token_runs": sum(r["input_tokens"] is not None and r["output_tokens"] is not None for r in runs),
                    "replay_runs": sum(bool(r["steps"]) for r in runs)}}
            document["availability"] = {
                "cost_usd": "measured" if document["coverage"]["cost_runs"] else "unavailable",
                "wall_sec": "measured" if document["coverage"]["wall_runs"] else "unavailable",
                "command_count": "measured" if document["coverage"]["command_runs"] else "unavailable",
                "tool_call_count": "measured" if document["coverage"]["tool_call_runs"] else "unavailable",
                "tokens": "measured" if document["coverage"]["token_runs"] else "unavailable",
                "replay": "available" if document["coverage"]["replay_runs"] else "unavailable"}
            write_json(directory / relative, document)
    index = {"schema": "tdb-run-details-index-v1", "dates": dates, "task_files": task_files}
    write_json(directory / "index.json", index)
    return index


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--published", type=Path, required=True)
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--board", type=Path)
    sources.add_argument("--eval-results", type=Path,
                         help="persisted clean-pipeline eval.json; requires exact published majority parity")
    parser.add_argument("--exclude-spec", action="append", default=[])
    parser.add_argument("--telemetry", type=Path,
                        help="externally audited complete-attempt telemetry keyed by stable public run id")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--day-out", type=Path, required=True)
    parser.add_argument("--audit-out", type=Path, required=True)
    parser.add_argument("--publish-dir", type=Path,
                        help="also update full-date and per-task files plus their index in this directory")
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    source_path = args.board or args.eval_results
    private_paths = [source_path, args.audit_out] + ([args.telemetry] if args.telemetry else [])
    if any(path.resolve().is_relative_to(repo) for path in private_paths):
        parser.error("raw board/eval inputs and private provenance audits must stay outside the public checkout")
    published = json.loads(args.published.read_text(encoding="utf-8"))
    board = json.loads(source_path.read_text(encoding="utf-8"))
    if args.eval_results:
        board = board_from_eval_results(board, excluded_specs=args.exclude_spec)
    telemetry = json.loads(args.telemetry.read_text(encoding="utf-8")) if args.telemetry else None
    day, details, audit = reconstruct_board(published, board, excluded_specs=args.exclude_spec, telemetry=telemetry)
    audit["sources"] = [{"path": str(p.resolve()), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                        for p in [args.published, source_path] + ([args.telemetry] if args.telemetry else [])]
    write_json(args.day_out, day)
    write_json(args.out, details)
    write_json(args.audit_out, audit)
    if args.publish_dir:
        documents = {}
        index_path = args.publish_dir / "index.json"
        if index_path.exists():
            index = json.loads(index_path.read_text(encoding="utf-8"))
            for date in index["dates"]:
                documents[_date(date)] = json.loads((args.publish_dir / f"{date}.json").read_text(encoding="utf-8"))
        documents[details["date"]] = details
        publish_details(args.publish_dir, documents)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
