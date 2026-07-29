"""Target-population declaration and result classification (honest-empty semantics)."""

from __future__ import annotations

from src.domain.concept_scope import ConceptScope
from src.domain.ontology_representation.ontology_types import EntityTypeInfo
from src.domain.viewpoints.viewpoint_criteria import EntityCriteriaGroup
from src.domain.viewpoints.viewpoint_target_population import (
    declared_target_types,
    is_structural_helper,
    summarize_target_population,
)
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery, PresentationSpec, ViewpointDefinition


def _info(type_name: str, classes: tuple[str, ...] = ()) -> EntityTypeInfo:
    return EntityTypeInfo(
        artifact_type=type_name, prefix="XXX", hierarchy=("common",), classes=classes,
        create_when="", never_create_when="",
    )


_INFOS = {
    "and-junction": _info("and-junction", ("junction",)),
    "grouping": _info("grouping", ("composite-element",)),
    "capability": _info("capability"),
    "outcome": _info("outcome"),
}


def _definition(**kw: object) -> ViewpointDefinition:
    defaults: dict[str, object] = dict(slug="test", version=1, name="Test")
    defaults.update(kw)
    return ViewpointDefinition(**defaults)  # type: ignore[arg-type]


class TestStructuralHelpers:
    def test_junction_class_and_grouping_type_are_helpers(self) -> None:
        assert is_structural_helper("and-junction", _INFOS["and-junction"])
        assert is_structural_helper("grouping", _INFOS["grouping"])
        assert not is_structural_helper("capability", _INFOS["capability"])


class TestDeclaredTargetTypes:
    def test_explicit_presentation_declaration_wins_in_any_mode(self) -> None:
        definition = _definition(
            query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup()),
            selection_mode="query",
            presentation=PresentationSpec(representation="table", target_types=("capability",)),
        )
        assert declared_target_types(definition, _INFOS) == ("capability",)

    def test_scope_mode_derives_targets_mechanically_minus_helpers(self) -> None:
        definition = _definition(
            scope=ConceptScope(entity_types=frozenset({"capability", "and-junction", "grouping"})),
            selection_mode="scope",
        )
        assert declared_target_types(definition, _INFOS) == ("capability",)

    def test_legacy_scope_only_definition_also_derives_mechanically(self) -> None:
        definition = _definition(scope=ConceptScope(entity_types=frozenset({"capability"})))
        assert declared_target_types(definition, _INFOS) == ("capability",)

    def test_undeclared_query_mode_definition_has_unknown_targets(self) -> None:
        definition = _definition(
            scope=ConceptScope(entity_types=frozenset({"capability"})),  # stale INACTIVE layer
            query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup()),
            selection_mode="query",
        )
        assert declared_target_types(definition, _INFOS) is None

    def test_query_mode_with_declaration_uses_it_not_the_stale_scope(self) -> None:
        definition = _definition(
            scope=ConceptScope(entity_types=frozenset({"capability"})),  # stale INACTIVE layer
            query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup()),
            selection_mode="query",
            presentation=PresentationSpec(representation="table", target_types=("outcome",)),
        )
        assert declared_target_types(definition, _INFOS) == ("outcome",)


class TestSummarizeTargetPopulation:
    def test_target_empty_with_incidental_and_structural_content(self) -> None:
        summary = summarize_target_population(
            ("capability",),
            ["outcome"] * 15 + ["and-junction"] * 5 + ["grouping"] * 2,
            _INFOS,
        )
        assert summary.target_count == 0
        assert summary.incidental_type_counts == {"outcome": 15}
        assert summary.structural_count == 7

    def test_helpers_only_result(self) -> None:
        summary = summarize_target_population(("capability",), ["and-junction"] * 7, _INFOS)
        assert (summary.target_count, summary.incidental_type_counts, summary.structural_count) == (0, {}, 7)

    def test_target_present(self) -> None:
        summary = summarize_target_population(("capability",), ["capability", "capability", "outcome"], _INFOS)
        assert summary.target_count == 2
        assert summary.incidental_type_counts == {"outcome": 1}
