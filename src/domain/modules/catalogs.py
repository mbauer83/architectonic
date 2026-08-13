"""Focused injectable catalog Protocols and their ModuleCatalog-backed implementations.

Protocols (OntologyCatalog, ConnectionSemantics, DiagramTypeCatalog) live in the
domain layer; implementations are built at the composition root from a frozen
ModuleCatalog and injected into consumers.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from src.domain.modules.module_catalog import ModuleCatalog
from src.domain.modules.module_types import ConnectionTypeName, ElementClassName, EntityTypeName
from src.domain.ontology_representation.behavioral_elements import resolve_behavioral_types
from src.domain.ontology_representation.classification_levels import (
    ClassificationLevel,
    classification_levels_for,
)
from src.domain.ontology_representation.ontology_protocol import DiagramTypeModule, StoreGraphProjectingDiagramType
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, EntityTypeInfo
from src.domain.ontology_representation.relation_notation import DEFAULT_NOTATION
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet

# ── Protocols ─────────────────────────────────────────────────────────────────

@runtime_checkable
class OntologyCatalog(Protocol):
    """Read-only ontology data derived from the registered module catalog."""

    def all_entity_types(self) -> Mapping[str, EntityTypeInfo]: ...
    def all_connection_types(self) -> Mapping[str, ConnectionTypeInfo]: ...
    def all_entity_type_names(self) -> frozenset[str]: ...
    def all_connection_type_names(self) -> frozenset[str]: ...
    def known_domain_names(self) -> frozenset[str]: ...

    def behavioral_entity_types(self) -> frozenset[str]: ...
    def domain_appearance(self) -> Mapping[str, Mapping[str, str]]: ...
    def corner_by_entity_type(self) -> Mapping[str, str]: ...
    def de_emphasis_rule(self) -> Mapping[str, str]: ...
    def classification_levels(self) -> Mapping[str, Sequence[ClassificationLevel]]: ...
    def domain_order(self) -> Sequence[str]: ...
    def domain_grouping(self) -> Mapping[str, str]: ...
    def entity_types_with_class(self, element_class: str) -> frozenset[str]: ...
    def expand_entity_type_term(self, term: str) -> Sequence[str]: ...
    def format_entity_type_term(self, term: str) -> str: ...
    def entity_type_term_matches(self, term: str, linked_types: set[str]) -> bool: ...
    def archimate_stereotype_to_connection_type(self) -> Mapping[str, str]: ...
    def entity_type_prefixes(self) -> Mapping[str, str]: ...
    def matrix_abbreviations_by_connection_type(self) -> Mapping[str, str]: ...
    def matrix_connection_type_abbreviations(self) -> Mapping[str, str]: ...


@runtime_checkable
class ConnectionSemantics(Protocol):
    """Permitted-relationship and symmetry queries over registered ontologies."""

    def is_symmetric(self, conn_type: str) -> bool: ...
    def relationship_kind(self, conn_type: str) -> str | None: ...
    def relation_notation(self, conn_type: str) -> Mapping[str, str]: ...
    def all_relation_notations(self) -> Mapping[str, Mapping[str, str]]: ...
    def permissible_connection_types(self, source_type: str, target_type: str) -> Sequence[str]: ...
    def permissible_target_types(self, source_type: str) -> Mapping[str, Sequence[str]]: ...
    def classify_connections(self, source_type: str) -> Mapping[str, Mapping[str, Sequence[str]]]: ...


@runtime_checkable
class DiagramTypeCatalog(Protocol):
    """Diagram-type lookup and relation-label suppression logic."""

    def suppressed_stereotype_tokens(self) -> frozenset[str]: ...
    def diagram_type_domain(self, name: str) -> str | None: ...
    def get_diagram_type(self, name: str) -> DiagramTypeModule: ...
    def find_diagram_type(self, name: str) -> DiagramTypeModule | None: ...
    def all_diagram_types(self) -> Mapping[str, DiagramTypeModule]: ...
    def store_projected_diagram_types(self) -> frozenset[str]: ...


# ── Implementations ───────────────────────────────────────────────────────────

class OntologyCatalogImpl:
    """ModuleCatalog-backed OntologyCatalog.

    matrix_abbreviations: Mapping[abbrev → conn_type] — supplied at the
    composition root from the ontology package so that domain stays free of
    ontologies imports (resolves D8 when injected in Phase C/D).
    """

    def __init__(self, catalog: ModuleCatalog, matrix_abbreviations: Mapping[str, str]) -> None:
        self._catalog = catalog
        self._matrix_abbrevs: dict[str, str] = dict(matrix_abbreviations)

    @functools.cached_property
    def _et(self) -> dict[str, EntityTypeInfo]:
        return {str(n): info for n, info in self._catalog.all_entity_types().items()}

    @functools.cached_property
    def _behavioral_types(self) -> frozenset[str]:
        """Entity types that denote something which acts, across every registered ontology.

        Each ontology resolves against *its own* types, so one module's declaration can never claim a
        type belonging to another. Returned as type names, so callers never handle a class name — the
        vocabulary stays inside the ontology that owns it.
        """
        resolved: set[str] = set()
        for module in self._catalog.all_ontologies().values():
            classes_by_type = {
                str(name): [str(c) for c in info.classes]
                for name, info in module.entity_types.items()
            }
            resolved |= resolve_behavioral_types(classes_by_type, module.behavioral_elements)
        return frozenset(resolved)

    def behavioral_entity_types(self) -> frozenset[str]:
        return self._behavioral_types

    def domain_appearance(self) -> Mapping[str, Mapping[str, str]]:
        """Every domain's fill, border and container tint, from the ontology that owns the domain.

        Three values from the one declared colour, so a consumer cannot pick up a fill from here
        and a border from somewhere else — which is precisely what three hand-maintained palettes
        let every consumer do.
        """
        resolved: dict[str, dict[str, str]] = {}
        for module in self._catalog.all_ontologies().values():
            appearance = module.element_appearance
            for info in module.entity_types.values():
                domain = info.hierarchy[0] if info.hierarchy else "common"
                fill = appearance.color_for(domain)
                if fill and domain not in resolved:
                    resolved[domain] = {
                        "fill": fill,
                        "border": appearance.border_for(fill),
                        "container": appearance.de_emphasized(fill),
                    }
        return resolved

    def corner_by_entity_type(self) -> Mapping[str, str]:
        """Each entity type's corner style, resolved through the classes its ontology declares.

        Returned per *type* rather than per class, for the reason `behavioral_entity_types` is:
        the class vocabulary stays inside the ontology that owns it, and a renderer receives an
        answer it can draw.
        """
        return {
            str(name): module.element_appearance.corner_for(info.classes)
            for module in self._catalog.all_ontologies().values()
            for name, info in module.entity_types.items()
        }

    def de_emphasis_rule(self) -> Mapping[str, str]:
        """How a surface mutes a declared colour, from the ontology that declares it.

        The rule rather than a muted palette, because a second palette is how the three that
        disagreed came about. Empty where no ontology declares one — a client then leaves colours
        as they are rather than guessing at a grey.
        """
        for module in self._catalog.all_ontologies().values():
            rule = module.element_appearance.de_emphasis
            if rule.is_declared:
                return {"toward": rule.toward, "amount": str(rule.amount)}
        return {}

    def classification_levels(self) -> Mapping[str, Sequence[ClassificationLevel]]:
        """Each ontology module's entity classification ladder, declared or derived."""
        return {
            str(name): classification_levels_for(module)
            for name, module in self._catalog.all_ontologies().items()
        }

    @functools.cached_property
    def _ct(self) -> dict[str, ConnectionTypeInfo]:
        return {str(n): info for n, info in self._catalog.all_connection_types().items()}

    @functools.cached_property
    def _et_names(self) -> frozenset[str]:
        return frozenset(self._et)

    @functools.cached_property
    def _ct_names(self) -> frozenset[str]:
        return frozenset(self._ct)

    @functools.cached_property
    def _domain_names(self) -> frozenset[str]:
        domains = {info.hierarchy[0] for info in self._et.values() if info.hierarchy}
        return frozenset(domains | {"unknown"})

    @functools.cached_property
    def _domain_ord(self) -> list[str]:
        return self._catalog.domain_order()

    @functools.cached_property
    def _archimate_stereo_map(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for info in self._ct.values():
            if info.conn_lang == "archimate" and info.archimate_relationship_type is not None:
                result[info.archimate_relationship_type.lower()] = info.artifact_type
        return result

    @functools.cached_property
    def _et_prefix_map(self) -> dict[str, str]:
        return {info.prefix: at for at, info in self._et.items()}

    def all_entity_types(self) -> Mapping[str, EntityTypeInfo]:
        return self._et

    def all_connection_types(self) -> Mapping[str, ConnectionTypeInfo]:
        return self._ct

    def all_entity_type_names(self) -> frozenset[str]:
        return self._et_names

    def all_connection_type_names(self) -> frozenset[str]:
        return self._ct_names

    def known_domain_names(self) -> frozenset[str]:
        return self._domain_names

    def domain_order(self) -> Sequence[str]:
        return list(self._domain_ord)

    def domain_grouping(self) -> Mapping[str, str]:
        return {d: f"{d.capitalize()}Grouping" for d in self._domain_ord}

    def entity_types_with_class(self, element_class: str) -> frozenset[str]:
        raw = self._catalog.entity_types_with_class(ElementClassName(element_class))
        return frozenset(str(n) for n in raw)

    def expand_entity_type_term(self, term: str) -> Sequence[str]:
        if term == "@all":
            return sorted(self._et_names)
        if term.startswith("@"):
            return sorted(self.entity_types_with_class(term[1:]))
        return [term] if term in self._et_names else []

    def format_entity_type_term(self, term: str) -> str:
        if term == "@all":
            return "entity"
        normalized = term[1:] if term.startswith("@") else term
        return normalized.replace("-", " ").replace("_", " ")

    def entity_type_term_matches(self, term: str, linked_types: set[str]) -> bool:
        return bool(set(self.expand_entity_type_term(term)) & linked_types)

    def archimate_stereotype_to_connection_type(self) -> Mapping[str, str]:
        return self._archimate_stereo_map

    def entity_type_prefixes(self) -> Mapping[str, str]:
        return self._et_prefix_map

    def matrix_abbreviations_by_connection_type(self) -> Mapping[str, str]:
        return self._matrix_abbrevs

    def matrix_connection_type_abbreviations(self) -> Mapping[str, str]:
        return {ct: abbrev for abbrev, ct in self._matrix_abbrevs.items()}


class ConnectionSemanticsImpl:
    """ModuleCatalog-backed ConnectionSemantics."""

    def __init__(self, catalog: ModuleCatalog) -> None:
        self._catalog = catalog

    @functools.cached_property
    def _permitted(self) -> PermittedRelationshipSet:
        return self._catalog.aggregated_permitted_relationships()

    def is_symmetric(self, conn_type: str) -> bool:
        info = self._catalog.find_connection_type(ConnectionTypeName(conn_type))
        return info.symmetric if info is not None else False

    def relationship_kind(self, conn_type: str) -> str | None:
        info = self._catalog.find_connection_type(ConnectionTypeName(conn_type))
        return info.relationship_kind if info is not None else None

    def relation_notation(self, conn_type: str) -> Mapping[str, str]:
        """How this relationship is drawn — line style and the marker at each end.

        A type this catalog does not know still gets a notation: an unrecognised relationship
        should render as a plain directed line, not vanish from the picture.
        """
        info = self._catalog.find_connection_type(ConnectionTypeName(conn_type))
        return (info.notation if info is not None else DEFAULT_NOTATION).as_mapping()

    def all_relation_notations(self) -> Mapping[str, Mapping[str, str]]:
        """Every known relationship's notation, for renderers that style a whole graph.

        Served whole rather than asked per edge: a graph surface styles hundreds of edges and
        would otherwise make a request per relationship type it happens to meet.
        """
        return {
            str(name): info.notation.as_mapping()
            for name, info in self._catalog.all_connection_types().items()
        }

    def permissible_connection_types(self, source_type: str, target_type: str) -> Sequence[str]:
        prs = self._permitted
        src, tgt = EntityTypeName(source_type), EntityTypeName(target_type)
        result = set(prs.permitted_connection_types(src, tgt))
        for ct in prs.permitted_connection_types(tgt, src):
            if self.is_symmetric(ct):
                result.add(ct)
        return sorted(result)

    def permissible_target_types(self, source_type: str) -> Mapping[str, Sequence[str]]:
        out: dict[str, list[str]] = {}
        for tgt, ct in self._permitted.by_source().get(EntityTypeName(source_type), []):
            out.setdefault(str(ct), []).append(str(tgt))
        return {ct: sorted(tgts) for ct, tgts in sorted(out.items())}

    def classify_connections(self, source_type: str) -> Mapping[str, Mapping[str, Sequence[str]]]:
        prs = self._permitted
        src = EntityTypeName(source_type)
        outgoing: dict[str, list[str]] = {}
        incoming: dict[str, list[str]] = {}
        symmetric: dict[str, list[str]] = {}
        for tgt, ct in prs.by_source().get(src, []):
            target = symmetric if self.is_symmetric(ct) else outgoing
            target.setdefault(str(tgt), []).append(str(ct))
        for src2, ct in prs.by_target().get(src, []):
            key = str(src2)
            if self.is_symmetric(ct):
                symmetric.setdefault(key, []).extend([] if key in symmetric else [str(ct)])
            else:
                incoming.setdefault(key, []).append(str(ct))
        return {"outgoing": outgoing, "incoming": incoming, "symmetric": symmetric}


def _display_connection_label(conn_type: str) -> str:
    return conn_type.removeprefix("archimate-")


class DiagramTypeCatalogImpl:
    """ModuleCatalog-backed DiagramTypeCatalog."""

    def __init__(self, catalog: ModuleCatalog) -> None:
        self._catalog = catalog

    @functools.cached_property
    def _suppressed(self) -> frozenset[str]:
        return frozenset(
            _display_connection_label(str(name)).lower()
            for name, info in self._catalog.all_connection_types().items()
            if not info.show_stereotype
        )

    def suppressed_stereotype_tokens(self) -> frozenset[str]:
        return self._suppressed

    def diagram_type_domain(self, name: str) -> str | None:
        dt = self._catalog.find_diagram_type(name)
        if dt is None:
            return None
        domains = {
            info.hierarchy[0]
            for info in dt.effective_entity_types().values()
            if not info.internal and info.hierarchy
        }
        non_common = {d for d in domains if d != "common"}
        if len(non_common) == 1:
            return next(iter(non_common))
        if not non_common and len(domains) == 1:
            return next(iter(domains))
        return None

    def get_diagram_type(self, name: str) -> DiagramTypeModule:
        return self._catalog.get_diagram_type(name)

    def find_diagram_type(self, name: str) -> DiagramTypeModule | None:
        return self._catalog.find_diagram_type(name)

    def all_diagram_types(self) -> Mapping[str, DiagramTypeModule]:
        return self._catalog.all_diagram_types()

    @functools.cached_property
    def _store_projected(self) -> frozenset[str]:
        return frozenset(
            name for name, dt in self._catalog.all_diagram_types().items()
            if isinstance(dt, StoreGraphProjectingDiagramType)
        )

    def store_projected_diagram_types(self) -> frozenset[str]:
        """Types whose content is projected from a store graph rather than read from a repository file.

        This is what separates the diagrams a file-backed listing must skip from the ones it owns:
        such a type has no artifact on disk to list, open or group. Asking the capability protocol is
        exact, where a hand-kept list of names drifts and a module-class test only coincides with the
        answer — GSN is assurance work but lives in the repository like any other diagram.
        """
        return self._store_projected
