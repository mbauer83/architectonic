"""AllowedBindingsSpec — module-declared binding admissibility rules.

Diagram modules declare which correspondence kinds, target forms, and (for entity
types) visual roles are valid per diagram entity type and connection type.  The
loader validates that each entry's default_correspondence_kind is a member of its
own correspondence_kinds list.

Phase 3 will add the connection-path target form; that form is not parsed yet.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from src.domain.diagrams.bindings import CORE_CORRESPONDENCE_KINDS


@dataclass(frozen=True)
class EntityBindingSpec:
    """Declared binding admissibility for one diagram entity type."""

    correspondence_kinds: tuple[str, ...]
    default_correspondence_kind: str
    target_forms: tuple[str, ...]  # entity-id | connection-id | connection-ids | diagram-local
    visual_roles: tuple[str, ...] = ()  # empty = duplicate represents forbidden


@dataclass(frozen=True)
class ConnectionBindingSpec:
    """Declared binding admissibility for one diagram connection type."""

    target_connection_types: tuple[str, ...]
    target_connection_classes: tuple[str, ...]
    correspondence_kinds: tuple[str, ...]
    target_forms: tuple[str, ...]
    default_correspondence_kind: str


@dataclass(frozen=True)
class AllowedBindingsSpec:
    """Module-level binding admissibility constraints for a diagram type."""

    entity: dict[str, EntityBindingSpec] = field(default_factory=dict)
    connection: dict[str, ConnectionBindingSpec] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> AllowedBindingsSpec:
        return cls(entity={}, connection={})

    def is_empty(self) -> bool:
        return not self.entity and not self.connection

    def allowed_entity_kinds(self, entity_type: str) -> frozenset[str] | None:
        """Return allowed correspondence kinds for an entity type, or None if not declared."""
        spec = self.entity.get(entity_type)
        return frozenset(spec.correspondence_kinds) if spec is not None else None

    def allowed_connection_kinds(self, connection_type: str) -> frozenset[str] | None:
        """Return allowed correspondence kinds for a connection type, or None if not declared."""
        spec = self.connection.get(connection_type)
        return frozenset(spec.correspondence_kinds) if spec is not None else None

    def visual_roles_for(self, entity_type: str) -> tuple[str, ...]:
        """Return declared visual roles for an entity type (empty = duplicate represents forbidden)."""
        spec = self.entity.get(entity_type)
        return spec.visual_roles if spec is not None else ()


def _parse_entity_binding_spec(etype: str, cfg: Mapping[str, Any]) -> EntityBindingSpec:
    kinds = tuple(str(k) for k in (cfg.get("correspondence_kinds") or []))
    default_kind = str(cfg.get("default_correspondence_kind") or "")
    if default_kind not in kinds:
        raise ValueError(
            f"allowed_bindings.entity.{etype}: default_correspondence_kind "
            f"'{default_kind}' is not in correspondence_kinds {kinds}"
        )
    return EntityBindingSpec(
        correspondence_kinds=kinds,
        default_correspondence_kind=default_kind,
        target_forms=tuple(str(f) for f in (cfg.get("target_forms") or [])),
        visual_roles=tuple(str(r) for r in (cfg.get("visual_roles") or [])),
    )


def _parse_connection_binding_spec(ctype: str, cfg: Mapping[str, Any]) -> ConnectionBindingSpec:
    kinds = tuple(str(k) for k in (cfg.get("correspondence_kinds") or []))
    default_kind = str(cfg.get("default_correspondence_kind") or "")
    if default_kind not in kinds:
        raise ValueError(
            f"allowed_bindings.connection.{ctype}: default_correspondence_kind "
            f"'{default_kind}' is not in correspondence_kinds {kinds}"
        )
    return ConnectionBindingSpec(
        target_connection_types=tuple(str(t) for t in (cfg.get("target_connection_types") or [])),
        target_connection_classes=tuple(str(c) for c in (cfg.get("target_connection_classes") or [])),
        correspondence_kinds=kinds,
        target_forms=tuple(str(f) for f in (cfg.get("target_forms") or [])),
        default_correspondence_kind=default_kind,
    )


def allowed_bindings_from_config(raw: object) -> AllowedBindingsSpec:
    """Parse allowed_bindings from YAML config dict.

    Raises ValueError when any default_correspondence_kind is not in its own
    correspondence_kinds list — caught by the diagram module loader as a config error.
    """
    if not isinstance(raw, Mapping):
        return AllowedBindingsSpec.empty()

    entity_specs: dict[str, EntityBindingSpec] = {}
    raw_entity: object = raw.get("entity") or {}
    if isinstance(raw_entity, Mapping):
        for etype, cfg in raw_entity.items():
            if isinstance(cfg, Mapping):
                entity_specs[str(etype)] = _parse_entity_binding_spec(str(etype), cfg)

    connection_specs: dict[str, ConnectionBindingSpec] = {}
    raw_connection: object = raw.get("connection") or {}
    if isinstance(raw_connection, Mapping):
        for ctype, cfg in raw_connection.items():
            if isinstance(cfg, Mapping):
                connection_specs[str(ctype)] = _parse_connection_binding_spec(str(ctype), cfg)

    return AllowedBindingsSpec(entity=entity_specs, connection=connection_specs)


def serialize_allowed_bindings(spec: AllowedBindingsSpec) -> dict[str, object]:
    """Serialize AllowedBindingsSpec to a JSON-compatible dict for guidance output."""
    entity_out: dict[str, object] = {}
    for etype, espec in spec.entity.items():
        entry: dict[str, object] = {
            "correspondence_kinds": list(espec.correspondence_kinds),
            "default_correspondence_kind": espec.default_correspondence_kind,
            "target_forms": list(espec.target_forms),
        }
        if espec.visual_roles:
            entry["visual_roles"] = list(espec.visual_roles)
        entity_out[etype] = entry

    connection_out: dict[str, object] = {}
    for ctype, cspec in spec.connection.items():
        conn_entry: dict[str, object] = {
            "correspondence_kinds": list(cspec.correspondence_kinds),
            "default_correspondence_kind": cspec.default_correspondence_kind,
            "target_forms": list(cspec.target_forms),
        }
        if cspec.target_connection_types:
            conn_entry["target_connection_types"] = list(cspec.target_connection_types)
        if cspec.target_connection_classes:
            conn_entry["target_connection_classes"] = list(cspec.target_connection_classes)
        connection_out[ctype] = conn_entry

    return {"entity": entity_out, "connection": connection_out}


# Re-export for verifier convenience
__all__ = [
    "AllowedBindingsSpec",
    "EntityBindingSpec",
    "ConnectionBindingSpec",
    "allowed_bindings_from_config",
    "serialize_allowed_bindings",
    "CORE_CORRESPONDENCE_KINDS",
]
