"""Unit tests for `project_artifact_by_frontmatter` (companion plan §6.2): assembles the
artifact-local projection from a diagram/matrix's raw frontmatter — the WU-E5a GUI
projection endpoint's use of the WU-E15 service, alongside the WU-E16 verifier rule
(`tests/tools/test_viewpoint_verifier_rule.py` covers that consumer).
"""

from __future__ import annotations

from pathlib import Path

from src.application.viewpoints.artifact_projection import project_artifact_by_frontmatter
from src.domain.concept_scope import ConceptScope
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoints import ViewpointCatalog, ViewpointDefinition

_REGISTRIES = RegistrySnapshot(
    known_entity_types=frozenset({"stakeholder", "goal"}),
    known_connection_types=frozenset({"archimate-realization"}),
    known_specialization_slugs=frozenset(),
    entity_attribute_types={},
    connection_attribute_types={},
)
_DEFINITION = ViewpointDefinition(
    slug="motivation",
    version=2,
    name="Motivation",
    scope=ConceptScope(entity_types=frozenset({"stakeholder"}), connection_types=frozenset()),
)
_CATALOG = ViewpointCatalog((_DEFINITION,))


class _FakeModule:
    def concept_scope(self) -> ConceptScope:
        return ConceptScope.unrestricted()


class _FakeRegistry:
    def __init__(self, entities: dict[str, EntityRecord], connections: dict[str, ConnectionRecord]) -> None:
        self._entities = entities
        self._connections = connections

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self._entities.get(artifact_id)

    def get_connection(self, artifact_id: str) -> ConnectionRecord | None:
        return self._connections.get(artifact_id)


def _entity(artifact_id: str, artifact_type: str = "stakeholder") -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id, artifact_type=artifact_type, name=artifact_id, version="1.0.0",
        status="active", domain="test", subdomain="", path=Path("x"), keywords=(), extra={}, content_text="",
        display_blocks={}, display_label=artifact_id, display_alias=artifact_id,
    )


_STK = _entity("STK@1.x.a")
_GOAL_OUT_OF_SCOPE = _entity("GOA@1.x.b", artifact_type="goal")
_REGISTRY = _FakeRegistry({_STK.artifact_id: _STK, _GOAL_OUT_OF_SCOPE.artifact_id: _GOAL_OUT_OF_SCOPE}, {})


def _project(fm: dict, **overrides):
    kwargs = {
        "target_kind": "diagram",
        "target_id": "ARC@1.x.diagram",
        "catalog": _CATALOG,
        "module": _FakeModule(),
        "entity_type_infos": {},
        "default_enforcement": "warn",
        "registry": _REGISTRY,  # type: ignore[arg-type]
        "registries": _REGISTRIES,
        **overrides,
    }
    return project_artifact_by_frontmatter(fm, **kwargs)


class TestNoApplication:
    def test_returns_none_when_no_viewpoint_key(self) -> None:
        assert _project({"entity-ids-used": [_STK.artifact_id]}) is None


class TestApplication:
    def test_projects_placed_entities_with_reasons(self) -> None:
        fm = {
            "viewpoint": {"slug": "motivation", "version": 2},
            "entity-ids-used": [_STK.artifact_id, _GOAL_OUT_OF_SCOPE.artifact_id],
        }
        projection = _project(fm)
        assert projection is not None
        by_id = {item.item_id: item for item in projection.items}
        assert by_id[_STK.artifact_id].reasons == ()
        assert by_id[_GOAL_OUT_OF_SCOPE.artifact_id].reasons == ("out_of_scope",)
        assert projection.stale_pin is False

    def test_stale_pin_when_pinned_version_below_current(self) -> None:
        fm = {"viewpoint": {"slug": "motivation", "version": 1}, "entity-ids-used": [_STK.artifact_id]}
        projection = _project(fm)
        assert projection is not None
        assert projection.stale_pin is True

    def test_unknown_slug_is_identity_projection_with_warning(self) -> None:
        fm = {"viewpoint": {"slug": "does-not-exist", "version": 1}, "entity-ids-used": [_STK.artifact_id]}
        projection = _project(fm)
        assert projection is not None
        assert projection.items[0].state == "visible"
        assert projection.items[0].reasons == ()
        assert any("does-not-exist" in w for w in projection.warnings)

    def test_off_enforcement_still_computed_but_zeroed_reasons(self) -> None:
        fm = {
            "viewpoint": {"slug": "motivation", "version": 2, "enforcement_override": "off"},
            "entity-ids-used": [_GOAL_OUT_OF_SCOPE.artifact_id],
        }
        projection = _project(fm)
        assert projection is not None
        assert projection.items[0].state == "visible"
        assert projection.items[0].reasons == ()
