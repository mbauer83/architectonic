"""Structural assertions for the trace-pattern grammar shapes (the discriminated unions
the loader, authoring DTOs, validator, and upgrade detector all build on)."""

from __future__ import annotations

import dataclasses

import pytest

from src.domain.viewpoints.viewpoint_trace_patterns import (
    MAX_LEAF_HOPS,
    BranchesRef,
    DerivedReachabilityLeaf,
    DiagnosticEdge,
    InlineBranches,
    LayerMembershipEndpoint,
    NamedBranchEdge,
    NoneLeaf,
    RegistryEndpoint,
    StoredEdge,
    TracePattern,
    TracePatternSet,
)


def _motivation() -> TracePattern:
    return TracePattern(
        name="motivation",
        applies_to=("goal", "outcome"),
        branches=InlineBranches(
            edges=(
                NamedBranchEdge("goal_to_outcome", StoredEdge("archimate-realization", "incoming", "outcome")),
                NamedBranchEdge(
                    "outcome_to_requirement", StoredEdge("archimate-realization", "incoming", "requirement")
                ),
            )
        ),
        shortcuts=(
            DiagnosticEdge("archimate-influence", "incoming", "requirement", "shortcut"),
            DiagnosticEdge("archimate-association", "incoming", "requirement", "ambiguous_link"),
        ),
        leaf=NoneLeaf(),
    )


class TestVariantTags:
    def test_edge_and_leaf_variants_carry_stable_kind_discriminators(self) -> None:
        assert StoredEdge("c", "incoming", "outcome").kind == "stored-edge"
        assert DiagnosticEdge("c", "incoming", "requirement", "shortcut").kind == "diagnostic-edge"
        assert NoneLeaf().kind == "none"
        assert RegistryEndpoint("permitted-realizers-of-requirement").kind == "registry"
        assert LayerMembershipEndpoint("business").kind == "layer"
        assert InlineBranches(()).kind == "inline"
        assert BranchesRef("motivation").kind == "ref"

    def test_derived_leaf_defaults_to_the_hop_cap_and_direct_and_derived(self) -> None:
        leaf = DerivedReachabilityLeaf("archimate-realization", RegistryEndpoint("permitted-realizers-of-requirement"))
        assert leaf.max_hops == MAX_LEAF_HOPS
        assert leaf.traversal == "direct_and_derived"
        assert leaf.kind == "derived-reachability"


class TestPatternRole:
    def test_default_pattern_is_authoritative(self) -> None:
        assert _motivation().role == "authoritative"

    def test_diagnostic_flag_makes_the_pattern_diagnostic(self) -> None:
        diag = dataclasses.replace(_motivation(), name="business_coverage", diagnostic=True)
        assert diag.role == "diagnostic"


class TestImmutabilityAndLookup:
    def test_shapes_are_frozen(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            _motivation().name = "changed"  # type: ignore[misc]

    def test_set_lookup_by_name(self) -> None:
        overall = dataclasses.replace(_motivation(), name="overall_realization", branches=BranchesRef("motivation"))
        s = TracePatternSet((_motivation(), overall))
        assert s.by_name("overall_realization") is overall
        assert s.by_name("nonexistent") is None
