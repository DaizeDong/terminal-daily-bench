"""terminal-daily-bench -- a living, execution-graded coding-agent benchmark.

Tasks are mined from real merged PRs every day; models are scored by protected-test
execution replay. A submitted claim cannot bypass replay; semantic verifier
false-accept remains an empirical quantity.
This package is the PUBLIC evaluation bundle -- it scores and submits; the daily
construction pipeline + acceptance gate that build the task set are private.

Public surface:
  harbor_score  -- gate-free reward reader (read_harbor_reward, ...)
  scoring       -- the protected-test replay contract over a task package
  quality       -- the multi-angle Selection-Quality (MSQ) instrument
  adapters      -- pluggable harness adapters (single-shot, terminus, ...)
  cli (`tdb`)   -- run / oracle / quality / submit
"""
__version__ = "0.1.0"

from . import harbor_score, quality, scoring  # noqa: F401

__all__ = ["harbor_score", "quality", "scoring", "__version__"]
