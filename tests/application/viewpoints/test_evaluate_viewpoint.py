"""Tests for ``EvaluateViewpoint``: sorted ids/summaries, entity-denominated truncation, four counts, matrix axis
complement property, timeout, repo_scope, index revision, duration.
"""

from __future__ import annotations

import pytest

import src.domain.viewpoints.viewpoint_derived_relationship_batch as viewpoint_derived_relationship_batch_module
from src.application.viewpoints.evaluate_viewpoint import (
    UnknownViewpointSlugError,
    ViewpointExecutionRequest,
    ViewpointExecutionTimeoutError,
    evaluate_viewpoint,
    project_viewpoint_repository,
    resolve_viewpoint_definition,
)
from src.application.viewpoints.parameter_binding import ViewpointParameterError
from src.domain.viewpoints.viewpoint_bindings import DerivedAttribute, QueryParameter
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria import (
    AttributeCondition,
    EntityCriteriaGroup,
    NeighborInclusion,
    ValueRef,
)
from src.domain.viewpoints.viewpoints import (
    ExecutableViewpointQuery,
    PresentationSpec,
    StyleRule,
    ViewpointCatalog,
    ViewpointDefinition,
)
from tests.application.viewpoints._fixtures import REGISTRIES, Store, connection, entity
from tests.fixtures.viewpoints import derivation_examples

_DEFAULTS: dict[str, object] = dict(max_entities=500, default_limit=500, timeout_seconds=10.0, index_generation=None)


def _run(request: ViewpointExecutionRequest, *, catalog: ViewpointCatalog, read_access: Store, **overrides: object):
    kwargs = {**_DEFAULTS, **overrides}
    return evaluate_viewpoint(request, catalog=catalog, read_access=read_access, registries=REGISTRIES, **kwargs)


def _type_condition(value: str) -> AttributeCondition:
    return AttributeCondition(attribute="type", comparator="eq", value=ValueRef(literal=value))


def _definition(**kw: object) -> ViewpointDefinition:
    defaults: dict[str, object] = dict(slug="test-viewpoint", version=3, name="Test")
    defaults.update(kw)
    return ViewpointDefinition(**defaults)  # type: ignore[arg-type]


class TestSlugResolution:
    def test_unknown_slug_raises(self) -> None:
        with pytest.raises(UnknownViewpointSlugError):
            _run(ViewpointExecutionRequest(slug="missing"), catalog=ViewpointCatalog.empty(), read_access=Store())

    def test_known_slug_carries_identity(self) -> None:
        definition = _definition(query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup()))
        catalog = ViewpointCatalog(entries=(definition,))
        result = _run(ViewpointExecutionRequest(slug="test-viewpoint"), catalog=catalog, read_access=Store())
        assert result.slug == "test-viewpoint"
        assert result.version == 3

    def test_ad_hoc_query_has_no_identity(self) -> None:
        request = ViewpointExecutionRequest(query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup()))
        result = _run(request, catalog=ViewpointCatalog.empty(), read_access=Store())
        assert result.slug is None
        assert result.version is None

    def test_request_without_slug_or_query_raises(self) -> None:
        with pytest.raises(ValueError):
            _run(ViewpointExecutionRequest(), catalog=ViewpointCatalog.empty(), read_access=Store())


class TestPresentationOverride:
    """The ephemeral presentation override on both execution paths (Plan: slug + presentation
    swaps the saved presentation for this execution only; inline query carries its own)."""

    def _saved_definition(self, presentation: PresentationSpec | None) -> ViewpointDefinition:
        return _definition(
            query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup()), presentation=presentation
        )

    def test_slug_override_replaces_presentation_without_mutating_catalog(self) -> None:
        saved = PresentationSpec(representation="table")
        override = PresentationSpec(representation="matrix")
        catalog = ViewpointCatalog(entries=(self._saved_definition(saved),))
        resolved, slug, version = resolve_viewpoint_definition(
            "test-viewpoint", None, catalog=catalog, presentation=override
        )
        assert resolved.presentation == override
        assert (slug, version) == ("test-viewpoint", 3)  # identity still reflects the saved definition
        stored = catalog.get("test-viewpoint")
        assert stored is not None and stored.presentation == saved  # stored definition never mutated

    def test_slug_without_override_keeps_saved_presentation(self) -> None:
        saved = PresentationSpec(representation="table")
        catalog = ViewpointCatalog(entries=(self._saved_definition(saved),))
        resolved, _, _ = resolve_viewpoint_definition("test-viewpoint", None, catalog=catalog)
        assert resolved.presentation == saved

    def test_ad_hoc_query_carries_inline_presentation(self) -> None:
        inline = PresentationSpec(representation="matrix")
        query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup())
        resolved, slug, version = resolve_viewpoint_definition(
            None, query, catalog=ViewpointCatalog.empty(), presentation=inline
        )
        assert resolved.presentation == inline
        assert (slug, version) == (None, None)

    def test_ad_hoc_query_without_presentation_defaults_to_none(self) -> None:
        query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup())
        resolved, _, _ = resolve_viewpoint_definition(None, query, catalog=ViewpointCatalog.empty())
        assert resolved.presentation is None


