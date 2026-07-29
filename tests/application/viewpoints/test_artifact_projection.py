"""Unit tests for the artifact-local projection (companion plan §6.2): Appendix-C
"Projection" cluster, artifact-local half — every occurrence present, reason assignment,
enforcement mapping, occlusion-dominates-styling, stale pin, unknown slug.
"""

from __future__ import annotations

from src.application.viewpoints.artifact_projection import project_artifact_local
from src.domain.concept_scope import ConceptScope
from src.domain.modules.module_types import EntityTypeName
from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, EntityCriteriaGroup, ValueRef
from src.domain.viewpoints.viewpoints import (
    ExecutableViewpointQuery,
    PresentationSpec,
    StyleRule,
    ViewpointApplication,
    ViewpointDefinition,
)
from tests.application.viewpoints._fixtures import REGISTRIES, Store, connection, entity

_UNRESTRICTED = ConceptScope.unrestricted()


def _type_condition(value: str) -> AttributeCondition:
    return AttributeCondition(attribute="type", comparator="eq", value=ValueRef(literal=value))


def _deprecated_condition() -> AttributeCondition:
    return AttributeCondition(attribute="status", comparator="eq", value=ValueRef(literal="deprecated"))


def _application(**kw: object) -> ViewpointApplication:
    defaults: dict[str, object] = dict(
        target_kind="diagram", target_id="DIA@1", viewpoint_slug="test-viewpoint", pinned_version=1
    )
    defaults.update(kw)
    return ViewpointApplication(**defaults)  # type: ignore[arg-type]


def _definition(**kw: object) -> ViewpointDefinition:
    defaults: dict[str, object] = dict(slug="test-viewpoint", version=1, name="Test", scope=_UNRESTRICTED)
    defaults.update(kw)
    return ViewpointDefinition(**defaults)  # type: ignore[arg-type]


class TestUnknownSlug:
    def test_identity_projection_with_warning(self) -> None:
        placed = [entity(artifact_id="ENT@A")]
        projection = project_artifact_local(
            None,
            _application(),
            diagram_scope=_UNRESTRICTED,
            entity_type_infos={},
            placed_entities=placed,
            placed_connections=[],
            enforcement="ghost",
            read_access=Store(),
            registries=REGISTRIES,
        )
        assert len(projection.items) == 1
        assert projection.items[0].state == "visible"
        assert projection.items[0].reasons == ()
        assert "test-viewpoint" in projection.warnings[0]


class TestFullyMatching:
    def test_no_query_no_reasons_visible_and_styled(self) -> None:
        placed = [entity(artifact_id="ENT@A", status="deprecated")]
        presentation = PresentationSpec(
            representation="table",
            styling_rules=(
                StyleRule(
                    capability="badges",
                    mode="match",
                    match_criteria=EntityCriteriaGroup(children=(_deprecated_condition(),)),
                    value="badge-warning",
                ),
            ),
        )
        definition = _definition(presentation=presentation)
        projection = project_artifact_local(
            definition,
            _application(),
            diagram_scope=_UNRESTRICTED,
            entity_type_infos={},
            placed_entities=placed,
            placed_connections=[],
            enforcement="ghost",
            read_access=Store(),
            registries=REGISTRIES,
        )
        item = projection.items[0]
        assert item.reasons == ()
        assert item.state == "visible"
        assert item.style == {"badges": "badge-warning"}


class TestOutOfScope:
    def test_entity_outside_effective_scope_gets_reason(self) -> None:
        placed = [entity(artifact_id="ENT@A", artifact_type="process")]
        scope = ConceptScope(entity_types=frozenset({EntityTypeName("application-component")}))
        definition = _definition(scope=scope)
        projection = project_artifact_local(
            definition,
            _application(),
            diagram_scope=_UNRESTRICTED,
            entity_type_infos={},
            placed_entities=placed,
            placed_connections=[],
            enforcement="warn",
            read_access=Store(),
            registries=REGISTRIES,
        )
        item = projection.items[0]
        assert item.reasons == ("out_of_scope",)
        assert item.state == "visible"  # warn keeps everything visible
        assert item.style == {}  # occlusion dominates styling


