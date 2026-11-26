"""What a body draws that the body generated from its composition does not: the constructs a hand put there."""

from __future__ import annotations

from src.application.modeling.hand_drawn_constructs import HandDrawnRelation, hand_drawn

GENERATED = """@startuml
top to bottom direction
rectangle "Business" <<BusinessGrouping>> {
  rectangle "Architect" <<business_actor>> as ACT_a
  rectangle "Repository" <<business_object>> as BOB_r
}
ACT_a --> BOB_r
ACT_a -[hidden]right- BOB_r
@enduml
"""


def test_the_generated_body_draws_nothing_by_hand() -> None:
    assert not hand_drawn(GENERATED, GENERATED)


def test_a_box_the_composition_does_not_state_is_hand_drawn() -> None:
    body = GENERATED.replace(
        '  rectangle "Architect" <<business_actor>> as ACT_a\n',
        '  rectangle "Team A" <<BusinessGrouping>> {\n  rectangle "Architect" <<business_actor>> as ACT_a\n  }\n',
    )

    found = hand_drawn(body, GENERATED)

    assert found.boxes == ("Team A",)


def test_a_further_drawing_and_its_relation_are_hand_drawn() -> None:
    body = GENERATED.replace(
        "ACT_a --> BOB_r\n",
        'ACT_a --> BOB_r\nrectangle "Repository" <<business_object>> as BOB_r__2\nACT_a -- BOB_r__2\n',
    )

    found = hand_drawn(body, GENERATED)

    assert found.elements == ("BOB_r__2",)
    assert found.relations == (HandDrawnRelation("ACT_a", "BOB_r__2"),)


def test_a_relation_drawn_the_other_way_round_or_hidden_is_not_hand_drawn() -> None:
    body = GENERATED.replace("ACT_a --> BOB_r\n", "BOB_r <-- ACT_a\nBOB_r -[hidden]down- ACT_a\n")

    assert not hand_drawn(body, GENERATED).relations


def test_a_direction_the_generated_body_does_not_state_is_hand_drawn() -> None:
    body = GENERATED.replace("top to bottom direction", "left to right direction")

    assert hand_drawn(body, GENERATED).directions == ("left to right direction",)


def test_stating_plantumls_own_direction_is_not_hand_drawn() -> None:
    generated = GENERATED.replace("top to bottom direction\n", "")

    assert not hand_drawn(GENERATED, generated)
