"""A grouping's hidden spread chain must follow the flow it contains, not the alphabet.

The auto-layout already emits one rank constraint per adjacent pair — `A -[hidden]right- B`
tells Graphviz A precedes B on the spread axis. The constraint was never missing; the
*sequence* it encoded was wrong. Aliases reach this stage in declaration order (by artifact
type, then label), so a pipeline `A → B → C` could be pinned out as `C, A, B`, and its
triggering arrows had to double back across the whole grouping. Diagrams whose whole point
was a flow read as a tangle.

The fix reorders the same aliases and changes nothing else: same number of hidden links, same
direction, no arrow hints, no new constraints. These tests hold that boundary — the ordering
must improve, and everything around it must stay byte-for-byte where it was.
"""

from __future__ import annotations

import re

from src.application.modeling.artifact_write_layout import ensure_puml_layout, rebuild_puml_layout

HIDDEN_RE = re.compile(r"^(\w+) -\[hidden\](\w+)- (\w+)$")


def hidden_chain(puml: str) -> list[tuple[str, str]]:
    """The (source, target) of every hidden spread link, in emission order."""
    return [(m.group(1), m.group(3)) for m in (HIDDEN_RE.match(line.strip()) for line in puml.split("\n")) if m]


def spread_order(puml: str) -> list[str]:
    """The alias sequence the hidden chain pins out."""
    chain = hidden_chain(puml)
    if not chain:
        return []
    return [chain[0][0], *[target for _, target in chain]]


def diagram(members: str, connections: str) -> str:
    return f"""@startuml
top to bottom direction

title Test

rectangle "Steps" <<CommonGrouping>> {{
{members}
}}

{connections}

@enduml"""


PIPELINE_MEMBERS = """  rectangle "Charlie" as C
  rectangle "Alpha" as A
  rectangle "Bravo" as B"""


class TestFlowOrdering:
    def test_a_chain_is_spread_in_flow_order_not_declaration_order(self) -> None:
        puml = ensure_puml_layout(diagram(PIPELINE_MEMBERS, "A --> B\nB --> C"))

        assert spread_order(puml) == ["A", "B", "C"]

    def test_the_macro_form_orders_the_same_way(self) -> None:
        puml = ensure_puml_layout(
            diagram(PIPELINE_MEMBERS, 'Rel_Triggering(A, B, "")\nRel_Triggering(B, C, "")')
        )

        assert spread_order(puml) == ["A", "B", "C"]

    def test_unrelated_members_keep_declaration_order(self) -> None:
        """A grouping that expresses no flow must be emitted exactly as it was before."""
        puml = ensure_puml_layout(diagram(PIPELINE_MEMBERS, ""))

        assert spread_order(puml) == ["C", "A", "B"]

    def test_a_partial_flow_orders_what_it_can_and_leaves_the_rest(self) -> None:
        """An element outside the flow keeps its place; the chain still straightens."""
        puml = ensure_puml_layout(diagram(PIPELINE_MEMBERS, "B --> C"))
        order = spread_order(puml)

        assert order.index("B") < order.index("C")
        assert set(order) == {"A", "B", "C"}

    def test_a_branch_still_puts_every_source_before_its_targets(self) -> None:
        """Not just simple chains: any acyclic flow must come out consistent."""
        puml = ensure_puml_layout(diagram(PIPELINE_MEMBERS, "C --> A\nC --> B"))
        order = spread_order(puml)

        assert order.index("C") < order.index("A")
        assert order.index("C") < order.index("B")

    def test_an_association_does_not_impose_an_order(self) -> None:
        """`A -- B` says the two are related, not that one follows the other."""
        puml = ensure_puml_layout(diagram(PIPELINE_MEMBERS, "A -- B\nB -- C"))

        assert spread_order(puml) == ["C", "A", "B"]


class TestRobustness:
    def test_a_cycle_keeps_every_element(self) -> None:
        """No valid order exists; a worse picture is acceptable, a lost element is not."""
        puml = ensure_puml_layout(diagram(PIPELINE_MEMBERS, "A --> B\nB --> C\nC --> A"))

        assert set(spread_order(puml)) == {"A", "B", "C"}
        assert len(hidden_chain(puml)) == 2

    def test_a_self_edge_is_ignored(self) -> None:
        puml = ensure_puml_layout(diagram(PIPELINE_MEMBERS, "A --> A\nA --> B"))

        order = spread_order(puml)
        assert order.index("A") < order.index("B")
        assert set(order) == {"A", "B", "C"}

    def test_parallel_edges_do_not_strand_a_target(self) -> None:
        """Two relations between the same pair are one ordering fact, not two."""
        puml = ensure_puml_layout(
            diagram(PIPELINE_MEMBERS, 'A --> B\nRel_Triggering(A, B, "")\nB --> C')
        )

        assert spread_order(puml) == ["A", "B", "C"]

    def test_edges_to_elements_outside_the_grouping_are_ignored(self) -> None:
        puml = ensure_puml_layout(diagram(PIPELINE_MEMBERS, "OUTSIDE --> A\nB --> C"))

        assert set(spread_order(puml)) == {"A", "B", "C"}


