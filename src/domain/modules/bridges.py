"""BridgeDeclaration — named cross-module type alignment with a checkable class-preservation claim.

A bridge is the evolution of permitted_mappings.sources: it carries an identity,
a version, and a preservation claim the registry can verify at startup.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BridgeDeclaration:
    """A named alignment between a diagram-owned entity type and model ontology types.

    Parsed from a ``bridges:`` list in a diagram module's ontology.yaml.
    """

    name: str
    version: int
    from_module: str          # diagram type name (matches declaring module)
    from_type: str            # diagram entity type name
    to_module: str            # ontology module name (must be registered)
    to_types: tuple[str, ...]  # entity types in to_module
    preserves_classes: tuple[str, ...]  # class preservation claim to check
    correspondence_kind: str  # must be a core or module-declared kind


def bridges_from_config(raw: object, *, declaring_module: str = "") -> tuple[BridgeDeclaration, ...]:
    """Parse bridge declarations from a YAML ``bridges:`` list.

    Returns an empty tuple for None, non-list, or an empty list.
    Skips entries that are not mappings.  ``declaring_module`` is used
    as the default ``from.module`` when the entry omits it.
    """
    if not isinstance(raw, list):
        return ()
    result: list[BridgeDeclaration] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        bridge = _bridge_from_mapping(item, declaring_module=declaring_module)
        if bridge is not None:
            result.append(bridge)
    return tuple(result)


def _bridge_from_mapping(item: Mapping[str, Any], *, declaring_module: str) -> BridgeDeclaration | None:
    from_spec: object = item.get("from") or {}
    to_spec: object = item.get("to") or {}
    if not isinstance(from_spec, Mapping) or not isinstance(to_spec, Mapping):
        return None
    name = str(item.get("name") or "")
    if not name:
        return None
    return BridgeDeclaration(
        name=name,
        version=int(item.get("version") or 1),
        from_module=str(from_spec.get("module") or declaring_module),
        from_type=str(from_spec.get("type") or ""),
        to_module=str(to_spec.get("module") or ""),
        to_types=tuple(str(t) for t in (to_spec.get("types") or [])),
        preserves_classes=tuple(str(c) for c in (item.get("preserves_classes") or [])),
        correspondence_kind=str(item.get("correspondence_kind") or ""),
    )
