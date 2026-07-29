"""Ordering a grouping's members along the flow that runs through them.

The regression at the bottom is the view that motivated the shared rule: *Promote Artifacts*, whose
eight functions were chained in id order while twelve triggering connections ran through them, so
every arrow criss-crossed one arbitrary row.
"""

from __future__ import annotations

from src.application.modeling.flow_ordering import flow_depths, order_aliases_along_flow


class TestOrderingFollowsTheFlow:
    def test_a_straight_chain_reads_along_itself(self) -> None:
        ordered = order_aliases_along_flow(
            aliases=["C", "A", "B"],
            flow_edges=[("A", "B"), ("B", "C")],
        )

        assert ordered == ["A", "B", "C"]

    def test_converging_paths_place_the_join_after_the_longer_one(self) -> None:
        """Depth is the longest path, not the first arrival: an element must follow everything
        that leads to it, or the chain pins it in front of one of its own predecessors."""
        ordered = order_aliases_along_flow(
            aliases=["JOIN", "A", "B", "C"],
            flow_edges=[("A", "JOIN"), ("A", "B"), ("B", "C"), ("C", "JOIN")],
        )

        assert ordered == ["A", "B", "C", "JOIN"]

    def test_members_the_flow_does_not_reach_keep_their_order_and_follow(self) -> None:
        """A grouping expressing no flow must come out exactly as it went in."""
        assert order_aliases_along_flow(aliases=["B", "A", "C"], flow_edges=[]) == ["B", "A", "C"]

        mixed = order_aliases_along_flow(
            aliases=["LOOSE_B", "Y", "LOOSE_A", "X"],
            flow_edges=[("X", "Y")],
        )
        assert mixed == ["X", "Y", "LOOSE_B", "LOOSE_A"]

    def test_a_cycle_keeps_every_member(self) -> None:
        """A cycle admits no valid order, so its members trail in arrival order rather than
        vanishing — a slightly worse picture, never a lost element."""
        ordered = order_aliases_along_flow(
            aliases=["A", "B", "C", "START"],
            flow_edges=[("START", "A"), ("A", "B"), ("B", "C"), ("C", "A")],
        )

        assert ordered[0] == "START"
        assert sorted(ordered) == ["A", "B", "C", "START"]

    def test_a_self_loop_orders_nothing(self) -> None:
        assert order_aliases_along_flow(aliases=["B", "A"], flow_edges=[("A", "A")]) == ["B", "A"]

    def test_a_repeated_edge_is_one_ordering_fact(self) -> None:
        ordered = order_aliases_along_flow(
            aliases=["B", "A"],
            flow_edges=[("A", "B"), ("A", "B")],
        )

        assert ordered == ["A", "B"]


class TestDepthSpansTheWholeFlowGraph:
    def test_a_chain_leaving_the_group_and_returning_still_orders_correctly(self) -> None:
        """The distinguishing case, and the reason depth is not computed per group.

        `IN` and `OUT` are members; the flow between them runs through `AWAY`, which is not. An
        order computed from the members' own edges sees no edge at all and reports both as
        beginnings, leaving them in arrival order — here, backwards.
        """
        ordered = order_aliases_along_flow(
            aliases=["OUT", "IN"],
            flow_edges=[("IN", "AWAY"), ("AWAY", "OUT")],
        )

        assert ordered == ["IN", "OUT"]

    def test_depths_are_reported_for_every_alias_the_flow_reaches(self) -> None:
        depths = flow_depths([("A", "B"), ("B", "C")])

        assert depths == {"A": 0, "B": 1, "C": 2}


class TestPromoteArtifactsReadsAlongItsFlow:
    """The original defect, as the view actually states it.

    Eight functions grouped by element type, arriving in id order — Validate, Execute, Resolve,
    Run, Verify, Select, Detect, Replace — with the promotion chain running through them and out
    through two events in another group. The events are why a per-group sort cannot fix this: they
    carry the chain from Detect to Validate and to Resolve.
    """

    _FUNCTIONS_IN_ID_ORDER = [
        "FNC_54UnNB",  # Validate Promotion Selection
        "FNC_6xjXsw",  # Execute Promotion
        "FNC_A0dOFm",  # Resolve Promotion Conflicts
        "FNC_A_wFZl",  # Run Quality Gates
        "FNC_NGjUCa",  # Verify Artifact Integrity & Coherence
        "FNC_Z2rrfP",  # Select Artifacts for Promotion
        "FNC_ndMgDn",  # Detect Promotion Conflicts
        "FNC_wahMSm",  # Replace Promoted Entities with GRFs
    ]

    _TRIGGERING = [
        ("FNC_Z2rrfP", "FNC_ndMgDn"),
        ("FNC_ndMgDn", "EVT_Dm0CyE"),
        ("FNC_ndMgDn", "EVT_fWpwu5"),
        ("EVT_Dm0CyE", "FNC_54UnNB"),
        ("EVT_fWpwu5", "FNC_A0dOFm"),
        ("FNC_A0dOFm", "FNC_54UnNB"),
        ("FNC_54UnNB", "FNC_A_wFZl"),
        ("FNC_A_wFZl", "FNC_6xjXsw"),
        ("FNC_6xjXsw", "FNC_wahMSm"),
        ("FNC_6xjXsw", "EVT_hDF1Qz"),
        ("FNC_wahMSm", "FNC_NGjUCa"),
    ]

    def test_the_functions_read_select_detect_resolve_validate_run_execute_replace_verify(
        self,
    ) -> None:
        ordered = order_aliases_along_flow(
            aliases=list(self._FUNCTIONS_IN_ID_ORDER),
            flow_edges=list(self._TRIGGERING),
        )

        assert ordered == [
            "FNC_Z2rrfP",  # Select
            "FNC_ndMgDn",  # Detect
            "FNC_A0dOFm",  # Resolve
            "FNC_54UnNB",  # Validate
            "FNC_A_wFZl",  # Run Quality Gates
            "FNC_6xjXsw",  # Execute
            "FNC_wahMSm",  # Replace with GRFs
            "FNC_NGjUCa",  # Verify
        ]

    def test_every_triggering_edge_between_functions_now_points_forwards(self) -> None:
        """The property the picture actually depends on: no arrow doubles back along the chain."""
        ordered = order_aliases_along_flow(
            aliases=list(self._FUNCTIONS_IN_ID_ORDER),
            flow_edges=list(self._TRIGGERING),
        )
        position = {alias: index for index, alias in enumerate(ordered)}

        backwards = [
            (source, target)
            for source, target in self._TRIGGERING
            if source in position and target in position and position[source] >= position[target]
        ]
        assert backwards == []

    def test_the_events_read_along_the_flow_too(self) -> None:
        ordered = order_aliases_along_flow(
            aliases=["EVT_Dm0CyE", "EVT_fWpwu5", "EVT_hDF1Qz"],
            flow_edges=list(self._TRIGGERING),
        )

        assert ordered == ["EVT_Dm0CyE", "EVT_fWpwu5", "EVT_hDF1Qz"]
