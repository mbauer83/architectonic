"""Domain model for concept-level specializations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Literal

ConceptKind = Literal["entity", "connection"]


@dataclass(frozen=True)
class SpecializationNotation:
    """Optional notation override carried by a specialization."""

    icon: str = ""
    color: str = ""
    line_style: str = ""
    label_marker: str = ""
    extras: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class RelationshipRestriction:
    """Entity-specialization allow-list entry for relationships involving the entity."""

    connection_type: str
    source_type: str | None = None
    target_type: str | None = None


@dataclass(frozen=True)
class EndpointRestriction:
    """Connection-specialization allow-list entry for permitted endpoints."""

    source_types: frozenset[str] = frozenset()
    target_types: frozenset[str] = frozenset()


@dataclass(frozen=True)
class SpecializationInfo:
    """One specialization of an entity or connection type."""

    slug: str
    name: str
    concept_kind: ConceptKind
    parent_type: str
    module_alias: str
    description: str = ""
    notation: SpecializationNotation = field(default_factory=SpecializationNotation)
    restrict_relationships: tuple[RelationshipRestriction, ...] = ()
    restrict_endpoints: tuple[EndpointRestriction, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)
    bound_profiles: tuple[str, ...] = ()
    """Names of reusable profiles this specialization binds, in declaration order (PLAN
    §3 P2). Resolution folds them between the base schema and this specialization's own
    profile. A name with no matching registry entry is a Class A structural error, checked
    at startup (WU-Q1) — never silently ignored here."""
    create_when: str = ""
    never_create_when: str = ""

    @property
    def key(self) -> tuple[str, ConceptKind, str, str]:
        return (self.module_alias, self.concept_kind, self.parent_type, self.slug)


@dataclass(frozen=True)
class SpecializationCatalog:
    """Immutable lookup for entity and connection specializations."""

    entries: tuple[SpecializationInfo, ...] = ()

    def __post_init__(self) -> None:
        seen: set[tuple[str, ConceptKind, str, str]] = set()
        for entry in self.entries:
            if entry.key in seen:
                module, kind, parent, slug = entry.key
                raise ValueError(
                    "Duplicate specialization "
                    f"{module}/{kind}/{parent}/{slug}; uniqueness is per module, concept kind, parent type, and slug"
                )
            seen.add(entry.key)

    def __or__(self, other: "SpecializationCatalog") -> "SpecializationCatalog":
        return SpecializationCatalog(self.entries + other.entries)

    def for_type(
        self,
        concept_kind: ConceptKind,
        parent_type: str,
        *,
        module_alias: str | None = None,
    ) -> tuple[SpecializationInfo, ...]:
        """Return all specializations declared for a parent concept type."""
        return tuple(
            entry
            for entry in self.entries
            if entry.concept_kind == concept_kind
            and entry.parent_type == parent_type
            and (module_alias is None or entry.module_alias == module_alias)
        )

    def get(
        self,
        concept_kind: ConceptKind,
        parent_type: str,
        slug: str,
        *,
        module_alias: str | None = None,
    ) -> SpecializationInfo | None:
        """Find one specialization by kind, parent type, and slug."""
        matches = [
            entry
            for entry in self.for_type(concept_kind, parent_type, module_alias=module_alias)
            if entry.slug == slug
        ]
        if len(matches) > 1:
            raise ValueError(
                f"Specialization lookup for {concept_kind}/{parent_type}/{slug} is ambiguous; "
                "pass module_alias"
            )
        return matches[0] if matches else None

    def validate_restriction_narrowing(
        self,
        *,
        parent_relationships: Mapping[tuple[str, str], frozenset[RelationshipRestriction]] | None = None,
        parent_endpoints: Mapping[tuple[str, str], frozenset[EndpointRestriction]] | None = None,
    ) -> tuple[str, ...]:
        """Validate specialization restrictions against parent allow-lists when supplied.

        The hook is intentionally pure and data-driven. Callers that know the parent
        metamodel rules pass those rules by ``(module_alias, parent_type)``; absent parent
        entries mean the parent is unrestricted for that axis, so any specialization
        restriction is a narrowing.
        """
        relationship_rules = parent_relationships or {}
        endpoint_rules = parent_endpoints or {}
        issues: list[str] = []
        for entry in self.entries:
            parent_key = (entry.module_alias, entry.parent_type)
            allowed_relationships = relationship_rules.get(parent_key)
            if allowed_relationships is not None:
                for restriction in entry.restrict_relationships:
                    if not any(
                        _relationship_restriction_narrows(restriction, parent)
                        for parent in allowed_relationships
                    ):
                        issues.append(
                            f"{_label(entry)} restrict_relationships entry {restriction!r} is not permitted by parent"
                        )
            allowed_endpoints = endpoint_rules.get(parent_key)
            if allowed_endpoints is not None:
                for restriction in entry.restrict_endpoints:
                    if not any(_endpoint_restriction_narrows(restriction, parent) for parent in allowed_endpoints):
                        issues.append(
                            f"{_label(entry)} restrict_endpoints entry {restriction!r} is not permitted by parent"
                        )
        return tuple(issues)

    @staticmethod
    def empty() -> "SpecializationCatalog":
        return SpecializationCatalog()


def merge_specialization_catalogs(*catalogs: SpecializationCatalog) -> SpecializationCatalog:
    entries: list[SpecializationInfo] = []
    for catalog in catalogs:
        entries.extend(catalog.entries)
    return SpecializationCatalog(tuple(entries))


def overlay_specialization_guidance(
    catalog: SpecializationCatalog,
    entries: Mapping[tuple[str, ConceptKind, str, str], tuple[str, str]],
) -> SpecializationCatalog:
    """Return a catalog with create/never guidance overlaid by specialization key."""
    overlaid: list[SpecializationInfo] = []
    for entry in catalog.entries:
        guidance = entries.get(entry.key)
        if guidance is None:
            overlaid.append(entry)
        else:
            create_when, never_create_when = guidance
            overlaid.append(replace(entry, create_when=create_when, never_create_when=never_create_when))
    return SpecializationCatalog(tuple(overlaid))


def specialization_infos_from_mapping(data: Mapping[str, Any], *, module_alias: str) -> tuple[SpecializationInfo, ...]:
    """Parse the ``specializations: {entity: ..., connection: ...}`` YAML shape."""
    root = data.get("specializations")
    if not isinstance(root, Mapping):
        return ()

    entries: list[SpecializationInfo] = []
    concept_kinds: tuple[ConceptKind, ...] = ("entity", "connection")
    for concept_kind in concept_kinds:
        section = root.get(concept_kind)
        if not isinstance(section, Mapping):
            continue
        for parent_type, raw_items in section.items():
            if not isinstance(parent_type, str) or not isinstance(raw_items, (list, tuple)):
                continue
            for raw_item in raw_items:
                if isinstance(raw_item, Mapping):
                    entries.append(_info_from_mapping(raw_item, concept_kind, parent_type, module_alias))
    return tuple(entries)


def specialization_catalog_from_mapping(data: Mapping[str, Any], *, module_alias: str) -> SpecializationCatalog:
    """Parse specializations and return a validating catalog."""
    return SpecializationCatalog(specialization_infos_from_mapping(data, module_alias=module_alias))


def _info_from_mapping(
    raw: Mapping[str, Any],
    concept_kind: ConceptKind,
    parent_type: str,
    module_alias: str,
) -> SpecializationInfo:
    slug = str(raw["slug"])
    name = str(raw.get("name") or slug.replace("-", " ").title())
    return SpecializationInfo(
        slug=slug,
        name=name,
        concept_kind=concept_kind,
        parent_type=parent_type,
        module_alias=module_alias,
        description=str(raw.get("description") or ""),
        notation=_notation_from_mapping(raw.get("notation")),
        restrict_relationships=_relationship_restrictions(raw.get("restrict_relationships")),
        restrict_endpoints=_endpoint_restrictions(raw.get("restrict_endpoints")),
        attributes=_attributes_from_mapping(raw.get("attributes")),
        bound_profiles=_bound_profiles(raw.get("profiles")),
        create_when=str(raw.get("create_when") or ""),
        never_create_when=str(raw.get("never_create_when") or ""),
    )


def _notation_from_mapping(raw: object) -> SpecializationNotation:
    if not isinstance(raw, Mapping):
        return SpecializationNotation()
    known = {"icon", "color", "line_style", "label_marker"}
    return SpecializationNotation(
        icon=str(raw.get("icon") or ""),
        color=str(raw.get("color") or ""),
        line_style=str(raw.get("line_style") or ""),
        label_marker=str(raw.get("label_marker") or ""),
        extras=tuple(sorted((str(k), str(v)) for k, v in raw.items() if k not in known)),
    )


def _attributes_from_mapping(raw: object) -> Mapping[str, Any]:
    return dict(raw) if isinstance(raw, Mapping) else {}


def _bound_profiles(raw: object) -> tuple[str, ...]:
    """Named-profile bindings in declaration order, de-duplicated (a repeated name adds
    nothing). A non-list value yields no bindings."""
    if not isinstance(raw, (list, tuple)):
        return ()
    seen: dict[str, None] = {}
    for item in raw:
        seen.setdefault(str(item), None)
    return tuple(seen)


def _relationship_restrictions(raw: object) -> tuple[RelationshipRestriction, ...]:
    if not isinstance(raw, (list, tuple)):
        return ()
    restrictions: list[RelationshipRestriction] = []
    for item in raw:
        if isinstance(item, str):
            restrictions.append(RelationshipRestriction(connection_type=item))
        elif isinstance(item, Mapping):
            conn = item.get("connection_type") or item.get("type")
            if conn:
                restrictions.append(
                    RelationshipRestriction(
                        connection_type=str(conn),
                        source_type=_optional_str(item.get("source_type") or item.get("source")),
                        target_type=_optional_str(item.get("target_type") or item.get("target")),
                    )
                )
    return tuple(restrictions)


def _endpoint_restrictions(raw: object) -> tuple[EndpointRestriction, ...]:
    if not isinstance(raw, (list, tuple)):
        return ()
    restrictions: list[EndpointRestriction] = []
    for item in raw:
        if isinstance(item, Mapping):
            restrictions.append(
                EndpointRestriction(
                    source_types=_string_set(item.get("source_types") or item.get("sources") or item.get("source")),
                    target_types=_string_set(item.get("target_types") or item.get("targets") or item.get("target")),
                )
            )
    return tuple(restrictions)


def _string_set(raw: object) -> frozenset[str]:
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        return frozenset({raw})
    if isinstance(raw, (list, tuple, set, frozenset)):
        return frozenset(str(item) for item in raw)
    return frozenset()


def _optional_str(raw: object) -> str | None:
    return str(raw) if raw else None


def _label(entry: SpecializationInfo) -> str:
    return f"{entry.module_alias}/{entry.concept_kind}/{entry.parent_type}/{entry.slug}"


def _relationship_restriction_narrows(child: RelationshipRestriction, parent: RelationshipRestriction) -> bool:
    if child.connection_type != parent.connection_type:
        return False
    return _optional_value_narrows(child.source_type, parent.source_type) and _optional_value_narrows(
        child.target_type, parent.target_type
    )


def _optional_value_narrows(child: str | None, parent: str | None) -> bool:
    if parent is None:
        return True
    return child == parent


def _endpoint_restriction_narrows(child: EndpointRestriction, parent: EndpointRestriction) -> bool:
    return _set_narrows(child.source_types, parent.source_types) and _set_narrows(
        child.target_types,
        parent.target_types,
    )


def _set_narrows(child: frozenset[str], parent: frozenset[str]) -> bool:
    if not parent:
        return True
    return bool(child) and child <= parent