class TestParameters:
    def test_missing_unknown_and_mistyped_parameters_raise_typed_errors(self) -> None:
        query = ExecutableViewpointQuery(parameters=(QueryParameter("limit", "integer"),))
        for supplied, code in (
            (None, "missing-parameter"),
            ({"other": 1}, "unknown-parameter"),
            ({"limit": "1"}, "parameter-type-mismatch"),
        ):
            with pytest.raises(ViewpointParameterError) as error:
                _run(
                    ViewpointExecutionRequest(query=query, parameters=supplied),
                    catalog=ViewpointCatalog.empty(),
                    read_access=Store(),
                )
            assert error.value.code == code


class TestAnchorIds:
    def _anchored_query(self) -> ExecutableViewpointQuery:
        anchor_condition = AttributeCondition(
            attribute="id", comparator="eq", value=ValueRef(kind="parameter", parameter="anchor")
        )
        return ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(anchor_condition,)),
            parameters=(QueryParameter("anchor", "entity-id"),),
        )

    def test_entity_id_parameters_become_anchor_ids(self) -> None:
        store = Store(entities={"ENT@A": entity(artifact_id="ENT@A"), "ENT@B": entity(artifact_id="ENT@B")})
        result = _run(
            ViewpointExecutionRequest(query=self._anchored_query(), parameters={"anchor": "ENT@A"}),
            catalog=ViewpointCatalog.empty(),
            read_access=store,
        )
        assert result.anchor_ids == ("ENT@A",)
        assert result.entity_ids == ("ENT@A",)

    def test_unanchored_execution_has_no_anchor_ids(self) -> None:
        store = Store(entities={"ENT@A": entity(artifact_id="ENT@A")})
        query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup())
        result = _run(ViewpointExecutionRequest(query=query), catalog=ViewpointCatalog.empty(), read_access=store)
        assert result.anchor_ids == ()

    def test_anchored_execution_ranks_entities_by_modeled_distance(self) -> None:
        store = Store(
            entities={"ENT@A": entity(artifact_id="ENT@A"), "ENT@B": entity(artifact_id="ENT@B")},
            connections=[connection(artifact_id="CON@ab", source="ENT@A", target="ENT@B")],
        )
        query = ExecutableViewpointQuery(
            entity_criteria=self._anchored_query().entity_criteria,
            parameters=self._anchored_query().parameters,
            include_connected=(NeighborInclusion(),),
        )
        result = _run(
            ViewpointExecutionRequest(query=query, parameters={"anchor": "ENT@A"}),
            catalog=ViewpointCatalog.empty(),
            read_access=store,
        )
        by_id = {e.id: e.anchor_modeled_distance for e in result.entities}
        assert by_id == {"ENT@A": 0, "ENT@B": 1}

    def test_scope_mode_execution_carries_a_target_population_summary(self) -> None:
        from src.domain.concept_scope import ConceptScope

        store = Store(entities={"ENT@P": entity(artifact_id="ENT@P", artifact_type="process")})
        definition = _definition(
            scope=ConceptScope(entity_types=frozenset({"application-component", "process"})),
            selection_mode="scope",
        )
        result = _run(
            ViewpointExecutionRequest(slug="test-viewpoint"),
            catalog=ViewpointCatalog(entries=(definition,)),
            read_access=store,
        )
        assert result.target_population is not None
        assert result.target_population.target_count == 1

    def test_ad_hoc_query_has_unknown_target_population(self) -> None:
        store = Store(entities={"ENT@A": entity(artifact_id="ENT@A")})
        query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup())
        result = _run(ViewpointExecutionRequest(query=query), catalog=ViewpointCatalog.empty(), read_access=store)
        assert result.target_population is None

    def test_unanchored_execution_leaves_entities_unranked(self) -> None:
        store = Store(entities={"ENT@A": entity(artifact_id="ENT@A")})
        query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup())
        result = _run(ViewpointExecutionRequest(query=query), catalog=ViewpointCatalog.empty(), read_access=store)
        assert all(e.anchor_modeled_distance is None for e in result.entities)


