"""adapters/terminus.py -- multi-turn agent scaffold (integration stub).

A real multi-turn agent (terminus-2 / Claude Code / Aider / OpenHands / SWE-agent)
drives a shell in the task container over many turns, then the gate re-lays the
protected tests. Any harness that accepts a custom OpenAI base URL drives an
arbitrary model unchanged. This stub documents the contract; wire your harness'
CLI here (see CONTRIBUTING.md / docs/submission.md).
"""
from __future__ import annotations

from typing import Any, List

from .base import AdapterResult, HarnessAdapter


class TerminusAdapter(HarnessAdapter):
    name = "terminus"

    def produce_patch(self, task_dir: str, failing_test_ids: List[str],
                      model: str, **kwargs: Any) -> AdapterResult:
        return AdapterResult(patch="", error="terminus adapter not wired in this bundle; "
                             "implement produce_patch to drive your agent CLI (docs/submission.md)")
