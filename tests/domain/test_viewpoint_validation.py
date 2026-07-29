"""Tests for the three-mode registry-aware viewpoint validator:
`load` downgrades registry findings to warnings and skips ergonomics/lifecycle checks,
`save` promotes them to errors and adds ergonomics checks, `persist_edit` adds lifecycle
rules against prior state."""

from __future__ import annotations

import pytest

from src.domain.concept_scope import ConceptScope, HierarchyPredicate
from src.domain.ontology_representation.ontology_types import EntityTypeInfo
from src.domain.viewpoints.viewpoint_criteria import (
    AttributeCondition,
    ConnectionCriteriaGroup,
    ConnectionSelection,
    EntityCriteriaGroup,
    ValueRef,
)
from src.domain.viewpoints.viewpoint_validation import validate_viewpoint_definition
from src.domain.viewpoints.viewpoints import (
    ColumnSpec,
    ExecutableViewpointQuery,
    PresentationSpec,
    ViewpointCatalog,
    ViewpointDefinition,
)

_KNOWN_ENTITY_TYPES = frozenset({"requirement", "goal"})
_KNOWN_CONNECTION_TYPES = frozenset({"archimate-serving", "archimate-realization"})
_KNOWN_SPECIALIZATIONS = frozenset({"business-service"})
_ENTITY_ATTRIBUTE_TYPES = {"criticality": "string", "priority": "integer"}
_CONNECTION_ATTRIBUTE_TYPES = {"weight": "number"}


def _validate(definition: ViewpointDefinition, *, mode: str = "save", **overrides: object) -> tuple[object, ...]:
    kwargs: dict[str, object] = {
        "known_entity_types": _KNOWN_ENTITY_TYPES,
        "known_connection_types": _KNOWN_CONNECTION_TYPES,
        "known_specialization_slugs": _KNOWN_SPECIALIZATIONS,
        "entity_attribute_types": _ENTITY_ATTRIBUTE_TYPES,
        "connection_attribute_types": _CONNECTION_ATTRIBUTE_TYPES,
    }
    kwargs.update(overrides)
    return validate_viewpoint_definition(definition, mode=mode, **kwargs)  # type: ignore[arg-type]


def _condition(attribute: str, comparator: str, value: object) -> AttributeCondition:
    return AttributeCondition(attribute=attribute, comparator=comparator, value=ValueRef(kind="literal", literal=value))


def _base_definition(
    *,
    version: int = 1,
    scope: ConceptScope | None = None,
    query: ExecutableViewpointQuery | None = None,
    presentation: PresentationSpec | None = None,
) -> ViewpointDefinition:
    return ViewpointDefinition(
        slug="v",
        version=version,
        name="V",
        scope=scope if scope is not None else ConceptScope.unrestricted(),
        query=query,
        presentation=presentation,
    )


class TestScopeValidation:
    def test_valid_scope_has_no_issues(self) -> None:
        definition = _base_definition(scope=ConceptScope(entity_types=frozenset({"requirement"})))
        assert _validate(definition) == ()

    def test_unknown_entity_type_in_scope_is_rejected(self) -> None:
        definition = _base_definition(scope=ConceptScope(entity_types=frozenset({"bogus-type"})))
        issues = _validate(definition)
        assert any("bogus-type" in i.message for i in issues)

    def test_unknown_connection_type_in_scope_is_rejected(self) -> None:
        definition = _base_definition(scope=ConceptScope(connection_types=frozenset({"bogus-conn"})))
        issues = _validate(definition)
        assert any("bogus-conn" in i.message for i in issues)

    def test_valid_excluded_entity_type_has_no_issues(self) -> None:
        definition = _base_definition(scope=ConceptScope(excluded_entity_types=frozenset({"requirement"})))
        assert _validate(definition) == ()

    def test_unknown_excluded_entity_type_is_rejected(self) -> None:
        definition = _base_definition(scope=ConceptScope(excluded_entity_types=frozenset({"bogus-type"})))
        issues = _validate(definition)
        assert any("bogus-type" in i.message for i in issues)

    def test_unknown_excluded_connection_type_is_rejected(self) -> None:
        definition = _base_definition(scope=ConceptScope(excluded_connection_types=frozenset({"bogus-conn"})))
        issues = _validate(definition)
        assert any("bogus-conn" in i.message for i in issues)

    def test_valid_excluded_domain_has_no_issues(self) -> None:
        info = EntityTypeInfo(
            artifact_type="requirement", prefix="REQ", hierarchy=("motivation", "requirement"), classes=(),
            create_when="", never_create_when="",
        )
        motivation_predicate = HierarchyPredicate(index=0, values=frozenset({"motivation"}))
        scope = ConceptScope(excluded_hierarchy_predicates=(motivation_predicate,))
        definition = _base_definition(scope=scope)
        assert _validate(definition, entity_type_infos={"requirement": info}) == ()

    def test_unknown_excluded_domain_is_rejected(self) -> None:
        bogus_predicate = HierarchyPredicate(index=0, values=frozenset({"bogus-domain"}))
        scope = ConceptScope(excluded_hierarchy_predicates=(bogus_predicate,))
        definition = _base_definition(scope=scope)
        issues = _validate(definition)
        assert any("bogus-domain" in i.message for i in issues)