class TestSummaries:
    def test_entity_and_connection_summaries(self) -> None:
        store = Store(
            entities={
                "ENT@A": entity(artifact_id="ENT@A", name="Alpha", group="core", specialization="custom-spec"),
                "ENT@B": entity(artifact_id="ENT@B", name="Beta"),
            },
            connections=[connection(artifact_id="CON@ab", source="ENT@A", target="ENT@B")],
        )
        definition = _definition(query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup()))
        catalog = ViewpointCatalog(entries=(definition,))
        result = _run(ViewpointExecutionRequest(slug="test-viewpoint"), catalog=catalog, read_access=store)

        assert result.entity_ids == ("ENT@A", "ENT@B")
        alpha = next(e for e in result.entities if e.id == "ENT@A")
        assert alpha.name == "Alpha"
        assert alpha.type == "application-component"
        assert alpha.specialization_slugs == ("custom-spec",)
        assert alpha.group == "core"
        assert alpha.membership == "primary"
        assert isinstance(alpha.status, str) and alpha.status != ""
        assert isinstance(alpha.version, str) and alpha.version != ""

        assert result.connection_ids == ("CON@ab",)
        link = result.connections[0]
        assert (link.type, link.source, link.target) == ("archimate-serving", "ENT@A", "ENT@B")


class TestTruncation:
    def _store_with_expanded_neighbors(self) -> Store:
        primary = entity(artifact_id="ENT@A", artifact_type="application-component")
        neighbor1 = entity(artifact_id="ENT@N1", artifact_type="process")
        neighbor2 = entity(artifact_id="ENT@N2", artifact_type="process")
        link1 = connection(artifact_id="CON@1", source="ENT@A", target="ENT@N1")
        link2 = connection(artifact_id="CON@2", source="ENT@A", target="ENT@N2")
        return Store(entities={"ENT@A": primary, "ENT@N1": neighbor1, "ENT@N2": neighbor2}, connections=[link1, link2])

    def _definition_with_inclusion(self) -> ViewpointDefinition:
        return _definition(
            query=ExecutableViewpointQuery(
                entity_criteria=EntityCriteriaGroup(children=(_type_condition("application-component"),)),
                include_connected=(NeighborInclusion(),),
            )
        )

    def test_expanded_dropped_before_primary(self) -> None:
        store = self._store_with_expanded_neighbors()
        catalog = ViewpointCatalog(entries=(self._definition_with_inclusion(),))
        result = _run(ViewpointExecutionRequest(slug="test-viewpoint", limit=2), catalog=catalog, read_access=store)
        assert result.entity_ids == ("ENT@A", "ENT@N1")
        assert result.returned_entity_count == 2
        assert result.total_entity_count == 3
        assert result.truncated is True
        assert result.entity_limit == 2

    def test_connections_refiltered_to_retained_entities(self) -> None:
        store = self._store_with_expanded_neighbors()
        catalog = ViewpointCatalog(entries=(self._definition_with_inclusion(),))
        result = _run(ViewpointExecutionRequest(slug="test-viewpoint", limit=2), catalog=catalog, read_access=store)
        assert result.total_connection_count == 2
        assert result.returned_connection_count == 1
        assert result.connection_ids == ("CON@1",)

    def test_limit_clamped_to_max_entities(self) -> None:
        store = self._store_with_expanded_neighbors()
        catalog = ViewpointCatalog(entries=(self._definition_with_inclusion(),))
        result = _run(
            ViewpointExecutionRequest(slug="test-viewpoint", limit=1000),
            catalog=catalog,
            read_access=store,
            max_entities=1,
            default_limit=1,
        )
        assert result.entity_limit == 1
        assert result.returned_entity_count == 1

    def test_untruncated_result_reports_false(self) -> None:
        store = Store(entities={"ENT@A": entity(artifact_id="ENT@A")})
        definition = _definition(query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup()))
        catalog = ViewpointCatalog(entries=(definition,))
        result = _run(ViewpointExecutionRequest(slug="test-viewpoint"), catalog=catalog, read_access=store)
        assert result.truncated is False
        assert result.total_entity_count == result.returned_entity_count == 1


