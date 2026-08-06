"""Pluggable harness registry; adapters never own reward interpretation."""
from __future__ import annotations

from typing import Type

from .base import AdapterResult, HarborRunSpec, HarnessAdapter
from .single_shot import SingleShotAdapter
from .terminus import TerminusAdapter
from .vendor import ClaudeCodeAdapter, CodexAdapter, Terminus2Adapter


REGISTRY: dict[str, Type[HarnessAdapter]] = {}
_ALIASES: dict[str, str] = {}


def register_adapter(adapter: Type[HarnessAdapter], *aliases: str) -> None:
    """Register an adapter class and optional spellings.

    This intentionally stays tiny: downstream packages can register another
    adapter without editing the runner or the protected-test gate.
    """
    name = adapter.name
    if not name or name == "base":
        # Vendor classes set ``name`` on their declarative spec.
        spec = getattr(adapter, "spec", None)
        name = getattr(spec, "name", "")
    if not name:
        raise ValueError("adapter must declare a non-empty name")
    REGISTRY[name] = adapter
    _ALIASES[name.replace("-", "_")] = name
    for alias in (*getattr(getattr(adapter, "spec", None), "aliases", ()), *aliases):
        _ALIASES[alias] = name


def create_adapter(name: str) -> HarnessAdapter:
    normalized = (name or "").strip().lower()
    canonical = _ALIASES.get(normalized, normalized)
    try:
        adapter = REGISTRY[canonical]
    except KeyError as exc:
        choices = ", ".join(sorted(REGISTRY))
        raise ValueError(f"unknown harness {name!r}; choose one of: {choices}") from exc
    return adapter()


for _adapter in (
    SingleShotAdapter,
    TerminusAdapter,
    Terminus2Adapter,
    ClaudeCodeAdapter,
    CodexAdapter,
):
    register_adapter(_adapter)


__all__ = [
    "HarnessAdapter",
    "AdapterResult",
    "HarborRunSpec",
    "SingleShotAdapter",
    "TerminusAdapter",
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "Terminus2Adapter",
    "REGISTRY",
    "create_adapter",
    "register_adapter",
]
