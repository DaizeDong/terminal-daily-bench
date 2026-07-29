"""Pluggable harness adapters. The execution gate is always the sole reward authority."""
from .base import AdapterResult, HarnessAdapter
from .single_shot import SingleShotAdapter
from .terminus import TerminusAdapter

REGISTRY = {a.name: a for a in (SingleShotAdapter, TerminusAdapter)}
__all__ = ["HarnessAdapter", "AdapterResult", "SingleShotAdapter", "TerminusAdapter", "REGISTRY"]