class TestMatrixAxes:
    def _store(self) -> Store:
        return Store(
            entities={
                "ENT@A": entity(artifact_id="ENT@A", artifact_type="application-component"),
                "ENT@B": entity(artifact_id="ENT@B", artifact_type="process"),
                "ENT@C": entity(artifact_id="ENT@C", artifact_type="process", name="Neither"),
            }
        )

    def _matrix_definition(self) -> ViewpointDefinition:
        return _definition(
            query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup()),
            presentation=PresentationSpec(
                representation="matrix",
                row_criteria=EntityCriteriaGroup(children=(_type_condition("application-component"),)),
                column_criteria=EntityCriteriaGroup(
                    children=(AttributeCondition(attribute="name", comparator="eq", value=ValueRef(literal="Beta")),)
                ),
            ),
        )

    def test_present_for_criteria_axes_matrix(self) -> None:
        store = self._store()
        store.entities["ENT@B"] = entity(artifact_id="ENT@B", artifact_type="process", name="Beta")
        catalog = ViewpointCatalog(entries=(self._matrix_definition(),))
        result = _run(ViewpointExecutionRequest(slug="test-viewpoint"), catalog=catalog, read_access=store)
        assert result.matrix_axes is not None
        assert result.matrix_axes.row_entity_ids == ("ENT@A",)
        assert result.matrix_axes.column_entity_ids == ("ENT@B",)

    def test_complement_is_unrendered_entities(self) -> None:
        store = self._store()
        store.entities["ENT@B"] = entity(artifact_id="ENT@B", artifact_type="process", name="Beta")
        catalog = ViewpointCatalog(entries=(self._matrix_definition(),))
        result = _run(ViewpointExecutionRequest(slug="test-viewpoint"), catalog=catalog, read_access=store)
        axis_union = set(result.matrix_axes.row_entity_ids) | set(result.matrix_axes.column_entity_ids)
        unrendered = set(result.entity_ids) - axis_union
        assert unrendered == {"ENT@C"}

    def test_absent_without_matrix_presentation(self) -> None:
        store = Store(entities={"ENT@A": entity(artifact_id="ENT@A")})
        definition = _definition(query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup()))
        catalog = ViewpointCatalog(entries=(definition,))
        result = _run(ViewpointExecutionRequest(slug="test-viewpoint"), catalog=catalog, read_access=store)
        assert result.matrix_axes is None


class TestRepoScope:
    def test_filters_entities_and_echoes_scope(self) -> None:
        store = Store(
            entities={
                "ENT@enterprise": entity(artifact_id="ENT@enterprise"),
                "ENT@engagement": entity(artifact_id="ENT@engagement"),
            },
            enterprise_ids=frozenset({"ENT@enterprise"}),
        )
        definition = _definition(
            query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup(), repo_scope="enterprise")
        )
        catalog = ViewpointCatalog(entries=(definition,))
        result = _run(ViewpointExecutionRequest(slug="test-viewpoint"), catalog=catalog, read_access=store)
        assert result.entity_ids == ("ENT@enterprise",)
        assert result.repo_scope == "enterprise"


class TestIndexRevisionAndDuration:
    def test_index_generation_passthrough(self) -> None:
        store = Store(entities={"ENT@A": entity(artifact_id="ENT@A")})
        definition = _definition(query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup()))
        catalog = ViewpointCatalog(entries=(definition,))
        result = _run(
            ViewpointExecutionRequest(slug="test-viewpoint"), catalog=catalog, read_access=store, index_generation=42
        )
        assert result.index_generation == 42

    def test_duration_is_recorded(self) -> None:
        store = Store(entities={"ENT@A": entity(artifact_id="ENT@A")})
        definition = _definition(query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup()))
        catalog = ViewpointCatalog(entries=(definition,))
        result = _run(ViewpointExecutionRequest(slug="test-viewpoint"), catalog=catalog, read_access=store)
        assert result.duration_ms >= 0.0