class TestQueryValidation:
    def test_unknown_entity_type_value_is_rejected(self) -> None:
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(_condition("type", "eq", "bogus"),))
        )
        issues = _validate(_base_definition(query=query))
        assert any(i.code == "unknown-value" for i in issues)

    def test_unknown_specialization_value_is_rejected(self) -> None:
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(_condition("specialization", "eq", "bogus-spec"),))
        )
        issues = _validate(_base_definition(query=query))
        assert any(i.code == "unknown-value" for i in issues)

    def test_unknown_attribute_is_rejected(self) -> None:
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(_condition("not-a-real-attribute", "eq", "x"),))
        )
        issues = _validate(_base_definition(query=query))
        assert any(i.code == "unknown-attribute" for i in issues)

    def test_numeric_operator_on_string_attribute_is_a_type_mismatch(self) -> None:
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(_condition("criticality", "lt", 1),))
        )
        issues = _validate(_base_definition(query=query))
        assert any(i.code == "operator-type-mismatch" for i in issues)

    def test_numeric_operator_on_numeric_attribute_is_valid(self) -> None:
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(_condition("priority", "gte", 2),))
        )
        assert _validate(_base_definition(query=query)) == ()

    def test_like_operator_on_numeric_attribute_is_a_type_mismatch(self) -> None:
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(_condition("priority", "like", "%1%"),))
        )
        issues = _validate(_base_definition(query=query))
        assert any(i.code == "operator-type-mismatch" for i in issues)

    def test_ilike_operator_on_string_attribute_is_valid(self) -> None:
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(_condition("criticality", "ilike", "%high%"),))
        )
        assert _validate(_base_definition(query=query)) == ()

    def test_not_in_on_string_attribute_checks_known_slugs(self) -> None:
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(_condition("type", "not_in", ["bogus"]),))
        )
        issues = _validate(_base_definition(query=query))
        assert any(i.code == "unknown-value" for i in issues)

    def test_not_in_with_scalar_value_is_an_unsupported_shape(self) -> None:
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(_condition("priority", "not_in", 1),))
        )
        issues = _validate(_base_definition(query=query))
        assert any(i.code == "unsupported-value-shape" for i in issues)

    def test_like_with_non_string_literal_is_an_unsupported_shape(self) -> None:
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(_condition("criticality", "like", 5),))
        )
        issues = _validate(_base_definition(query=query))
        assert any(i.code == "unsupported-value-shape" for i in issues)

    def test_load_mode_downgrades_registry_findings_to_warnings(self) -> None:
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(_condition("bogus", "eq", "x"),))
        )
        issues = _validate(_base_definition(query=query), mode="load")
        assert issues
        assert all(i.severity == "warning" for i in issues)

    def test_load_mode_skips_depth_cap(self) -> None:
        deep = EntityCriteriaGroup(children=(_condition("priority", "eq", 1),))
        for _ in range(6):
            deep = EntityCriteriaGroup(children=(deep,))
        query = ExecutableViewpointQuery(entity_criteria=deep)
        assert _validate(_base_definition(query=query), mode="load") == ()

    def test_save_mode_enforces_depth_cap(self) -> None:
        deep = EntityCriteriaGroup(children=(_condition("priority", "eq", 1),))
        for _ in range(6):
            deep = EntityCriteriaGroup(children=(deep,))
        query = ExecutableViewpointQuery(entity_criteria=deep)
        issues = _validate(_base_definition(query=query), mode="save")
        assert any(i.code == "depth-cap-exceeded" for i in issues)

    def test_custom_depth_cap_is_honored(self) -> None:
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(
                children=(EntityCriteriaGroup(children=(_condition("priority", "eq", 1),)),)
            )
        )
        assert _validate(_base_definition(query=query), mode="save", depth_cap=1) != ()
        assert _validate(_base_definition(query=query), mode="save", depth_cap=2) == ()

    def test_empty_non_root_group_is_a_save_error(self) -> None:
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(EntityCriteriaGroup(children=()),))
        )
        issues = _validate(_base_definition(query=query), mode="save")
        assert any(i.code == "empty-non-root-group" for i in issues)

    def test_empty_root_group_is_valid(self) -> None:
        query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup())
        assert _validate(_base_definition(query=query), mode="save") == ()

    def test_connection_attribute_predicate_validated_against_connection_types(self) -> None:
        query = ExecutableViewpointQuery(
            connections=ConnectionSelection(
                criteria=ConnectionCriteriaGroup(children=(_condition("weight", "gte", 1),))
            )
        )
        assert _validate(_base_definition(query=query)) == ()


