"""Unit tests for viewpoint-scope narrowing of the diagram-authoring palette/picker
(WU-E5a, companion plan §6.2's "effective authoring scope = diagram-type scope ∩ applied
viewpoint scope", extended from *applying* a viewpoint to *choosing* one while authoring):
``resolve_viewpoint_scope``, ``accepted_entity_types``, ``diagram_kind_entity_type_items``,
and ``diagram_kind_connection_type_items``.
"""

from __future__ import annotations

import dataclasses

import pytest
from fastapi import HTTPException

from src.domain.concept_scope import ConceptScope
from src.domain.viewpoints.viewpoints import ViewpointCatalog, ViewpointDefinition
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.rest.routers._diagram_context import (
    diagram_kind_connection_type_items,
    diagram_kind_entity_type_items,
)
from src.infrastructure.rest.routers._entity_display_search import accepted_entity_types
from src.infrastructure.rest.routers._viewpoint_scope import resolve_viewpoint_scope

_NARROW = ViewpointDefinition(
    slug="narrow-app",
    version=1,
    name="Narrow Application",
    scope=ConceptScope(entity_types=frozenset({"application-component"}), connection_types=frozenset()),
)


@pytest.fixture()
def catalogs():
    base = build_runtime_catalogs(get_module_registry())
    return dataclasses.replace(base, viewpoints=ViewpointCatalog(entries=(_NARROW,)))


class TestResolveViewpointScope:
    def test_none_slug_returns_none(self, catalogs) -> None:
        assert resolve_viewpoint_scope(None, catalogs) is None

    def test_known_slug_returns_its_scope(self, catalogs) -> None:
        assert resolve_viewpoint_scope("narrow-app", catalogs) is _NARROW.scope

    def test_unknown_slug_raises_404(self, catalogs) -> None:
        with pytest.raises(HTTPException) as exc_info:
            resolve_viewpoint_scope("does-not-exist", catalogs)
        assert exc_info.value.status_code == 404


class TestAcceptedEntityTypes:
    def test_without_viewpoint_returns_full_diagram_scope(self, catalogs) -> None:
        types = accepted_entity_types("archimate-application", catalogs)
        assert types is not None
        assert "application-component" in types
        assert len(types) > 1

    def test_with_viewpoint_narrows_to_intersection(self, catalogs) -> None:
        types = accepted_entity_types("archimate-application", catalogs, viewpoint="narrow-app")
        assert types == {"application-component"}


class TestDiagramKindEntityTypeItems:
    def test_narrowed_by_viewpoint(self, catalogs) -> None:
        items = diagram_kind_entity_type_items("archimate-application", catalogs, viewpoint="narrow-app")
        assert {item["artifact_type"] for item in items} == {"application-component"}

    def test_unnarrowed_has_more_than_one_type(self, catalogs) -> None:
        items = diagram_kind_entity_type_items("archimate-application", catalogs)
        assert len(items) > 1


class TestDiagramKindConnectionTypeItems:
    def test_narrowed_to_empty_when_viewpoint_excludes_all_connections(self, catalogs) -> None:
        items = diagram_kind_connection_type_items("archimate-application", catalogs, viewpoint="narrow-app")
        assert items == []

    def test_unnarrowed_has_connection_types(self, catalogs) -> None:
        items = diagram_kind_connection_type_items("archimate-application", catalogs)
        assert len(items) > 0
