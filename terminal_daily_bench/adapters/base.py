"""adapters/base.py -- the HarnessAdapter contract.

Any coding-agent harness plugs in by implementing this contract:
    input  = (task dir, failing test ids, model id/endpoint)
    output = (unified diff, telemetry)
The execution gate stays the SOLE reward authority -- an adapter only produces a
candidate repo state; it never scores. This is what keeps false_accept = 0 as more
harnesses are added (single-shot, terminus, Claude Code, Aider, OpenHands, ...).
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AdapterResult:
    """What a harness returns for one (task, model) attempt."""
    patch: str                                  # unified diff the harness produced
    telemetry: Dict[str, Any] = field(default_factory=dict)  # tokens, cost_usd, turns, wall_s
    error: Optional[str] = None


class HarnessAdapter(abc.ABC):
    """A pluggable scaffold. Subclasses MUST NOT score -- they only produce a patch."""

    name: str = "base"

    @abc.abstractmethod
    def produce_patch(self, task_dir: str, failing_test_ids: List[str],
                      model: str, **kwargs: Any) -> AdapterResult:
        """Drive the harness on ``task_dir`` and return the candidate patch + telemetry.

        MUST NOT read or write the protected tests / the gold solution, and MUST NOT
        compute a reward. Scoring is done afterward by the execution gate.
        """
        raise NotImplementedError