class TestCriteriaMismatch:
    def test_query_mismatch_flagged_and_unstyled(self) -> None:
        placed = [entity(artifact_id="ENT@A", artifact_type="process")]
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(_type_condition("application-component"),))
        )
        definition = _definition(query=query)
        projection = project_artifact_local(
            definition,
            _application(),
            diagram_scope=_UNRESTRICTED,
            entity_type_infos={},
            placed_entities=placed,
            placed_connections=[],
            enforcement="ghost",
            read_access=Store(),
            registries=REGISTRIES,
        )
        item = projection.items[0]
        assert item.reasons == ("criteria_mismatch",)
        assert item.state == "ghosted"
        assert item.style == {}


class TestEndpointExcluded:
    def test_connection_with_excluded_endpoint_flagged(self) -> None:
        excluded = entity(artifact_id="ENT@excluded", artifact_type="process")
        included = entity(artifact_id="ENT@included", artifact_type="application-component")
        link = connection(artifact_id="CON@1", source="ENT@excluded", target="ENT@included")
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(_type_condition("application-component"),))
        )
        definition = _definition(query=query)
        store = Store(entities={"ENT@excluded": excluded, "ENT@included": included})
        projection = project_artifact_local(
            definition,
            _application(),
            diagram_scope=_UNRESTRICTED,
            entity_type_infos={},
            placed_entities=[excluded, included],
            placed_connections=[link],
            enforcement="warn",
            read_access=store,
            registries=REGISTRIES,
        )
        connection_item = next(item for item in projection.items if item.item_kind == "connection")
        assert "endpoint_excluded" in connection_item.reasons


class TestEnforcementMapping:
    def _mismatching_definition(self) -> ViewpointDefinition:
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(_type_condition("application-component"),))
        )
        return _definition(query=query)

    def test_off_zeroes_reasons_and_still_styles(self) -> None:
        placed = [entity(artifact_id="ENT@A", artifact_type="process", status="deprecated")]
        presentation = PresentationSpec(
            representation="table",
            styling_rules=(
                StyleRule(
                    capability="badges",
                    mode="match",
                    match_criteria=EntityCriteriaGroup(children=(_deprecated_condition(),)),
                    value="badge-warning",
                ),
            ),
        )
        query = self._mismatching_definition().query
        definition = _definition(query=query, presentation=presentation)
        projection = project_artifact_local(
            definition,
            _application(),
            diagram_scope=_UNRESTRICTED,
            entity_type_infos={},
            placed_entities=placed,
            placed_connections=[],
            enforcement="off",
            read_access=Store(),
            registries=REGISTRIES,
        )
        item = projection.items[0]
        assert item.reasons == ()
        assert item.state == "visible"
        assert item.style == {"badges": "badge-warning"}

    def test_warn_keeps_visible_with_reasons(self) -> None:
        placed = [entity(artifact_id="ENT@A", artifact_type="process")]
        projection = project_artifact_local(
            self._mismatching_definition(),
            _application(),
            diagram_scope=_UNRESTRICTED,
            entity_type_infos={},
            placed_entities=placed,
            placed_connections=[],
            enforcement="warn",
            read_access=Store(),
            registries=REGISTRIES,
        )
        item = projection.items[0]
        assert item.reasons == ("criteria_mismatch",)
        assert item.state == "visible"

    def test_ghost_ghosts_non_matching(self) -> None:
        placed = [entity(artifact_id="ENT@A", artifact_type="process")]
        projection = project_artifact_local(
            self._mismatching_definition(),
            _application(),
            diagram_scope=_UNRESTRICTED,
            entity_type_infos={},
            placed_entities=placed,
            placed_connections=[],
            enforcement="ghost",
            read_access=Store(),
            registries=REGISTRIES,
        )
        item = projection.items[0]
        assert item.state == "ghosted"


class TestStalePin:
    def test_pinned_version_older_than_current_sets_stale_pin(self) -> None:
        placed = [entity(artifact_id="ENT@A")]
        definition = _definition(version=2)
        projection = project_artifact_local(
            definition,
            _application(pinned_version=1),
            diagram_scope=_UNRESTRICTED,
            entity_type_infos={},
            placed_entities=placed,
            placed_connections=[],
            enforcement="warn",
            read_access=Store(),
            registries=REGISTRIES,
        )
        assert projection.stale_pin is True

    def test_pinned_version_current_no_stale_pin(self) -> None:
        placed = [entity(artifact_id="ENT@A")]
        definition = _definition(version=1)
        projection = project_artifact_local(
            definition,
            _application(pinned_version=1),
            diagram_scope=_UNRESTRICTED,
            entity_type_infos={},
            placed_entities=placed,
            placed_connections=[],
            enforcement="warn",
            read_access=Store(),
            registries=REGISTRIES,
        )
        assert projection.stale_pin is False