class TestTimeout:
    def test_negative_budget_always_raises_typed_error_no_partial_result(self) -> None:
        store = Store(entities={"ENT@A": entity(artifact_id="ENT@A")})
        definition = _definition(query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup()))
        catalog = ViewpointCatalog(entries=(definition,))
        with pytest.raises(ViewpointExecutionTimeoutError) as excinfo:
            _run(
                ViewpointExecutionRequest(slug="test-viewpoint"),
                catalog=catalog,
                read_access=store,
                timeout_seconds=-1.0,
            )
        assert excinfo.value.timeout_seconds == -1.0


class TestResolveViewpointDefinition:
    """``resolve_viewpoint_definition`` — the resolver shared by ``evaluate_viewpoint`` and
    ``project_viewpoint_repository`` (a delegation regression: both must resolve slugs
    identically)."""

    def test_unknown_slug_raises(self) -> None:
        with pytest.raises(UnknownViewpointSlugError):
            resolve_viewpoint_definition("missing", None, catalog=ViewpointCatalog.empty())

    def test_known_slug_resolves_definition_and_identity(self) -> None:
        definition = _definition(query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup()))
        catalog = ViewpointCatalog(entries=(definition,))
        resolved, slug, version = resolve_viewpoint_definition("test-viewpoint", None, catalog=catalog)
        assert resolved is definition
        assert (slug, version) == ("test-viewpoint", 3)

    def test_ad_hoc_query_has_no_identity(self) -> None:
        query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup())
        resolved, slug, version = resolve_viewpoint_definition(None, query, catalog=ViewpointCatalog.empty())
        assert resolved.query == query
        assert (slug, version) == (None, None)

    def test_neither_slug_nor_query_raises(self) -> None:
        with pytest.raises(ValueError):
            resolve_viewpoint_definition(None, None, catalog=ViewpointCatalog.empty())


class TestProjectViewpointRepository:
    """``project_viewpoint_repository`` — the styled, GUI-only sibling of the unstyled
    execution result (the data source for exploration/table/matrix/diagram
    representations)."""

    def test_delegates_to_project_repository_with_resolved_definition(self) -> None:
        store = Store(entities={"ENT@A": entity(artifact_id="ENT@A", group="core")})
        definition = _definition(
            query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup()),
            presentation=PresentationSpec(
                representation="exploration",
                styling_rules=(
                    StyleRule(capability="node_color", match_criteria=EntityCriteriaGroup(), value="positive"),
                ),
            ),
        )
        catalog = ViewpointCatalog(entries=(definition,))
        projection = project_viewpoint_repository(
            "test-viewpoint", None, catalog=catalog, read_access=store, registries=REGISTRIES
        )
        assert projection.target == "repository"
        item = next(i for i in projection.items if i.item_id == "ENT@A")
        assert item.style == {"node_color": "positive"}

    def test_unknown_slug_raises(self) -> None:
        with pytest.raises(UnknownViewpointSlugError):
            project_viewpoint_repository(
                "missing", None, catalog=ViewpointCatalog.empty(), read_access=Store(), registries=REGISTRIES
            )


