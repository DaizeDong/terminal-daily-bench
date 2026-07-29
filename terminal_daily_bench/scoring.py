"""scoring.py -- the false_accept=0 scoring contract (gate-free, releasable).

A model/scaffold produces a candidate repo state (a patch, or an agent run); the
REWARD is always the outcome of harbor RE-LAYING the trusted, protected tests on a
face the candidate never touched, read by ``harbor_score.read_harbor_reward``. No
model ever scores itself -> false_accept = 0 by construction. This module is the
thin, public contract; the actual harbor invocation lives in ``eval`` / an adapter.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .harbor_score import read_harbor_reward


def score_from_jobs(jobs_dir: str) -> Optional[float]:
    """Reward for a completed harbor trial (its ``result.json`` under ``jobs_dir``).

    Returns the protected-test reward in [0,1], or None if unreadable. This is the
    SOLE reward authority -- a claimed reward is never trusted.
    """
    return read_harbor_reward(jobs_dir)


def false_accept_check(*, model_patch_touched_tests: bool = False) -> Dict[str, Any]:
    """The stamped integrity block: the reward came from re-laid protected tests,
    the model was never the judge, and it did not (effectively) edit the tests.
    ``false_accept`` is 0 by construction of execution scoring."""
    return {
        "gate": "harbor_protected_tests",
        "reward_source": "result.json via harbor_score.read_harbor_reward",
        "protected_tests_relaid_by_harbor": True,
        "model_is_judge": False,
        "model_patch_touched_tests": bool(model_patch_touched_tests),
        "false_accept": 0,
    }
