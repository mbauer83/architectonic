"""The shipped ``motivation-coverage`` viewpoint: it loads, validates cleanly against the real
registries, and carries its declared pattern set with the branch/leaf/diagnostic roles intact."""

from __future__ import annotations

import pytest

from src.application.viewpoints.registry_snapshot import build_registry_snapshot
from src.domain.viewpoints.viewpoint_trace_pattern_validation import expand_branch_edges
from src.domain.viewpoints.viewpoint_trace_patterns import (
    BranchesRef,
    DerivedReachabilityLeaf,
    LayerMembershipEndpoint,
    NoneLeaf,
    RegistryEndpoint,
)
from src.domain.viewpoints.viewpoint_validation import validate_viewpoint_definition
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.viewpoint_declarations import load_module_viewpoint_catalog
from tests.domain.test_default_viewpoint_library import _ARCH_PACKAGE_DIR

_REGISTRIES = build_registry_snapshot(build_runtime_catalogs(get_module_registry()), [])


def _definition():
    definition = load_module_viewpoint_catalog(_ARCH_PACKAGE_DIR).get("motivation-coverage")
    assert definition is not None
    return definition


def _patterns():
    query = _definition().query
    assert query is not None
    return query.trace_patterns


class TestShippedDefinition:
    def test_validates_cleanly_at_load(self) -> None:
        issues = validate_viewpoint_definition(
            _definition(),
            mode="load",
            known_entity_types=_REGISTRIES.known_entity_types,
            known_connection_types=_REGISTRIES.known_connection_types,
            known_specialization_slugs=_REGISTRIES.known_specialization_slugs,
            entity_type_infos=_REGISTRIES.entity_type_infos,
        )
        assert [i for i in issues if i.severity == "error"] == []

    def test_is_a_table_over_the_motivation_row_types(self) -> None:
        presentation = _definition().presentation
        assert presentation is not None
        assert presentation.representation == "table"
        assert set(presentation.target_types or ()) == {"goal", "outcome", "requirement"}


class TestShippedPatterns:
    def test_carries_the_five_declared_patterns(self) -> None:
        assert [p.name for p in _patterns().patterns] == [
            "motivation", "overall_realization", "behavior_coverage", "business_coverage", "application_coverage",
        ]

    @pytest.mark.verifies("REQ@1784609467.2I2fS1")
    def test_motivation_is_branch_completeness_only_with_both_shortcut_kinds(self) -> None:
        motivation = _patterns().by_name("motivation")
        assert motivation is not None
        assert isinstance(motivation.leaf, NoneLeaf)
        assert {s.status for s in motivation.shortcuts} == {"shortcut", "ambiguous_link"}

    def test_overall_realization_is_authoritative_over_the_registry_realizer_set(self) -> None:
        overall = _patterns().by_name("overall_realization")
        assert overall is not None
        assert overall.role == "authoritative"
        assert isinstance(overall.leaf, DerivedReachabilityLeaf)
        assert isinstance(overall.leaf.endpoint, RegistryEndpoint)

    def test_layer_patterns_are_diagnostic_never_authoritative(self) -> None:
        for name in ("behavior_coverage", "business_coverage", "application_coverage"):
            pattern = _patterns().by_name(name)
            assert pattern is not None
            assert pattern.role == "diagnostic", f"{name} must never contribute a verdict"
            assert isinstance(pattern.leaf, DerivedReachabilityLeaf)
            assert isinstance(pattern.leaf.endpoint, LayerMembershipEndpoint)

    def test_every_ref_expands_to_the_motivation_branch_edges(self) -> None:
        patterns = _patterns()
        expected = [named.label for named in expand_branch_edges(patterns.by_name("motivation"), patterns)]
        for name in ("overall_realization", "behavior_coverage", "business_coverage", "application_coverage"):
            pattern = patterns.by_name(name)
            assert isinstance(pattern.branches, BranchesRef)
            assert [named.label for named in expand_branch_edges(pattern, patterns)] == expected