class TestDeferredDerivedAttributes:
    """A `traversal: derived` derived attribute that no criteria condition ever
    references (the common case — used only by a presentation style rule) must not be
    evaluated for the whole scoped population: each evaluation is a full bounded
    relationship-derivation search, so doing it for every scoped entity instead of only
    the entities that end up retained turns population size into per-execution cost
    regardless of how selective the query actually is."""

    def _store_with_noise(self, *, noise_count: int, matched_ids: tuple[str, ...]) -> Store:
        entities = {
            entity_id: entity(artifact_id=entity_id, artifact_type="application-component", group="matched")
            for entity_id in matched_ids
        }
        entities.update(
            {
                f"ENT@noise-{i}": entity(
                    artifact_id=f"ENT@noise-{i}", artifact_type="application-component", group="noise"
                )
                for i in range(noise_count)
            }
        )
        return Store(entities=entities)

    def _registries_with_derivation_catalog(self) -> RegistrySnapshot:
        return RegistrySnapshot(
            known_entity_types=frozenset({"application-component"}),
            known_connection_types=frozenset(),
            known_specialization_slugs=frozenset(),
            entity_attribute_types={},
            connection_attribute_types={},
            derivation_catalog=derivation_examples.catalog(),
        )

    def _spy_on_derive_relationships(self, monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], list[int]]:
        """Returns `(anchors_seen, call_sizes)`: every anchor id passed across all calls
        (for asserting which entities were derived for), and the size of each individual
        call's own anchor set (for asserting derivation is batched into one combined call,
        not one call per entity — the whole point of this optimization)."""
        anchors_seen: list[str] = []
        call_sizes: list[int] = []
        real_derive_relationships = viewpoint_derived_relationship_batch_module.derive_relationships

        def _counting_derive_relationships(request: object, **kwargs: object) -> object:
            anchors_seen.extend(request.anchors)  # type: ignore[attr-defined]
            call_sizes.append(len(request.anchors))  # type: ignore[attr-defined]
            return real_derive_relationships(request, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(
            viewpoint_derived_relationship_batch_module, "derive_relationships", _counting_derive_relationships
        )
        return anchors_seen, call_sizes

    def test_a_presentation_only_derived_attribute_is_not_evaluated_for_unmatched_entities(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        matched_ids = ("ENT@match-1", "ENT@match-2")
        store = self._store_with_noise(noise_count=20, matched_ids=matched_ids)
        registries = self._registries_with_derivation_catalog()
        anchors_seen, call_sizes = self._spy_on_derive_relationships(monkeypatch)

        definition = _definition(
            query=ExecutableViewpointQuery(
                entity_criteria=EntityCriteriaGroup(
                    children=(
                        AttributeCondition(attribute="group", comparator="eq", value=ValueRef(literal="matched")),
                    )
                ),
                derived=(
                    DerivedAttribute("impact-distance", traversal="derived", direction="outgoing", reduce="min",
                                      of="relationship.hops"),
                ),
            ),
            presentation=PresentationSpec(
                representation="exploration",
                styling_rules=(
                    StyleRule(
                        capability="node_color", mode="scale", scale_attribute="derived.impact-distance",
                        scale_min=1, scale_max=4, scale_tokens=("heat-near", "heat-far"),
                    ),
                ),
            ),
        )
        catalog = ViewpointCatalog(entries=(definition,))
        projection = project_viewpoint_repository(
            "test-viewpoint", None, catalog=catalog, read_access=store, registries=registries
        )
        assert {item.item_id for item in projection.items} == set(matched_ids)
        # Only the two matched entities were ever handed to the derivation engine — never
        # the twenty unmatched "noise" entities also present in scope.
        assert set(anchors_seen) == set(matched_ids)
        # And both were folded into one combined call, not one call per entity.
        assert call_sizes == [2]

    def test_a_criteria_referenced_derived_attribute_still_evaluates_over_the_full_scope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A derived attribute a condition actually filters on must stay evaluated before
        # filtering happens — there is no way to know who matches without it.
        matched_ids = ("ENT@match-1",)
        store = self._store_with_noise(noise_count=5, matched_ids=matched_ids)
        registries = self._registries_with_derivation_catalog()
        anchors_seen, call_sizes = self._spy_on_derive_relationships(monkeypatch)

        definition = _definition(
            query=ExecutableViewpointQuery(
                entity_criteria=EntityCriteriaGroup(
                    children=(AttributeCondition(attribute="derived.impact-distance", comparator="exists"),)
                ),
                derived=(
                    DerivedAttribute("impact-distance", traversal="derived", direction="outgoing", reduce="min",
                                      of="relationship.hops"),
                ),
            ),
        )
        catalog = ViewpointCatalog(entries=(definition,))
        evaluate_viewpoint(
            ViewpointExecutionRequest(slug="test-viewpoint"), catalog=catalog, read_access=store, registries=registries,
            **_DEFAULTS,
        )
        # Six scoped entities (one matched, five noise) — the attribute is referenced by
        # the primary criteria, so every one of them had to be evaluated to decide who
        # matches the "derived.impact-distance exists" condition — but still folded into
        # one combined call, not six separate ones.
        assert set(anchors_seen) == {"ENT@match-1", *(f"ENT@noise-{i}" for i in range(5))}
        assert call_sizes == [6]
