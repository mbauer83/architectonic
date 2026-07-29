"""Unit tests for OntologyCatalogImpl, ConnectionSemanticsImpl, DiagramTypeCatalogImpl.

All tests build a ModuleCatalog from minimal stubs — zero global state.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.domain.diagrams.diagram_type_config import DiagramTypeUiConfig
from src.domain.modules.catalogs import (
    ConnectionSemantics,
    ConnectionSemanticsImpl,
    DiagramTypeCatalog,
    DiagramTypeCatalogImpl,
    OntologyCatalog,
    OntologyCatalogImpl,
)
from src.domain.modules.module_catalog import ModuleCatalog, ModuleCatalogBuilder
from src.domain.modules.module_types import ConnectionTypeName, ElementClassName, EntityTypeName
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, ElementClassInfo, EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet, permitted_connections_from_config

# ── Stub helpers ──────────────────────────────────────────────────────────────


def _et(
    name: str,
    domain: str = "d",
    prefix: str | None = None,
    classes: tuple[str, ...] = (),
    internal: bool = False,
) -> EntityTypeInfo:
    return EntityTypeInfo(
        artifact_type=name,
        prefix=prefix or name[:2].upper(),
        hierarchy=(domain, name),
        classes=classes,
        create_when="",
        never_create_when="",
        internal=internal,
    )


def _ct(
    name: str,
    *,
    conn_lang: str = "test",
    symmetric: bool = False,
    show_stereotype: bool = True,
    archimate_rel_type: str | None = None,
) -> ConnectionTypeInfo:
    return ConnectionTypeInfo(
        artifact_type=name,
        conn_lang=conn_lang,
        symmetric=symmetric,
        show_stereotype=show_stereotype,
        archimate_relationship_type=archimate_rel_type,
    )


class _StubOntology:
    module_class = "architecture"
    display_section_id = "stub"
    element_classes: Mapping[str, ElementClassInfo] = {}

    def __init__(
        self,
        name: str,
        entity_types: dict[str, EntityTypeInfo] | None = None,
        connection_types: dict[str, ConnectionTypeInfo] | None = None,
        permitted: PermittedRelationshipSet | None = None,
    ) -> None:
        self._name = name
        self._et: dict[EntityTypeName, EntityTypeInfo] = {
            EntityTypeName(k): v for k, v in (entity_types or {}).items()
        }
        self._ct: dict[ConnectionTypeName, ConnectionTypeInfo] = {
            ConnectionTypeName(k): v for k, v in (connection_types or {}).items()
        }
        self._permitted = permitted or PermittedRelationshipSet.empty()

    @property
    def name(self) -> str:
        return self._name

    @property
    def entity_types(self) -> Mapping[EntityTypeName, EntityTypeInfo]:
        return self._et

    @property
    def connection_types(self) -> Mapping[ConnectionTypeName, ConnectionTypeInfo]:
        return self._ct

    @property
    def permitted_relationships(self) -> PermittedRelationshipSet:
        return self._permitted

    def entity_types_with_class(self, cls: ElementClassName) -> frozenset[EntityTypeName]:
        return frozenset(n for n, info in self._et.items() if cls in info.classes)

    def connection_types_with_class(self, cls: str) -> frozenset[ConnectionTypeName]:
        return frozenset(n for n, info in self._ct.items() if cls in info.classes)

    def permits_connection(self, src: Any, tgt: Any, conn: Any) -> bool:
        return False

    def render_display_section(self, artifact_type: str, name: str, alias: str) -> str:
        return ""

    def extract_display_section(self, section_content: str) -> dict | None:
        return None

    def sprite_for(self, artifact_type: str) -> str | None:
        return None


class _StubDiagramType:
    module_class = "architecture"
    element_classes: Mapping[str, ElementClassInfo] = {}
    own_entity_types: Mapping[EntityTypeName, EntityTypeInfo] = {}
    own_connection_types: Mapping[ConnectionTypeName, ConnectionTypeInfo] = {}
    own_permitted_relationships = PermittedRelationshipSet.empty()
    effective_permitted_relationships = PermittedRelationshipSet.empty()
    bridges: tuple = ()
    primary_ontology: Any = None
    renderer: Any = None

    def __init__(
        self,
        name: str,
        effective_entity_types: dict[str, EntityTypeInfo] | None = None,
    ) -> None:
        self._name = name
        self._eff_et: dict[EntityTypeName, EntityTypeInfo] = {
            EntityTypeName(k): v for k, v in (effective_entity_types or {}).items()
        }

    @property
    def name(self) -> str:
        return self._name

    @property
    def ui_config(self) -> DiagramTypeUiConfig:
        return DiagramTypeUiConfig(label=self._name, entity_search_filter=False)

    def effective_entity_types(self) -> Mapping[EntityTypeName, EntityTypeInfo]:
        return self._eff_et

    def effective_connection_types(self) -> Mapping[ConnectionTypeName, ConnectionTypeInfo]:
        return {}

    def accepts_entity_type(self, t: Any) -> bool:
        return False

    def accepts_connection_type(self, t: Any) -> bool:
        return False

    def write_guidance(self) -> Any:
        return None

    def build_context_extras(self, repo: Any, diagram_id: str, diagram_entities: dict) -> dict:
        return {}

    def read_diagram_extras(self, parsed_source: dict) -> dict:
        return {}


def _catalog(ontologies: list | None = None, diagram_types: list | None = None) -> ModuleCatalog:
    b = ModuleCatalogBuilder()
    for o in ontologies or []:
        b.register_ontology(o)
    for d in diagram_types or []:
        b.register_diagram_type(d)
    return b.build()


# ── OntologyCatalog ──────────────────────────────────────────────────────────


class TestOntologyCatalog:
    def _impl(self, onto: _StubOntology, matrix: dict | None = None) -> OntologyCatalogImpl:
        return OntologyCatalogImpl(_catalog([onto]), matrix or {})

    def test_satisfies_protocol(self) -> None:
        impl = self._impl(_StubOntology("o"))
        assert isinstance(impl, OntologyCatalog)

    def test_all_entity_types(self) -> None:
        onto = _StubOntology("o", entity_types={"app": _et("app", domain="application")})
        impl = self._impl(onto)
        assert "app" in impl.all_entity_types()
        assert impl.all_entity_type_names() == frozenset({"app"})

    def test_all_connection_types(self) -> None:
        onto = _StubOntology("o", connection_types={"c1": _ct("c1")})
        impl = self._impl(onto)
        assert "c1" in impl.all_connection_types()
        assert "c1" in impl.all_connection_type_names()

    def test_known_domain_names_includes_unknown(self) -> None:
        onto = _StubOntology("o", entity_types={"app": _et("app", domain="application")})
        impl = self._impl(onto)
        assert "unknown" in impl.known_domain_names()
        assert "application" in impl.known_domain_names()

    def test_domain_order(self) -> None:
        onto = _StubOntology("o", entity_types={
            "app": _et("app", domain="application"),
            "tech": _et("tech", domain="technology"),
        })
        impl = self._impl(onto)
        order = impl.domain_order()
        assert "application" in order
        assert "technology" in order

    def test_domain_grouping(self) -> None:
        onto = _StubOntology("o", entity_types={"app": _et("app", domain="application")})
        impl = self._impl(onto)
        grouping = impl.domain_grouping()
        assert "application" in grouping
        assert grouping["application"] == "ApplicationGrouping"

    def test_entity_types_with_class(self) -> None:
        onto = _StubOntology("o", entity_types={
            "tagged": _et("tagged", classes=("my-cls",)),
            "plain": _et("plain"),
        })
        impl = self._impl(onto)
        result = impl.entity_types_with_class("my-cls")
        assert "tagged" in result
        assert "plain" not in result

    def test_expand_entity_type_term_literal(self) -> None:
        onto = _StubOntology("o", entity_types={"app": _et("app")})
        impl = self._impl(onto)
        assert impl.expand_entity_type_term("app") == ["app"]
        assert impl.expand_entity_type_term("missing") == []

    def test_expand_entity_type_term_all(self) -> None:
        onto = _StubOntology("o", entity_types={"a": _et("a"), "b": _et("b")})
        impl = self._impl(onto)
        assert set(impl.expand_entity_type_term("@all")) == {"a", "b"}

    def test_expand_entity_type_term_class(self) -> None:
        onto = _StubOntology("o", entity_types={
            "tagged": _et("tagged", classes=("the-class",)),
            "plain": _et("plain"),
        })
        impl = self._impl(onto)
        assert impl.expand_entity_type_term("@the-class") == ["tagged"]

    def test_format_entity_type_term(self) -> None:
        impl = self._impl(_StubOntology("o"))
        assert impl.format_entity_type_term("@all") == "entity"
        assert impl.format_entity_type_term("my-type") == "my type"
        assert impl.format_entity_type_term("@my-class") == "my class"

    def test_entity_type_term_matches(self) -> None:
        onto = _StubOntology("o", entity_types={"app": _et("app")})
        impl = self._impl(onto)
        assert impl.entity_type_term_matches("app", {"app", "other"})
        assert not impl.entity_type_term_matches("app", {"other"})

    def test_archimate_stereotype_to_connection_type(self) -> None:
        ct = _ct("archimate-association", conn_lang="archimate", archimate_rel_type="Association")
        onto = _StubOntology("o", connection_types={"archimate-association": ct})
        impl = self._impl(onto)
        stereo_map = impl.archimate_stereotype_to_connection_type()
        assert stereo_map.get("association") == "archimate-association"

    def test_entity_type_prefixes(self) -> None:
        onto = _StubOntology("o", entity_types={"app-service": _et("app-service", prefix="AS")})
        impl = self._impl(onto)
        assert impl.entity_type_prefixes()["AS"] == "app-service"

    def test_matrix_abbreviations(self) -> None:
        matrix = {"A": "archimate-association", "R": "archimate-realization"}
        onto = _StubOntology("o")
        impl = self._impl(onto, matrix)
        assert impl.matrix_abbreviations_by_connection_type() == matrix
        reverse = impl.matrix_connection_type_abbreviations()
        assert reverse["archimate-association"] == "A"
        assert reverse["archimate-realization"] == "R"

    def test_no_global_state(self) -> None:
        """Two separate OntologyCatalogImpl instances are fully independent."""
        a = OntologyCatalogImpl(_catalog([_StubOntology("a", {"e1": _et("e1")})]), {})
        b = OntologyCatalogImpl(_catalog([_StubOntology("b", {"e2": _et("e2")})]), {})
        assert "e1" in a.all_entity_type_names()
        assert "e2" not in a.all_entity_type_names()
        assert "e2" in b.all_entity_type_names()


# ── ConnectionSemantics ───────────────────────────────────────────────────────


def _prs_from_rules(rules: list[dict]) -> PermittedRelationshipSet:
    return permitted_connections_from_config(rules)


class TestConnectionSemantics:
    def _impl(self, onto: _StubOntology) -> ConnectionSemanticsImpl:
        return ConnectionSemanticsImpl(_catalog([onto]))

    def test_satisfies_protocol(self) -> None:
        assert isinstance(self._impl(_StubOntology("o")), ConnectionSemantics)

    def test_is_symmetric_false_for_unknown(self) -> None:
        impl = self._impl(_StubOntology("o"))
        assert not impl.is_symmetric("no-such-conn")

    def test_is_symmetric_for_known_symmetric(self) -> None:
        ct = _ct("sym-conn", symmetric=True)
        onto = _StubOntology("o", connection_types={"sym-conn": ct})
        impl = self._impl(onto)
        assert impl.is_symmetric("sym-conn")

    def test_is_symmetric_false_for_directional(self) -> None:
        ct = _ct("dir-conn", symmetric=False)
        onto = _StubOntology("o", connection_types={"dir-conn": ct})
        impl = self._impl(onto)
        assert not impl.is_symmetric("dir-conn")

    def test_permissible_connection_types_empty(self) -> None:
        impl = self._impl(_StubOntology("o"))
        result = impl.permissible_connection_types("src-type", "tgt-type")
        assert result == []

    def test_no_global_state(self) -> None:
        a = ConnectionSemanticsImpl(_catalog([_StubOntology("a")]))
        b = ConnectionSemanticsImpl(_catalog([_StubOntology("b")]))
        assert a is not b
        assert a._catalog is not b._catalog


# ── DiagramTypeCatalog ────────────────────────────────────────────────────────


class TestDiagramTypeCatalog:
    def _impl(
        self, *, connection_types: dict | None = None, diagram_types: list | None = None
    ) -> DiagramTypeCatalogImpl:
        onto = _StubOntology("o", connection_types=connection_types)
        return DiagramTypeCatalogImpl(_catalog([onto], diagram_types))

    def test_satisfies_protocol(self) -> None:
        assert isinstance(self._impl(), DiagramTypeCatalog)

    def test_suppressed_stereotype_tokens_empty_when_all_show(self) -> None:
        ct = _ct("my-conn", show_stereotype=True)
        impl = self._impl(connection_types={"my-conn": ct})
        assert "my-conn" not in impl.suppressed_stereotype_tokens()

    def test_suppressed_stereotype_tokens_for_hidden(self) -> None:
        ct = _ct("archimate-flow", show_stereotype=False)
        impl = self._impl(connection_types={"archimate-flow": ct})
        tokens = impl.suppressed_stereotype_tokens()
        assert "flow" in tokens  # removeprefix("archimate-").lower()

    def test_suppressed_tokens_cached(self) -> None:
        ct = _ct("archimate-flow", show_stereotype=False)
        impl = self._impl(connection_types={"archimate-flow": ct})
        assert impl.suppressed_stereotype_tokens() is impl.suppressed_stereotype_tokens()

    def test_get_diagram_type(self) -> None:
        dt = _StubDiagramType("arch")
        impl = self._impl(diagram_types=[dt])
        assert impl.get_diagram_type("arch") is dt

    def test_find_diagram_type_missing(self) -> None:
        impl = self._impl()
        assert impl.find_diagram_type("no-such") is None

    def test_all_diagram_types(self) -> None:
        dt = _StubDiagramType("arch")
        impl = self._impl(diagram_types=[dt])
        assert "arch" in impl.all_diagram_types()

    def test_diagram_type_domain_returns_none_when_not_found(self) -> None:
        impl = self._impl()
        assert impl.diagram_type_domain("no-such") is None

    def test_diagram_type_domain_single_non_common(self) -> None:
        et = _et("app-service", domain="application")
        dt = _StubDiagramType("arch", effective_entity_types={"app-service": et})
        impl = self._impl(diagram_types=[dt])
        assert impl.diagram_type_domain("arch") == "application"

    def test_diagram_type_domain_none_for_ambiguous(self) -> None:
        dt = _StubDiagramType("mixed", effective_entity_types={
            "app-service": _et("app-service", domain="application"),
            "tech-node": _et("tech-node", domain="technology"),
        })
        impl = self._impl(diagram_types=[dt])
        assert impl.diagram_type_domain("mixed") is None

    def test_no_global_state(self) -> None:
        a = DiagramTypeCatalogImpl(_catalog())
        b = DiagramTypeCatalogImpl(_catalog())
        assert a is not b


# ── Immutability contract ─────────────────────────────────────────────────────


class TestCatalogImmutability:
    """Verify that public catalog accessors return Mapping/Sequence views, not naked mutable dicts/lists."""

    def _onto_impl(self) -> OntologyCatalogImpl:
        onto = _StubOntology(
            "o",
            entity_types={"app": _et("app", domain="application")},
            connection_types={
                "archimate-assoc": _ct("archimate-assoc", conn_lang="archimate", archimate_rel_type="Association"),
            },
        )
        return OntologyCatalogImpl(_catalog([onto]), {"A": "archimate-assoc"})

    def test_domain_order_is_sequence(self) -> None:
        impl = self._onto_impl()
        result = impl.domain_order()
        assert isinstance(result, (list, tuple))
        assert "application" in result

    def test_domain_grouping_is_mapping(self) -> None:
        impl = self._onto_impl()
        result = impl.domain_grouping()
        assert isinstance(result, Mapping)
        assert "application" in result

    def test_archimate_stereotype_mapping_is_mapping(self) -> None:
        impl = self._onto_impl()
        result = impl.archimate_stereotype_to_connection_type()
        assert isinstance(result, Mapping)
        assert result.get("association") == "archimate-assoc"

    def test_entity_type_prefixes_is_mapping(self) -> None:
        onto = _StubOntology("o", entity_types={"app": _et("app", prefix="AP")})
        impl = OntologyCatalogImpl(_catalog([onto]), {})
        result = impl.entity_type_prefixes()
        assert isinstance(result, Mapping)
        assert result["AP"] == "app"

    def test_matrix_abbreviations_is_mapping(self) -> None:
        impl = self._onto_impl()
        by_ct = impl.matrix_abbreviations_by_connection_type()
        by_abbrev = impl.matrix_connection_type_abbreviations()
        assert isinstance(by_ct, Mapping)
        assert isinstance(by_abbrev, Mapping)

    def test_expand_entity_type_term_is_sequence(self) -> None:
        impl = self._onto_impl()
        result = impl.expand_entity_type_term("@all")
        assert hasattr(result, "__iter__")
        assert "app" in result

    def test_stereotype_map_shared_across_calls(self) -> None:
        """Repeated calls return the same cached object (no defensive copy overhead)."""
        impl = self._onto_impl()
        assert impl.archimate_stereotype_to_connection_type() is impl.archimate_stereotype_to_connection_type()

    def test_connection_semantics_permissible_types_is_sequence(self) -> None:
        onto = _StubOntology("o")
        impl = ConnectionSemanticsImpl(_catalog([onto]))
        result = impl.permissible_connection_types("a", "b")
        assert hasattr(result, "__iter__")

    def test_connection_semantics_classify_is_mapping(self) -> None:
        onto = _StubOntology("o")
        impl = ConnectionSemanticsImpl(_catalog([onto]))
        result = impl.classify_connections("some-type")
        assert isinstance(result, Mapping)
        assert "outgoing" in result
        assert "incoming" in result
        assert "symmetric" in result