class TestPresentationValidation:
    def test_valid_display_option_has_no_issues(self) -> None:
        presentation = PresentationSpec(representation="exploration", display_options={"node_color": True})
        assert _validate(_base_definition(presentation=presentation)) == ()

    def test_unsupported_display_option_is_rejected(self) -> None:
        presentation = PresentationSpec(representation="table", display_options={"node_color": True})
        issues = _validate(_base_definition(presentation=presentation))
        assert any(i.code == "unsupported-display-option" for i in issues)

    def test_unknown_column_source_is_rejected(self) -> None:
        presentation = PresentationSpec(representation="table", columns=(ColumnSpec(label="X", source="not-real"),))
        issues = _validate(_base_definition(presentation=presentation))
        assert any(i.code == "unknown-attribute" for i in issues)

    @pytest.mark.parametrize("representation", ["exploration", "diagram"])
    def test_label_attribute_accepted_on_exploration_and_diagram(self, representation: str) -> None:
        presentation = PresentationSpec(representation=representation, display_options={"label_attribute": "priority"})
        assert _validate(_base_definition(presentation=presentation)) == ()

    def test_label_attribute_accepts_derived_path_without_registry_lookup(self) -> None:
        presentation = PresentationSpec(
            representation="exploration", display_options={"label_attribute": "derived.impact-distance"}
        )
        assert _validate(_base_definition(presentation=presentation)) == ()

    @pytest.mark.parametrize("representation", ["table", "matrix"])
    def test_label_attribute_rejected_on_other_representations(self, representation: str) -> None:
        presentation = PresentationSpec(representation=representation, display_options={"label_attribute": "priority"})
        issues = _validate(_base_definition(presentation=presentation))
        assert any(i.code == "unsupported-display-option" for i in issues)

    def test_label_attribute_unknown_path_is_rejected(self) -> None:
        presentation = PresentationSpec(representation="exploration", display_options={"label_attribute": "not-real"})
        issues = _validate(_base_definition(presentation=presentation))
        assert any(i.code == "unknown-attribute" for i in issues)

    def test_group_by_dimension_keyword_is_always_valid(self) -> None:
        presentation = PresentationSpec(representation="table", group_by="group")
        assert _validate(_base_definition(presentation=presentation)) == ()

    def test_group_by_unknown_attribute_is_rejected(self) -> None:
        presentation = PresentationSpec(representation="table", group_by="not-real")
        issues = _validate(_base_definition(presentation=presentation))
        assert any(i.code == "unknown-attribute" for i in issues)

    def test_group_by_known_attribute_is_valid(self) -> None:
        presentation = PresentationSpec(representation="table", group_by="priority")
        assert _validate(_base_definition(presentation=presentation)) == ()

    def test_matrix_mixing_grouped_and_criteria_axes_is_rejected(self) -> None:
        presentation = PresentationSpec(
            representation="matrix",
            row_by="type",
            row_criteria=EntityCriteriaGroup(),
            column_criteria=EntityCriteriaGroup(),
        )
        issues = _validate(_base_definition(presentation=presentation))
        assert any(i.code == "matrix-axis-mode-mixed" for i in issues)

    def test_matrix_criteria_axes_require_both(self) -> None:
        presentation = PresentationSpec(representation="matrix", row_criteria=EntityCriteriaGroup())
        issues = _validate(_base_definition(presentation=presentation))
        assert any(i.code == "matrix-axis-incomplete" for i in issues)

    def test_matrix_criteria_axes_both_present_is_valid(self) -> None:
        presentation = PresentationSpec(
            representation="matrix", row_criteria=EntityCriteriaGroup(), column_criteria=EntityCriteriaGroup()
        )
        assert _validate(_base_definition(presentation=presentation)) == ()


