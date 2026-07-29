"""Structural signals: typed only, absent rather than zero, and backed by a witness.

Each test here corresponds to a way of getting a graph metric wrong that still produces a number.
Counting associations inflates every element that happens to be cross-referenced. Reporting zero for
an unmodelled element says "nothing depends on this" when the truth is "nobody drew what does".
Reporting a count with no path behind it gives a reader nothing to check.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.domain.assurance.fmea_structural_signals import (
    EXCLUDED_CONNECTION_TYPE,
    TypedEdge,
    common_cause_exposure,
    countable,
    interchangeable_pairs,
    reliance_on,
    sole_providers,
    typed_edges,
)


@dataclass(frozen=True)
class _TypeInfo:
    derivation_role: str | None
    derivation_strength: int | None


_CATALOG: dict[str, Any] = {
    "archimate-composition": _TypeInfo("structural", 4),
    "archimate-realization": _TypeInfo("structural", 1),
    "archimate-serving": _TypeInfo("dependency", 4),
    "archimate-access": _TypeInfo("dependency", 3),
    EXCLUDED_CONNECTION_TYPE: _TypeInfo("dependency", 1),
    "archimate-flow": _TypeInfo("dynamic", None),
    "archimate-specialization": _TypeInfo("specialization", None),
}


def _edge(source: str, connection_type: str, target: str) -> TypedEdge:
    info = _CATALOG[connection_type]
    return TypedEdge(
        connection_id=f"{source}-{connection_type}-{target}",
        source_id=source,
        target_id=target,
        connection_type=connection_type,
        role=info.derivation_role,
        strength=info.derivation_strength,
    )


class TestOnlyTypedRelianceCounts:
    def test_a_serving_relationship_counts(self) -> None:
        assert countable(_edge("APP@1", "archimate-serving", "APP@2"))

    def test_an_association_never_counts(self) -> None:
        """The weakest dependency, and it asserts no direction of reliance."""
        assert not countable(_edge("APP@1", EXCLUDED_CONNECTION_TYPE, "APP@2"))

    def test_a_flow_never_counts(self) -> None:
        """A flow says what moves, not what depends."""
        assert not countable(_edge("APP@1", "archimate-flow", "APP@2"))

    def test_a_specialization_never_counts(self) -> None:
        """Specialization says what something *is*, not what it leans on."""
        assert not countable(_edge("APP@1", "archimate-specialization", "APP@2"))

    def test_roles_and_strengths_come_from_the_catalog(self) -> None:
        built = typed_edges(
            [{
                "artifact_id": "CON@1", "source": "APP@1", "target": "APP@2",
                "connection_type": "archimate-composition",
            }],
            _CATALOG,
        )

        assert (built[0].role, built[0].strength) == ("structural", 4)


class TestRelianceIsAbsentRatherThanZero:
    def test_an_unmodelled_element_yields_absence(self) -> None:
        """Zero would say "nothing depends on this"; the truth is that nobody drew what does."""
        assert reliance_on("APP@lonely", []) is None

    def test_an_element_with_only_associations_reports_zero_dependents_not_absence(self) -> None:
        """Its neighbourhood IS modelled — the relationships there simply do not assert reliance,
        which is a different and reportable fact."""
        edges = [_edge("APP@2", EXCLUDED_CONNECTION_TYPE, "APP@1")]

        reliance = reliance_on("APP@1", edges)

        assert reliance is not None
        assert reliance.dependent_count == 0

    def test_dependents_are_the_sources_that_lean_on_it(self) -> None:
        edges = [
            _edge("APP@2", "archimate-serving", "APP@1"),
            _edge("APP@3", "archimate-access", "APP@1"),
        ]

        reliance = reliance_on("APP@1", edges)

        assert reliance is not None
        assert reliance.dependent_ids == ("APP@2", "APP@3")

    def test_the_direction_is_not_reversed(self) -> None:
        """What this element serves is not what depends on it."""
        edges = [_edge("APP@1", "archimate-serving", "APP@2")]

        reliance = reliance_on("APP@1", edges)

        assert reliance is not None
        assert reliance.dependent_count == 0

    def test_weight_sums_the_declared_strengths(self) -> None:
        edges = [
            _edge("APP@2", "archimate-serving", "APP@1"),
            _edge("APP@3", "archimate-realization", "APP@1"),
        ]

        reliance = reliance_on("APP@1", edges)

        assert reliance is not None
        assert reliance.weight == 5

    def test_twenty_associations_never_outweigh_one_composition(self) -> None:
        """The comparison untyped degree gets backwards."""
        associated = [_edge(f"APP@{i}", EXCLUDED_CONNECTION_TYPE, "APP@a") for i in range(20)]
        composed = [_edge("APP@x", "archimate-composition", "APP@b")]

        weak = reliance_on("APP@a", associated)
        strong = reliance_on("APP@b", composed)

        assert weak is not None and strong is not None
        assert weak.weight == 0
        assert strong.weight > weak.weight

    def test_a_thin_neighbourhood_is_marked_provisional(self) -> None:
        edges = [_edge("APP@2", "archimate-serving", "APP@1")]

        reliance = reliance_on("APP@1", edges)

        assert reliance is not None
        assert reliance.provisional, "one relationship is arithmetically correct and rests on little"

    def test_a_well_modelled_neighbourhood_is_not_provisional(self) -> None:
        edges = [_edge(f"APP@{i}", "archimate-serving", "APP@1") for i in range(2, 8)]

        reliance = reliance_on("APP@1", edges)

        assert reliance is not None
        assert not reliance.provisional

    def test_every_counted_relationship_appears_in_the_witness(self) -> None:
        edges = [_edge("APP@2", "archimate-serving", "APP@1")]

        reliance = reliance_on("APP@1", edges)

        assert reliance is not None
        assert reliance.witness == ("APP@2 --archimate-serving(4)--> APP@1",)


class TestSoleProviders:
    def test_an_element_nothing_can_stand_in_for_is_found(self) -> None:
        edges = [_edge("APP@client", "archimate-serving", "APP@store")]

        assert sole_providers(edges) == {"APP@store": ("APP@client",)}

    def test_an_element_with_an_alternative_is_not_a_sole_provider(self) -> None:
        """The dependent's own reliance set decides it, which is what makes this exact rather than
        remembered."""
        edges = [
            _edge("APP@client", "archimate-serving", "APP@primary"),
            _edge("APP@client", "archimate-serving", "APP@standby"),
        ]

        assert sole_providers(edges) == {}

    def test_associations_do_not_create_a_false_alternative(self) -> None:
        """An association to a second element must not make a real sole provider look replaceable."""
        edges = [
            _edge("APP@client", "archimate-serving", "APP@store"),
            _edge("APP@client", EXCLUDED_CONNECTION_TYPE, "APP@wiki"),
        ]

        assert sole_providers(edges) == {"APP@store": ("APP@client",)}


class TestCommonCauseExposure:
    def test_a_redundant_pair_sharing_a_dependency_is_reported(self) -> None:
        """Redundant on paper, not redundant at all: the same store sits under both."""
        edges = [
            _edge("APP@client", "archimate-serving", "APP@primary"),
            _edge("APP@client", "archimate-serving", "APP@standby"),
            _edge("APP@primary", "archimate-access", "APP@store"),
            _edge("APP@standby", "archimate-access", "APP@store"),
        ]

        found = common_cause_exposure([("APP@primary", "APP@standby")], edges)

        assert [c.shared_ancestor_id for c in found] == ["APP@store"]

    def test_the_report_names_the_shared_ancestor_and_both_paths(self) -> None:
        edges = [
            _edge("APP@primary", "archimate-access", "APP@store"),
            _edge("APP@standby", "archimate-access", "APP@store"),
        ]

        found = common_cause_exposure([("APP@primary", "APP@standby")], edges)

        assert found[0].left_witness and found[0].right_witness
        assert "APP@store" in found[0].left_witness[0]

    def test_a_genuinely_independent_pair_reports_nothing(self) -> None:
        edges = [
            _edge("APP@primary", "archimate-access", "APP@store-a"),
            _edge("APP@standby", "archimate-access", "APP@store-b"),
        ]

        assert common_cause_exposure([("APP@primary", "APP@standby")], edges) == ()

    def test_sharing_is_found_transitively(self) -> None:
        """The interesting case: neither names the shared thing directly."""
        edges = [
            _edge("APP@primary", "archimate-access", "APP@cache"),
            _edge("APP@standby", "archimate-access", "APP@queue"),
            _edge("APP@cache", "archimate-serving", "NOD@host"),
            _edge("APP@queue", "archimate-serving", "NOD@host"),
        ]

        found = common_cause_exposure([("APP@primary", "APP@standby")], edges)

        assert "NOD@host" in [c.shared_ancestor_id for c in found]

    def test_sharing_only_through_an_association_is_not_sharing(self) -> None:
        edges = [
            _edge("APP@primary", EXCLUDED_CONNECTION_TYPE, "APP@store"),
            _edge("APP@standby", EXCLUDED_CONNECTION_TYPE, "APP@store"),
        ]

        assert common_cause_exposure([("APP@primary", "APP@standby")], edges) == ()

    def test_candidate_pairs_are_discovered_from_the_graph(self) -> None:
        """Never declared: a declaration reading `active-active` while the model shows one provider
        would be a second source of truth, and the graph is the one that knows."""
        edges = [
            _edge("APP@client", "archimate-serving", "APP@primary"),
            _edge("APP@client", "archimate-serving", "APP@standby"),
        ]

        assert interchangeable_pairs(edges) == (("APP@primary", "APP@standby"),)

    def test_elements_serving_different_dependents_are_not_candidates(self) -> None:
        edges = [
            _edge("APP@a", "archimate-serving", "APP@one"),
            _edge("APP@b", "archimate-serving", "APP@two"),
        ]

        assert interchangeable_pairs(edges) == ()


class TestTheReliaceWalkIsBounded:
    """The walk runs over the same graph as the derivation engine, so it is bounded the same way.

    Absence of a finding must never be the silent result of a budget: a shared dependency the walk
    did not reach is exactly what this exists to surface, so "stopped looking" is reported and never
    allowed to read as "looked and found nothing".
    """

    def _chain(self, length: int) -> list[TypedEdge]:
        return [_edge(f"APP@{i}", "archimate-serving", f"APP@{i + 1}") for i in range(length)]

    def test_the_default_budget_is_the_derivation_engine_s(self) -> None:
        from src.domain.assurance.fmea_structural_signals import DEFAULT_BOUNDS

        assert (DEFAULT_BOUNDS.max_hops, DEFAULT_BOUNDS.time_budget_seconds) == (4, 2.0)
        assert DEFAULT_BOUNDS.max_relationships == 20000

    def test_a_hop_budget_stops_the_walk_and_says_so(self) -> None:
        from src.domain.assurance.fmea_structural_signals import DerivationBounds, common_cause_report

        # Both anchors reach APP@6, but only past the hop budget.
        edges = self._chain(6) + [_edge("APP@alt", "archimate-serving", "APP@1")]
        bounds = DerivationBounds(max_hops=1, max_relationships=20000, time_budget_seconds=2.0)

        report = common_cause_report([("APP@0", "APP@alt")], edges, bounds=bounds)

        assert report.truncated
        assert report.exposures == () or all(e.provisional for e in report.exposures)

    def test_a_generous_budget_finds_the_shared_ancestor(self) -> None:
        from src.domain.assurance.fmea_structural_signals import DerivationBounds, common_cause_report

        edges = self._chain(3) + [_edge("APP@alt", "archimate-serving", "APP@1")]
        bounds = DerivationBounds(max_hops=4, max_relationships=20000, time_budget_seconds=2.0)

        report = common_cause_report([("APP@0", "APP@alt")], edges, bounds=bounds)

        assert not report.truncated
        assert "APP@1" in [e.shared_ancestor_id for e in report.exposures]
        assert all(not e.provisional for e in report.exposures)

    def test_a_relationship_ceiling_stops_the_walk(self) -> None:
        from src.domain.assurance.fmea_structural_signals import DerivationBounds, common_cause_report

        edges = self._chain(10) + [_edge("APP@alt", "archimate-serving", "APP@1")]
        bounds = DerivationBounds(max_hops=10, max_relationships=2, time_budget_seconds=2.0)

        report = common_cause_report([("APP@0", "APP@alt")], edges, bounds=bounds)

        assert report.truncated

    def test_an_exhausted_time_budget_stops_the_walk(self) -> None:
        from src.domain.assurance.fmea_structural_signals import DerivationBounds, common_cause_report

        edges = self._chain(6) + [_edge("APP@alt", "archimate-serving", "APP@1")]
        expired = DerivationBounds(max_hops=10, max_relationships=20000, time_budget_seconds=-1.0)

        report = common_cause_report([("APP@0", "APP@alt")], edges, bounds=expired)

        assert report.truncated

    def test_the_convenience_wrapper_still_returns_exposures(self) -> None:
        edges = [
            _edge("APP@primary", "archimate-access", "APP@store"),
            _edge("APP@standby", "archimate-access", "APP@store"),
        ]

        assert [c.shared_ancestor_id for c in common_cause_exposure([("APP@primary", "APP@standby")], edges)] == [
            "APP@store"
        ]
