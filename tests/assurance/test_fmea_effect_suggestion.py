"""Effect suggestion: the search is automated, the causal claim is not.

Linking an effect means knowing which hazard this component's failure ends up in — a question about
the architecture that the graph can answer, and a judgement that it cannot. So the ranking, the
paths and the shortlist are computed, and nothing is linked.

The suggestions come only from hazards the analysis has *already* drawn to a control-structure node,
by the two routes the model already contains. Nothing new is inferred: an inferred causal chain
would be the analysis manufacturing its own evidence.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.application.assurance.fmea_effect_suggestion import EffectSuggestion, suggest_effects
from src.domain.assurance.fmea_structural_signals import TypedEdge


def _typed(source: str, target: str, *, strength: int = 4) -> TypedEdge:
    return TypedEdge(
        connection_id=f"{source}-{target}", source_id=source, target_id=target,
        connection_type="archimate-serving", role="dependency", strength=strength,
    )


def _node(node_id: str, node_type: str, name: str = "") -> dict[str, Any]:
    return {"node_id": node_id, "node_type": node_type, "name": name or node_id}


def _edge(source: str, conn_type: str, target: str) -> dict[str, Any]:
    return {"edge_id": f"{source}-{conn_type}-{target}", "source_id": source,
            "conn_type": conn_type, "target_id": target}


def _ref(node_id: str, element_id: str) -> dict[str, Any]:
    return {"assurance_node_id": node_id, "arch_artifact_id": element_id, "ref_type": "binds-to"}


def _uca_world() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """A controller analysed as a control-structure node, with a UCA leading to a hazard."""
    nodes = [
        _node("CSN@1", "control-structure-node"),
        _node("UCA@1", "unsafe-control-action"),
        _node("HAZ@1", "hazard", "Stale data is served"),
    ]
    edges = [_edge("UCA@1", "by-controller", "CSN@1"), _edge("UCA@1", "leads-to", "HAZ@1")]
    return nodes, edges, [_ref("CSN@1", "APP@store")]


class TestSuggestionsComeFromHazardsTheAnalysisAlreadyDrew:
    @pytest.mark.verifies("REQ@1785058330.-LmyST")
    def test_a_hazard_reached_through_an_analysed_neighbour_is_suggested(self) -> None:
        nodes, assurance_edges, refs = _uca_world()

        found = suggest_effects(
            "APP@client", nodes=nodes, arch_refs=refs,
            edges=[_typed("APP@client", "APP@store")], assurance_edges=assurance_edges,
        )

        assert [s.hazard_id for s in found] == ["HAZ@1"]
        assert found[0].via_element_id == "APP@store"

    def test_a_scenario_route_is_found_too(self) -> None:
        """The second route the model already contains: a scenario concerning the node."""
        nodes = [
            _node("CSN@1", "control-structure-node"),
            _node("LSC@1", "loss-scenario"),
            _node("HAZ@1", "hazard", "Stale data is served"),
        ]
        assurance_edges = [_edge("LSC@1", "concerns", "CSN@1"), _edge("LSC@1", "explains", "HAZ@1")]

        found = suggest_effects(
            "APP@client", nodes=nodes, arch_refs=[_ref("CSN@1", "APP@store")],
            edges=[_typed("APP@client", "APP@store")], assurance_edges=assurance_edges,
        )

        assert [s.hazard_id for s in found] == ["HAZ@1"]

    def test_an_element_in_no_analysis_suggests_nothing(self) -> None:
        """Nothing is inferred — an inferred chain would be the analysis inventing its evidence."""
        nodes, assurance_edges, _ = _uca_world()

        found = suggest_effects(
            "APP@client", nodes=nodes, arch_refs=[],
            edges=[_typed("APP@client", "APP@store")], assurance_edges=assurance_edges,
        )

        assert found == ()

    def test_an_unconnected_element_suggests_nothing(self) -> None:
        nodes, assurance_edges, refs = _uca_world()

        found = suggest_effects(
            "APP@island", nodes=nodes, arch_refs=refs, edges=[], assurance_edges=assurance_edges,
        )

        assert found == ()

    def test_a_control_node_with_no_hazard_yields_nothing(self) -> None:
        nodes = [_node("CSN@1", "control-structure-node")]

        found = suggest_effects(
            "APP@client", nodes=nodes, arch_refs=[_ref("CSN@1", "APP@store")],
            edges=[_typed("APP@client", "APP@store")], assurance_edges=[],
        )

        assert found == ()


class TestTheTraversalIsTypedAndBounded:
    def test_an_association_is_not_a_path_to_a_hazard(self) -> None:
        nodes, assurance_edges, refs = _uca_world()
        association = TypedEdge(
            connection_id="a", source_id="APP@client", target_id="APP@store",
            connection_type="archimate-association", role="dependency", strength=1,
        )

        found = suggest_effects(
            "APP@client", nodes=nodes, arch_refs=refs,
            edges=[association], assurance_edges=assurance_edges,
        )

        assert found == ()

    def test_a_neighbour_beyond_the_hop_budget_is_not_offered(self) -> None:
        """Past a few hops the connection stops reading as "this failure ends up there", and the
        shortlist stops being short."""
        nodes, assurance_edges, refs = _uca_world()
        chain = [
            _typed("APP@client", "APP@a"), _typed("APP@a", "APP@b"),
            _typed("APP@b", "APP@c"), _typed("APP@c", "APP@store"),
        ]

        found = suggest_effects(
            "APP@client", nodes=nodes, arch_refs=refs, edges=chain,
            assurance_edges=assurance_edges, max_hops=2,
        )

        assert found == ()

    def test_the_same_hazard_is_offered_once(self) -> None:
        nodes, assurance_edges, _ = _uca_world()
        refs = [_ref("CSN@1", "APP@store"), _ref("CSN@1", "APP@mirror")]

        found = suggest_effects(
            "APP@client", nodes=nodes, arch_refs=refs,
            edges=[_typed("APP@client", "APP@store"), _typed("APP@client", "APP@mirror")],
            assurance_edges=assurance_edges,
        )

        assert len(found) == 1


class TestTheOrderIsStableAndExplained:
    def test_the_stronger_path_is_offered_first(self) -> None:
        nodes = [
            _node("CSN@1", "control-structure-node"), _node("CSN@2", "control-structure-node"),
            _node("UCA@1", "unsafe-control-action"), _node("UCA@2", "unsafe-control-action"),
            _node("HAZ@weak", "hazard"), _node("HAZ@strong", "hazard"),
        ]
        assurance_edges = [
            _edge("UCA@1", "by-controller", "CSN@1"), _edge("UCA@1", "leads-to", "HAZ@weak"),
            _edge("UCA@2", "by-controller", "CSN@2"), _edge("UCA@2", "leads-to", "HAZ@strong"),
        ]
        refs = [_ref("CSN@1", "APP@weak"), _ref("CSN@2", "APP@strong")]
        edges = [
            _typed("APP@client", "APP@weak", strength=2),
            _typed("APP@client", "APP@strong", strength=4),
        ]

        found = suggest_effects(
            "APP@client", nodes=nodes, arch_refs=refs, edges=edges,
            assurance_edges=assurance_edges,
        )

        assert [s.hazard_id for s in found] == ["HAZ@strong", "HAZ@weak"]

    def test_every_suggestion_shows_the_path_that_produced_it(self) -> None:
        """So an analyst can see why it is offered and reject it on sight."""
        nodes, assurance_edges, refs = _uca_world()

        found = suggest_effects(
            "APP@client", nodes=nodes, arch_refs=refs,
            edges=[_typed("APP@client", "APP@store")], assurance_edges=assurance_edges,
        )

        assert "APP@client --archimate-serving(4)--> APP@store" in found[0].witness
        assert any("analysed as CSN@1" in step for step in found[0].witness)


class TestNothingIsLinked:
    def test_the_module_cannot_write_because_it_is_given_nothing_to_write_to(self) -> None:
        """Structural: no parameter anywhere in the module is a store or an archive, so linking is
        not something a future edit could do here by reaching for what is already in scope."""
        import inspect

        from src.application.assurance import fmea_effect_suggestion as module

        parameters = {
            name
            for _, function in inspect.getmembers(module, inspect.isfunction)
            for name in inspect.signature(function).parameters
        }

        assert not {"store", "archive", "writer"} & parameters

    def test_it_calls_no_mutation(self) -> None:
        import inspect

        from src.application.assurance import fmea_effect_suggestion as module

        source = inspect.getsource(module)

        assert "add_edge" not in source
        assert "register_arch_ref" not in source

    def test_a_suggestion_carries_no_decision(self) -> None:
        suggestion = EffectSuggestion(
            hazard_id="HAZ@1", hazard_name="n", via_element_id="APP@1",
            strength=4, hops=1, witness=(),
        )

        assert not {"linked", "accepted", "confidence"} & set(vars(suggestion))