class TestLifecycleValidation:
    def test_semantic_edit_without_version_bump_is_rejected(self) -> None:
        prior = _base_definition(version=1)
        edited = _base_definition(version=1, scope=ConceptScope(entity_types=frozenset({"requirement"})))
        issues = _validate(edited, mode="persist_edit", prior_definition=prior)
        assert any(i.code == "version-not-bumped" for i in issues)

    def test_semantic_edit_with_version_bump_is_accepted(self) -> None:
        prior = _base_definition(version=1)
        edited = _base_definition(version=2, scope=ConceptScope(entity_types=frozenset({"requirement"})))
        assert _validate(edited, mode="persist_edit", prior_definition=prior) == ()

    def test_descriptive_only_edit_does_not_require_bump(self) -> None:
        prior = ViewpointDefinition(slug="v", version=1, name="V")
        edited = ViewpointDefinition(slug="v", version=1, name="V2")
        assert _validate(edited, mode="persist_edit", prior_definition=prior) == ()

    def test_slug_collision_on_create_is_rejected(self) -> None:
        catalog = ViewpointCatalog((ViewpointDefinition(slug="v", version=1, name="Existing"),))
        definition = _base_definition()
        issues = _validate(definition, mode="persist_edit", catalog=catalog)
        assert any(i.code == "slug-collision" for i in issues)


_KNOWN_ISSUE_CODES = frozenset(
    {
        "unknown-type",
        "unexpected-value",
        "value-ref-missing-endpoint",
        "value-ref-endpoint-outside-connection",
        "value-ref-missing-attribute",
        "unsupported-value-shape",
        "unknown-value",
        "unknown-attribute",
        "operator-type-mismatch",
        "empty-non-root-group",
        "symmetric-direction-ineffective",
        "depth-cap-exceeded",
        "unsupported-capability",
        "missing-match-criteria",
        "capability-criteria-kind-mismatch",
        "missing-range-attribute",
        "range-band-overlap",
        "unsupported-display-option",
        "matrix-axis-mode-mixed",
        "matrix-axis-incomplete",
        "matrix-without-connections",
        "version-not-bumped",
        "slug-collision",
        "unknown-binding",
        "binding-cycle",
        "duplicate-binding-name",
        "binding-type-mismatch",
        "binding-attribute-type-ambiguous",
        "binding-count-exceeded",
        "binding-derived-reference-unsupported",
        "aggregate-over-instance",
        "include-in-result-shape-unsupported",
        "unquantified-set-comparison",
        "tuple-comparator-unsupported",
        "unknown-parameter",
        "duplicate-parameter-name",
        "parameter-type-mismatch",
        "parameter-count-exceeded",
        "derived-attribute-unknown",
        "derived-attribute-count-exceeded",
        "derived-attribute-reference-unsupported",
        "derived-of-missing",
        "derived-reduce-type-mismatch",
    }
)


class TestIssueCodeStability:
    """Codes are a public contract. This is a
    snapshot, not an exhaustive check — a new code is fine to add; renaming or removing one is
    a breaking change that must be a deliberate, visible diff to this set."""

    def test_every_emitted_code_is_in_the_known_set(self) -> None:
        deep = EntityCriteriaGroup(children=(_condition("priority", "eq", 1),))
        for _ in range(6):
            deep = EntityCriteriaGroup(children=(deep,))
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(
                children=(
                    _condition("type", "eq", "bogus"),
                    _condition("not-a-real-attribute", "eq", "x"),
                    _condition("criticality", "lt", 1),
                    EntityCriteriaGroup(children=()),
                )
            )
        )
        presentation = PresentationSpec(representation="table", display_options={"node_color": True})
        definition = _base_definition(query=query, presentation=presentation)
        issues = _validate(definition, mode="save", depth_cap=1)
        emitted = {i.code for i in issues}
        assert emitted
        assert emitted <= _KNOWN_ISSUE_CODES, f"unrecognized code(s): {emitted - _KNOWN_ISSUE_CODES}"
