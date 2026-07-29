"""The bowtie renderer — one implementation for both content sources.

Regression behind these tests: there were two renderers, and the one serving the **live** view
derived a node's role from its `node_type` and knew only four roles — so `barrier_right` could not be
drawn at all, in a diagram whose entire point is barriers on both sides of the top event. It also
dropped nodes whose role it did not recognise, where the other kept them.
"""

from __future__ import annotations

from pathlib import Path

from src.diagram_types._assurance_puml_alias import safe_alias
from src.diagram_types.bowtie import module as bowtie_module
from src.diagram_types.bowtie.notation import (
    BARRIER_LEFT,
    BARRIER_RIGHT,
    CONSEQUENCE,
    MITIGATES,
    ROLE_ORDER,
    THREAT,
    TOP_EVENT,
    project_store_graph,
    render,
    role_of,
)


def _node(node_id: str, name: str, **extra: object) -> dict[str, object]:
    return {"node_id": node_id, "name": name, **extra}


def _edge(source: str, target: str, **extra: object) -> dict[str, object]:
    return {"source_id": source, "target_id": target, **extra}


class TestRoleDerivation:
    def test_an_authored_role_wins_over_the_node_type(self) -> None:
        """A persisted diagram can place a node the store's type vocabulary cannot."""
        node = _node("N", "Recovery valve", node_type="assurance-constraint", role=BARRIER_RIGHT)
        assert role_of(node) == BARRIER_RIGHT

    def test_a_role_is_derived_from_the_store_node_type_when_absent(self) -> None:
        assert role_of(_node("H", "Hazard", node_type="hazard")) == TOP_EVENT
        assert role_of(_node("L", "Loss", node_type="loss")) == CONSEQUENCE
        assert role_of(_node("U", "UCA", node_type="unsafe-control-action")) == THREAT
        assert role_of(_node("S", "Scenario", node_type="loss-scenario")) == THREAT
        assert role_of(_node("C", "Constraint", node_type="assurance-constraint")) == BARRIER_LEFT

    def test_a_node_belonging_to_neither_vocabulary_has_no_role(self) -> None:
        assert role_of(_node("X", "Evidence", node_type="evidence")) == ""


class TestWhichSideABarrierTakes:
    """A constraint is preventive unless it `mitigates` a loss — the only signal the node lacks.

    Before this, every live-projected constraint landed left, so a detective or recovery control was
    drawn as if it stopped the top event from happening.
    """

    CONSTRAINT = _node("C", "Tamper-evident archive", node_type="assurance-constraint")
    LOSS = _node("L", "Disclosure", node_type="loss")

    def test_a_constraint_that_mitigates_a_loss_stands_right_of_the_top_event(self) -> None:
        mitigates = [_edge("C", "L", conn_type=MITIGATES)]
        nodes, _edges = project_store_graph([self.CONSTRAINT, self.LOSS], mitigates)

        assert {n["node_id"]: n["role"] for n in nodes} == {"C": BARRIER_RIGHT, "L": CONSEQUENCE}

    def test_a_constraint_with_no_mitigates_edge_stays_preventive(self) -> None:
        """The threat side needs no relation of its own: `derives` provenance already says it.

        The hazard is in the node list because the barrier has to be on a drawn pathway to appear at
        all — see `project_store_graph`. Which side it takes is what this test is about.
        """
        hazard = _node("H", "Top event", node_type="hazard")
        nodes, _edges = project_store_graph(
            [self.CONSTRAINT, self.LOSS, hazard], [_edge("H", "C", conn_type="derives")],
        )

        assert [n["role"] for n in nodes if n["node_id"] == "C"] == [BARRIER_LEFT]

    def test_render_places_the_barrier_from_the_edges_alone(self) -> None:
        """The persisted path renders frontmatter directly, without going through the projection."""
        puml = render(
            [self.CONSTRAINT, self.LOSS, _node("H", "Top", node_type="hazard")],
            [_edge("C", "L", conn_type=MITIGATES)],
        )
        order = [line.split(" as ")[1].split(" ")[0] for line in puml.splitlines() if " as " in line]

        assert order == [safe_alias("H"), safe_alias("C"), safe_alias("L")]

    def test_only_the_mitigating_end_of_the_edge_moves(self) -> None:
        """A loss is a consequence whether or not something mitigates it — the source moves, not the target."""
        assert role_of(self.LOSS, mitigating_ids={"C", "L"}) == CONSEQUENCE

    def test_an_authored_role_still_wins_over_the_edges(self) -> None:
        authored = _node("C", "Barrier", node_type="assurance-constraint", role=BARRIER_LEFT)
        assert role_of(authored, mitigating_ids={"C"}) == BARRIER_LEFT

    def test_a_projected_side_survives_being_projected_again(self) -> None:
        """The projection stamps `role`, so re-projecting a snapshot cannot silently re-place a barrier."""
        mitigates = [_edge("C", "L", conn_type=MITIGATES)]
        once, _edges = project_store_graph([self.CONSTRAINT, self.LOSS], mitigates)
        # Re-projected with the same edges: the pathway is what keeps both nodes in, and the point
        # here is that the stamped `role` is not recomputed into something else.
        twice, _edges = project_store_graph(once, mitigates)

        assert [n["role"] for n in twice if n["node_id"] == "C"] == [BARRIER_RIGHT]


