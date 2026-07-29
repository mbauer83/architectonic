"""Unit tests for the viewpoint-application verifier rule: unknown slug (E180), stale
pinned version (W180), out-of-scope entity/connection (W181), criteria-mismatch entity/
connection (W182), and the enforcement setting (off silences everything but E180).

``check_viewpoint_application`` obtains its artifact-local projection from
``project_artifact_local`` (companion plan §6.2/§6.3) — the same service the GUI's ghost/hide
overlay consumes — so a dedicated test asserts the verifier's W181/W182 issues agree with
that projection's ``out_of_scope``/``criteria_mismatch`` reasons on one shared fixture.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from src.application.verification._verifier_rules_viewpoint import check_viewpoint_application
from src.application.verification.artifact_verifier_types import VerificationResult
from src.application.viewpoints.artifact_projection import project_artifact_local
from src.application.viewpoints.placed_occurrences import resolve_placed_connections, resolve_placed_entities
from src.domain.concept_scope import ConceptScope
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria import (
    AttributeCondition,
    ConnectionCriteriaGroup,
    ConnectionSelection,
    EntityCriteriaGroup,
    ValueRef,
)
from src.domain.viewpoints.viewpoints import (
    ExecutableViewpointQuery,
    ViewpointApplication,
    ViewpointCatalog,
    ViewpointDefinition,
)

_DIAGRAM_SCOPE = ConceptScope.unrestricted()
_REGISTRIES = RegistrySnapshot(
    known_entity_types=frozenset({"stakeholder", "goal", "requirement"}),
    known_connection_types=frozenset({"archimate-realization", "archimate-serving"}),
    known_specialization_slugs=frozenset(),
    entity_attribute_types={},
    connection_attribute_types={},
)
_NARROW_DEFINITION = ViewpointDefinition(
    slug="motivation",
    version=2,
    name="Motivation",
    scope=ConceptScope(
        entity_types=frozenset({"stakeholder", "goal"}),
        connection_types=frozenset({"archimate-realization"}),
    ),
)
_QUERY_DEFINITION = ViewpointDefinition(
    slug="filtered",
    version=1,
    name="Filtered",
    scope=ConceptScope.unrestricted(),
    query=ExecutableViewpointQuery(
        entity_criteria=EntityCriteriaGroup(
            children=(AttributeCondition(attribute="name", comparator="eq", value=ValueRef(literal="Match")),)
        ),
        connections=ConnectionSelection(
            criteria=ConnectionCriteriaGroup(
                children=(
                    AttributeCondition(
                        attribute="type",
                        comparator="eq",
                        value=ValueRef(literal="archimate-realization"),
                    ),
                )
            )
        ),
    ),
)
_CATALOG = ViewpointCatalog((_NARROW_DEFINITION, _QUERY_DEFINITION))


def _entity(artifact_id: str, artifact_type: str = "stakeholder", name: str | None = None) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id, artifact_type=artifact_type, name=name or artifact_id, version="1.0.0",
        status="active", domain="test", subdomain="", path=Path("x"), keywords=(), extra={}, content_text="",
        display_blocks={}, display_label=artifact_id, display_alias=artifact_id,
    )


def _connection(artifact_id: str, source: str, target: str, conn_type: str) -> ConnectionRecord:
    return ConnectionRecord(
        artifact_id=artifact_id, source=source, target=target, conn_type=conn_type, version="1.0.0",
        status="active", path=Path("x"), extra={}, content_text="",
    )


class _FakeRegistry:
    def __init__(self, entities: dict[str, EntityRecord], connections: dict[str, ConnectionRecord]) -> None:
        self._entities = entities
        self._connections = connections

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self._entities.get(artifact_id)

    def get_connection(self, artifact_id: str) -> ConnectionRecord | None:
        return self._connections.get(artifact_id)

    def find_connections_for(
        self,
        entity_id: str,
        *,
        direction: Literal["any", "outbound", "inbound"] = "any",
        conn_type: str | None = None,
    ) -> list[ConnectionRecord]:
        return [c for c in self._connections.values() if c.source == entity_id or c.target == entity_id]


_EMPTY_REGISTRY = _FakeRegistry({}, {})


def _check(
    fm: dict,
    *,
    placed_entities: tuple[EntityRecord, ...] = (),
    placed_connections: tuple[ConnectionRecord, ...] = (),
    read_access: _FakeRegistry = _EMPTY_REGISTRY,
    **overrides: Any,
) -> VerificationResult:
    result = VerificationResult(path=Path("dummy.puml"), file_type="diagram")
    kwargs: dict[str, Any] = dict(
        target_kind="diagram",
        target_id="DGM@1.x.a",
        catalog=_CATALOG,
        diagram_scope=_DIAGRAM_SCOPE,
        entity_type_infos={},
        placed_entities=placed_entities,
        placed_connections=placed_connections,
        default_enforcement="warn",
        read_access=read_access,
        registries=_REGISTRIES,
        result=result,
        loc="dummy.puml",
    )
    kwargs.update(overrides)
    check_viewpoint_application(fm, **kwargs)
    return result


class TestNoViewpointApplication:
    def test_absent_key_produces_no_issues(self) -> None:
        assert _check({}).issues == []


class TestUnknownSlug:
    def test_unknown_slug_is_always_an_error(self) -> None:
        result = _check({"viewpoint": {"slug": "no-such-viewpoint", "version": 1}}, default_enforcement="off")
        assert len(result.issues) == 1
        assert result.issues[0].code == "E180"


class TestStaleApplication:
    def test_pinned_version_behind_current_is_a_warning(self) -> None:
        result = _check({"viewpoint": {"slug": "motivation", "version": 1}})
        codes = [i.code for i in result.issues]
        assert "W180" in codes

    def test_pinned_version_current_has_no_stale_warning(self) -> None:
        result = _check({"viewpoint": {"slug": "motivation", "version": 2}})
        assert "W180" not in [i.code for i in result.issues]


class TestOutOfScope:
    def test_out_of_scope_entity_is_a_warning(self) -> None:
        result = _check(
            {"viewpoint": {"slug": "motivation", "version": 2}},
            placed_entities=(_entity("STK@1.x.a", "stakeholder"), _entity("REQ@1.x.b", "requirement")),
        )
        w181 = [i for i in result.issues if i.code == "W181"]
        assert len(w181) == 1
        assert "REQ@1.x.b" in w181[0].message

    def test_in_scope_entity_has_no_warning(self) -> None:
        result = _check(
            {"viewpoint": {"slug": "motivation", "version": 2}},
            placed_entities=(_entity("STK@1.x.a", "stakeholder"),),
        )
        assert result.issues == []

    def test_out_of_scope_connection_is_a_warning(self) -> None:
        entities = {"STK@1.x.a": _entity("STK@1.x.a", "stakeholder"), "GOAL@1.x.b": _entity("GOAL@1.x.b", "goal")}
        connections = {"REL@1.x.a": _connection("REL@1.x.a", "STK@1.x.a", "GOAL@1.x.b", "archimate-serving")}
        result = _check(
            {"viewpoint": {"slug": "motivation", "version": 2}},
            placed_entities=tuple(entities.values()),
            placed_connections=tuple(connections.values()),
            read_access=_FakeRegistry(entities, connections),
        )
        w181 = [i for i in result.issues if i.code == "W181"]
        assert len(w181) == 1

    def test_in_scope_connection_has_no_warning(self) -> None:
        entities = {"STK@1.x.a": _entity("STK@1.x.a", "stakeholder"), "GOAL@1.x.b": _entity("GOAL@1.x.b", "goal")}
        connections = {"REL@1.x.a": _connection("REL@1.x.a", "STK@1.x.a", "GOAL@1.x.b", "archimate-realization")}
        result = _check(
            {"viewpoint": {"slug": "motivation", "version": 2}},
            placed_entities=tuple(entities.values()),
            placed_connections=tuple(connections.values()),
            read_access=_FakeRegistry(entities, connections),
        )
        assert result.issues == []


class TestCriteriaMismatch:
    def test_entity_failing_query_criteria_is_a_warning(self) -> None:
        result = _check(
            {"viewpoint": {"slug": "filtered", "version": 1}},
            placed_entities=(_entity("STK@1.x.a", "stakeholder", name="NoMatch"),),
        )
        w182 = [i for i in result.issues if i.code == "W182"]
        assert len(w182) == 1
        assert "STK@1.x.a" in w182[0].message

    def test_entity_matching_query_criteria_has_no_warning(self) -> None:
        result = _check(
            {"viewpoint": {"slug": "filtered", "version": 1}},
            placed_entities=(_entity("STK@1.x.a", "stakeholder", name="Match"),),
        )
        assert result.issues == []

    def test_connection_failing_query_criteria_is_a_warning(self) -> None:
        entities = {
            "STK@1.x.a": _entity("STK@1.x.a", "stakeholder", "Match"),
            "GOAL@1.x.b": _entity("GOAL@1.x.b", "goal", "Match"),
        }
        connections = {"REL@1.x.a": _connection("REL@1.x.a", "STK@1.x.a", "GOAL@1.x.b", "archimate-serving")}
        result = _check(
            {"viewpoint": {"slug": "filtered", "version": 1}},
            placed_entities=tuple(entities.values()),
            placed_connections=tuple(connections.values()),
            read_access=_FakeRegistry(entities, connections),
        )
        w182 = [i for i in result.issues if i.code == "W182"]
        assert len(w182) == 1
        assert "REL@1.x.a" in w182[0].message

    def test_off_query_less_definition_never_emits_w182(self) -> None:
        result = _check(
            {"viewpoint": {"slug": "motivation", "version": 2}},
            placed_entities=(_entity("STK@1.x.a", "stakeholder", name="anything"),),
        )
        assert [i for i in result.issues if i.code == "W182"] == []


class TestEnforcementSetting:
    def test_off_silences_stale_and_out_of_scope(self) -> None:
        result = _check(
            {"viewpoint": {"slug": "motivation", "version": 1}},
            default_enforcement="off",
            placed_entities=(_entity("REQ@1.x.b", "requirement"),),
        )
        assert result.issues == []

    def test_ghost_still_warns(self) -> None:
        result = _check({"viewpoint": {"slug": "motivation", "version": 1}}, default_enforcement="ghost")
        assert "W180" in [i.code for i in result.issues]

    def test_application_enforcement_override_wins_over_default(self) -> None:
        result = _check(
            {"viewpoint": {"slug": "motivation", "version": 1, "enforcement_override": "off"}},
            default_enforcement="warn",
        )
        assert result.issues == []


class TestResolvePlacedEntities:
    def test_absent_key_returns_empty(self) -> None:
        assert resolve_placed_entities({}, _EMPTY_REGISTRY) == ()  # type: ignore[arg-type]

    def test_resolves_known_entities(self) -> None:
        entity = _entity("STK@1.x.a", "stakeholder")
        registry = _FakeRegistry({"STK@1.x.a": entity}, {})
        resolved = resolve_placed_entities({"entity-ids-used": ["STK@1.x.a"]}, registry)  # type: ignore[arg-type]
        assert resolved == (entity,)

    def test_unresolvable_ids_are_skipped(self) -> None:
        resolved = resolve_placed_entities({"entity-ids-used": ["MISSING@1.x.a"]}, _EMPTY_REGISTRY)  # type: ignore[arg-type]
        assert resolved == ()


class TestResolvePlacedConnections:
    def test_absent_key_returns_empty(self) -> None:
        assert resolve_placed_connections({}, _EMPTY_REGISTRY) == ()  # type: ignore[arg-type]

    def test_resolves_known_connection_with_resolvable_endpoints(self) -> None:
        entities = {"STK@1.x.a": _entity("STK@1.x.a", "stakeholder"), "GOAL@1.x.b": _entity("GOAL@1.x.b", "goal")}
        conn = _connection("REL@1.x.a", "STK@1.x.a", "GOAL@1.x.b", "archimate-realization")
        registry = _FakeRegistry(entities, {"REL@1.x.a": conn})
        resolved = resolve_placed_connections({"connection-ids-used": ["REL@1.x.a"]}, registry)  # type: ignore[arg-type]
        assert resolved == (conn,)

    def test_unresolvable_connection_is_skipped(self) -> None:
        resolved = resolve_placed_connections({"connection-ids-used": ["MISSING@1.x.a"]}, _EMPTY_REGISTRY)  # type: ignore[arg-type]
        assert resolved == ()

    def test_connection_with_unresolvable_endpoint_is_skipped(self) -> None:
        conn = _connection("REL@1.x.a", "STK@1.x.a", "GOAL@1.x.b", "archimate-realization")
        registry = _FakeRegistry({"STK@1.x.a": _entity("STK@1.x.a")}, {"REL@1.x.a": conn})
        resolved = resolve_placed_connections({"connection-ids-used": ["REL@1.x.a"]}, registry)  # type: ignore[arg-type]
        assert resolved == ()


class TestVerifierProjectionAgreement:
    """The verifier's W181/W182 issues must exactly track the same
    ``project_artifact_local`` projection the GUI's ghost/hide overlay consumes — never a
    re-implementation (companion plan §6.3 acceptance criterion)."""

    def test_verifier_warnings_match_projection_reasons(self) -> None:
        entities = {
            "STK@1.x.a": _entity("STK@1.x.a", "stakeholder", name="Match"),
            "REQ@1.x.b": _entity("REQ@1.x.b", "requirement", name="NoMatch"),
        }
        placed_entities = tuple(entities.values())
        registry = _FakeRegistry(entities, {})
        application = ViewpointApplication(
            target_kind="diagram",
            target_id="DGM@1.x.a",
            viewpoint_slug="filtered",
            pinned_version=1,
        )

        result = _check(
            {"viewpoint": {"slug": "filtered", "version": 1}},
            placed_entities=placed_entities,
            read_access=registry,
        )
        projection = project_artifact_local(
            _QUERY_DEFINITION,
            application,
            diagram_scope=_DIAGRAM_SCOPE,
            entity_type_infos={},
            placed_entities=placed_entities,
            placed_connections=(),
            enforcement="warn",
            read_access=registry,
            registries=_REGISTRIES,
        )

        mismatched_ids = {o.item_id for o in projection.items if "criteria_mismatch" in o.reasons}
        w182_ids = {i.message.split("'")[1] for i in result.issues if i.code == "W182"}
        assert mismatched_ids == w182_ids == {"REQ@1.x.b"}