class TestNothingElseChanges:
    """The whole safety argument: ordering moved, the constraint budget did not."""

    def test_the_number_of_hidden_links_is_unchanged_by_ordering(self) -> None:
        flowing = ensure_puml_layout(diagram(PIPELINE_MEMBERS, "A --> B\nB --> C"))
        inert = ensure_puml_layout(diagram(PIPELINE_MEMBERS, ""))

        assert len(hidden_chain(flowing)) == len(hidden_chain(inert)) == 2

    def test_intra_grouping_arrows_are_left_alone(self) -> None:
        """Hinting these is what would add constraints; ordering deliberately does not."""
        puml = ensure_puml_layout(diagram(PIPELINE_MEMBERS, "A --> B\nB --> C"))

        assert "A --> B" in puml
        assert "B --> C" in puml

    def test_the_spread_direction_is_unchanged(self) -> None:
        puml = ensure_puml_layout(diagram(PIPELINE_MEMBERS, "A --> B\nB --> C"))

        matches = (HIDDEN_RE.match(line.strip()) for line in puml.split("\n"))
        assert all(m.group(2) == "right" for m in matches if m)

    def test_a_body_that_already_has_hidden_links_is_returned_untouched(self) -> None:
        body = diagram(PIPELINE_MEMBERS, "A --> B\nA -[hidden]right- B")

        assert ensure_puml_layout(body) == body

    def test_everything_outside_the_hidden_block_is_byte_identical(self) -> None:
        """The strongest negative: ordering may only ever move hidden links."""
        body = diagram(PIPELINE_MEMBERS, "A --> B\nB --> C")
        optimized = ensure_puml_layout(body)

        without_hidden = [line for line in optimized.split("\n")
                          if "[hidden]" not in line and "Auto-layout" not in line]
        assert [line for line in "\n".join(without_hidden).split("\n") if line.strip()] == \
               [line for line in body.split("\n") if line.strip()]

    def test_optimizing_is_idempotent(self) -> None:
        once = ensure_puml_layout(diagram(PIPELINE_MEMBERS, "A --> B\nB --> C"))

        assert ensure_puml_layout(once) == once

    def test_a_diagram_without_groupings_is_untouched(self) -> None:
        body = '@startuml\nrectangle "Alpha" as A\nrectangle "Bravo" as B\nA --> B\n@enduml'

        assert ensure_puml_layout(body) == body

    def test_a_single_member_grouping_is_untouched(self) -> None:
        body = diagram('  rectangle "Only" as A', "")

        assert ensure_puml_layout(body) == body


class TestOtherDiagramKinds:
    """Auto-layout is for the grouped ArchiMate bodies; other notations must pass through.

    A sequence or activity diagram has its own ordering semantics that this module knows
    nothing about, and reordering their statements would change what they mean rather than
    just how they are ranked.
    """

    def test_a_sequence_diagram_is_untouched(self) -> None:
        body = (
            "@startuml\nparticipant Author\nparticipant Queue\n"
            "Author -> Queue : enqueue\nQueue --> Author : accepted\n@enduml"
        )

        assert ensure_puml_layout(body) == body

    def test_an_activity_diagram_is_untouched(self) -> None:
        body = "@startuml\nstart\n:Verify;\n:Commit;\nstop\n@enduml"

        assert ensure_puml_layout(body) == body

    def test_a_c4_style_body_without_groupings_is_untouched(self) -> None:
        body = (
            "@startuml\n!include <C4/C4_Container>\n"
            'Container(api, "API", "Python")\nContainer(db, "Store", "SQLite")\n'
            "Rel(api, db, \"reads\")\n@enduml"
        )

        assert ensure_puml_layout(body) == body


class TestManualLayoutSurvives:
    """A hand-tuned diagram stays hand-tuned until the author asks otherwise.

    Layout optimization runs on writes that have nothing to do with layout — a rename, a
    binding change, a status edit. If it re-ranked the body every time, anyone who arranged a
    diagram by hand would find it rearranged by an unrelated edit, with no action of theirs
    that could be pointed at. So the recompute is opt-in, and belongs only to actions whose
    stated purpose is to rebuild the picture.
    """

    GENERATED = ensure_puml_layout(diagram(PIPELINE_MEMBERS, "A --> B\nB --> C"))

    def test_by_default_a_generated_block_is_left_alone(self) -> None:
        """Even when the flow now implies a different order than the block records."""
        stale = self.GENERATED.replace("A -[hidden]right- B\nB -[hidden]right- C",
                                       "C -[hidden]right- B\nB -[hidden]right- A")

        assert ensure_puml_layout(stale) == stale

    def test_a_relayout_recomputes_it(self) -> None:
        stale = self.GENERATED.replace("A -[hidden]right- B\nB -[hidden]right- C",
                                       "C -[hidden]right- B\nB -[hidden]right- A")

        assert spread_order(rebuild_puml_layout(stale)) == ["A", "B", "C"]

    def test_hand_placed_links_survive_even_a_rebuild(self) -> None:
        """The block is this module's to replace; anything else is the author's to keep."""
        body = diagram(PIPELINE_MEMBERS, "A --> B\nB --> C\nC -[hidden]right- A")

        assert rebuild_puml_layout(body) == body

    def test_a_rebuild_of_an_untouched_body_matches_a_first_pass(self) -> None:
        assert rebuild_puml_layout(self.GENERATED) == self.GENERATED