class TestBarriersOnBothSides:
    """The defect this unification fixes: the live view could not draw a right-hand barrier."""

    NODES = [
        _node("U1", "Threat", node_type="unsafe-control-action"),
        _node("C1", "Preventive barrier", node_type="assurance-constraint"),
        _node("H1", "Top event", node_type="hazard"),
        _node("C2", "Mitigative barrier", node_type="assurance-constraint", role=BARRIER_RIGHT),
        _node("L1", "Consequence", node_type="loss"),
    ]

    def test_a_right_hand_barrier_is_drawn(self) -> None:
        puml = render(self.NODES, [])

        assert f'card "Mitigative barrier" <<barrier>> as {safe_alias("C2")}' in puml
        assert f'card "Preventive barrier" <<barrier>> as {safe_alias("C1")}' in puml

    def test_nodes_read_left_to_right_through_the_top_event(self) -> None:
        puml = render(self.NODES, [])
        order = [line.split(" as ")[1].split(" ")[0] for line in puml.splitlines() if " as " in line]

        assert order == [safe_alias("U1"), safe_alias("C1"), safe_alias("H1"), safe_alias("C2"), safe_alias("L1")]

    def test_the_role_order_is_the_bowtie_shape(self) -> None:
        assert ROLE_ORDER == (THREAT, BARRIER_LEFT, TOP_EVENT, BARRIER_RIGHT, CONSEQUENCE)


class TestUnplacedNodes:
    def test_a_node_with_no_role_is_drawn_last_rather_than_dropped(self) -> None:
        """A node in a bowtie projection with no role is a modelling gap; omitting it hides it."""
        puml = render(
            [_node("H1", "Top event", node_type="hazard"), _node("X", "Unplaceable", role="invented")],
            [],
        )

        assert "Unplaceable" in puml
        order = [line.split(" as ")[1].split(" ")[0] for line in puml.splitlines() if " as " in line]
        assert order == [safe_alias("H1"), safe_alias("X")]

    def test_an_empty_projection_says_so(self) -> None:
        assert "No bowtie assurance nodes found." in render([], [])


class TestProjection:
    NODES = [
        _node("H1", "Top event", node_type="hazard"),
        _node("L1", "Consequence", node_type="loss"),
        _node("EV", "Evidence", node_type="evidence"),
    ]
    LEADS_TO = [_edge("H1", "L1", conn_type="leads-to")]

    def test_only_nodes_with_a_bowtie_role_take_part(self) -> None:
        nodes, _edges = project_store_graph(self.NODES, self.LEADS_TO)
        assert [n["node_id"] for n in nodes] == ["H1", "L1"]

    def test_an_edge_is_admitted_only_when_both_ends_are_drawn(self) -> None:
        _nodes, edges = project_store_graph(
            self.NODES,
            [*self.LEADS_TO, _edge("H1", "EV", conn_type="evidenced-by")],
        )
        assert [(e["source_id"], e["target_id"]) for e in edges] == [("H1", "L1")]

    def test_a_projection_never_widens_what_it_was_given(self) -> None:
        nodes, edges = project_store_graph(self.NODES, self.LEADS_TO)
        assert len(nodes) <= len(self.NODES)
        assert len(edges) <= 1

    def test_a_node_on_no_drawn_pathway_is_not_part_of_the_bowtie(self) -> None:
        """It rendered as a box with nothing touching it, which reads as a broken diagram.

        The live store had two of them: constraints whose only relations run to a failure mode that
        derives them, an obligation they comply with, and the evidence that exercises them — none of
        which a bowtie draws. Whether that is a coverage gap is the verifier's question to answer,
        where it can name the missing link.
        """
        barrier = _node("ACN1", "Records every operation", node_type="assurance-constraint")

        nodes, _edges = project_store_graph(
            [*self.NODES, barrier],
            [*self.LEADS_TO, _edge("ACN1", "EV", conn_type="evidenced-by")],
        )

        assert [n["node_id"] for n in nodes] == ["H1", "L1"]

    def test_a_barrier_on_a_pathway_is_kept(self) -> None:
        barrier = _node("ACN1", "Stops the hazard", node_type="assurance-constraint")

        nodes, _edges = project_store_graph(
            [*self.NODES, barrier],
            [*self.LEADS_TO, _edge("ACN1", "H1", conn_type="derives")],
        )

        assert set(n["node_id"] for n in nodes) == {"H1", "L1", "ACN1"}

    def test_a_projection_with_no_edges_draws_nothing(self) -> None:
        """Not an error: a bowtie is a picture of pathways, and there are none to draw."""
        nodes, edges = project_store_graph(self.NODES, [])

        assert nodes == []
        assert edges == []


class TestOneImplementation:
    def test_the_persisted_path_and_a_direct_render_agree(self) -> None:
        """The diagram-type renderer is a thin adapter: it normalises a payload and delegates."""
        nodes = [
            _node("U1", "Threat", node_type="unsafe-control-action"),
            _node("H1", "Top event", node_type="hazard"),
        ]
        edges = [_edge("U1", "H1", conn_type="leads-to")]

        from_payload = bowtie_module.renderer.render_body(
            "", [], [], "bowtie", Path("/"), diagram_entities={"nodes": nodes, "edges": edges},
        )
        assert from_payload == render(nodes, edges)

    def test_a_json_string_payload_is_accepted(self) -> None:
        """Frontmatter may carry either list as a JSON string."""
        import json

        body = bowtie_module.renderer.render_body(
            "", [], [], "bowtie", Path("/"),
            diagram_entities={"nodes": json.dumps([_node("H1", "Top", node_type="hazard")]), "edges": "[]"},
        )
        assert f'component "Top" <<top-event>> as {safe_alias("H1")}' in body

    def test_an_edge_label_is_quoted_so_specials_survive(self) -> None:
        puml = render(
            [_node("A", "A", role=THREAT), _node("B", "B", role=CONSEQUENCE)],
            [_edge("A", "B", label="leads to: eventually")],
        )
        assert f'{safe_alias("A")} --> {safe_alias("B")} : "leads to: eventually"' in puml
