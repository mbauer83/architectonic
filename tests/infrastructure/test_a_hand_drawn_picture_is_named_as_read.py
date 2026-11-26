"""What only a hand-drawn picture has is named as a reader sees the picture, never in the body's own spelling.

The edit-mode notice and the refusal of a canvas save listed raw PlantUML — `'ACT_Nn7Oo7__2 --> BOB_so7gfN__2'`,
`'ROL_udXPfB__2 -down- BOB_so7gfN__2'` — which tells a reader nothing. Boxes are named by their labels,
elements by the names they are drawn with, relations as `Name → Name (type)` with the type the diagram's own
connections give the pair.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.application.modeling.hand_drawn_constructs import hand_drawn
from src.infrastructure.diagram_body_ownership import (
    UNNAMED,
    BodyWrittenByHand,
    HandWrittenBody,
    NamedRelation,
    named_hand_drawn,
)

#: A PlantUML alias as the renderer spells one, a further drawing's included: `ACT_Nn7Oo7__2`.
RAW_ALIAS = re.compile(r"[A-Z]{2,4}_\w+__\d")

ARCHITECT = "ACT@1712870400.Nn7Oo7.architect"
REPOSITORY = "BOB@1712870400.so7gfN.engagement-repository"
AGENT = "ROL@1776633082.udXPfB.ai-agent"

FRONTMATTER: dict[str, object] = {
    "entity-ids-used": [ARCHITECT, REPOSITORY, AGENT],
    "connection-ids-used": [
        "ACT@1712870400.Nn7Oo7---BOB@1712870400.so7gfN@@archimate-assignment",
        "ROL@1776633082.udXPfB---BOB@1712870400.so7gfN@@archimate-association",
    ],
    "diagram-entities": {"occurrence": [
        {"id": "occ-repository-b", "backing_entity_id": REPOSITORY},
        {"id": "occ-architect-b", "backing_entity_id": ARCHITECT},
        {"id": "occ-agent-b", "backing_entity_id": AGENT},
    ]},
}

GENERATED = """@startuml
top to bottom direction
rectangle "Business" <<BusinessGrouping>> {
  rectangle "<$archimate_business_object{scale=1.2}> Engagement Repository" <<business_object>> as BOB_so7gfN
  rectangle "<$archimate_business_actor{scale=1.2}> Architect" <<business_actor>> as ACT_Nn7Oo7
  rectangle "<$archimate_role{scale=1.2}> AI Agent" <<role>> as ROL_udXPfB
  rectangle "<$archimate_business_object{scale=1.2}> Engagement Repository" <<business_object>> as BOB_so7gfN__2
  rectangle "<$archimate_business_actor{scale=1.2}> Architect" <<business_actor>> as ACT_Nn7Oo7__2
  rectangle "<$archimate_role{scale=1.2}> AI Agent" <<role>> as ROL_udXPfB__2
}
ACT_Nn7Oo7 --> BOB_so7gfN
ROL_udXPfB -- BOB_so7gfN
@enduml
"""

HAND_DRAWN = """@startuml
left to right direction
rectangle "Team / Project A" <<BusinessGrouping>> {
  rectangle "<$archimate_business_object{scale=1.2}> Engagement Repository" <<business_object>> as BOB_so7gfN
  rectangle "<$archimate_business_actor{scale=1.2}> Architect" <<business_actor>> as ACT_Nn7Oo7
  rectangle "<$archimate_role{scale=1.2}> AI Agent" <<role>> as ROL_udXPfB
}
rectangle "Team / Project B" <<BusinessGrouping>> {
  rectangle "<$archimate_business_object{scale=1.2}> Engagement Repository" <<business_object>> as BOB_so7gfN__2
  rectangle "<$archimate_business_actor{scale=1.2}> Architect" <<business_actor>> as ACT_Nn7Oo7__2
  rectangle "" <<role>> as ROL_udXPfB__2
  rectangle "" as ROL_udXPfB__3
}
ACT_Nn7Oo7 --> BOB_so7gfN
ROL_udXPfB -- BOB_so7gfN
ACT_Nn7Oo7__2 --> BOB_so7gfN__2
ROL_udXPfB__2 -down- BOB_so7gfN__2
ROL_udXPfB__3 -- BOB_so7gfN__2
@enduml
"""


@dataclass(frozen=True)
class _Entity:
    name: str


class _Repo:
    """Answers the model's names; only an element a declaration does not label is asked for."""

    def get_entity(self, artifact_id: str) -> _Entity | None:
        return {"ROL@1776633082.udXPfB": _Entity("AI Agent")}.get(artifact_id)


def _named() -> HandWrittenBody:
    drawn = hand_drawn(HAND_DRAWN, GENERATED)
    return named_hand_drawn(drawn, body=HAND_DRAWN, frontmatter=FRONTMATTER, repo=_Repo())


def test_boxes_elements_relations_and_direction_are_named_as_read() -> None:
    named = _named()

    assert named.boxes == ("Team / Project A", "Team / Project B")
    assert named.elements == (UNNAMED,)
    assert named.relations == (
        NamedRelation("Architect", "Engagement Repository", "assignment"),
        NamedRelation("AI Agent", "Engagement Repository", "association"),
        NamedRelation(UNNAMED, "Engagement Repository"),
    )
    assert named.directions == ("left to right",)


def test_a_relation_reads_name_arrow_name_and_its_type() -> None:
    assert str(NamedRelation("Architect", "Engagement Repository", "assignment")) == (
        "Architect → Engagement Repository (assignment)"
    )
    assert str(NamedRelation("Architect", "Engagement Repository")) == "Architect → Engagement Repository"


def test_the_reason_names_no_alias_and_no_arrow() -> None:
    reason = _named().reason()

    assert reason.startswith('it draws what a generated picture would not: boxes "Team / Project A", ')
    assert "relations Architect → Engagement Repository (assignment)" in reason
    assert not RAW_ALIAS.search(reason)
    assert "-->" not in reason and "-down-" not in reason


def test_the_refusal_says_the_picture_is_drawn_by_hand_in_a_readers_words() -> None:
    message = str(BodyWrittenByHand("ARC@1.a.teams", _named()))

    assert message.startswith(
        "Diagram 'ARC@1.a.teams' has a picture drawn by hand: it draws what a generated picture would not: "
    )
    assert message.endswith(
        "Saving this replacement would replace that picture with a generated one. Edit the PlantUML body "
        "instead, or state manual_layout: false to give the hand-drawn picture up."
    )
    assert not RAW_ALIAS.search(message)


def test_a_diagram_marked_manual_layout_says_so_and_lists_nothing() -> None:
    marked = HandWrittenBody(manual_layout=True)

    assert marked.reason() == "it is marked manual-layout"
    assert marked.to_mapping() == {"boxes": [], "elements": [], "relations": [], "directions": []}
