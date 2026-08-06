"""Execution-replay scoring contract (gate-free, releasable).

A model/scaffold produces a candidate repo state (a patch, or an agent run); the
REWARD is always the outcome of harbor RE-LAYING the trusted, protected tests on a
face the candidate never touched, read by ``harbor_score.read_harbor_reward``. No
submitted claim becomes a score without replay. Semantic verifier false-accept is
not implied by that fact and remains unmeasured without labeled exploit trials.
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
    """Compatibility integrity block, explicitly scoped to replay bypass.

    ``false_accept`` remains for old consumers and means only that a reward claim
    did not bypass protected-test replay. Semantic verifier error is ``None``.
    """
    return {
        "gate": "harbor_protected_tests",
        "reward_source": "result.json via harbor_score.read_harbor_reward",
        "protected_tests_relaid_by_harbor": True,
        "model_is_judge": False,
        "model_patch_touched_tests": bool(model_patch_touched_tests),
        "scope": "protected_test_replay_integrity",
        "claim_acceptance_without_replay": False,
        "semantic_false_accept": None,
        "false_accept": 0,
    }
