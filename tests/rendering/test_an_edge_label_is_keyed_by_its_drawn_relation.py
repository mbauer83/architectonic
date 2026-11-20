"""A label stated for one drawn relation reaches that arrow and no other.

The alias pair that keyed a label could not tell two relations between one pair apart, nor the
arrow at an element's second drawing from the one at its first. The key is the connection, and the
instances at its ends where either is a further occurrence.
"""

from __future__ import annotations

from src.domain.artifact_id import stable_conn_id
from src.infrastructure.rendering.diagram_builder import generate_archimate_puml_body
from tests.support.archimate_scenes import DIAGRAM_TYPE, E, connection

_SERVING = connection(E["orders"], "serving", E["billing"])
_FLOW = connection(E["orders"], "flow", E["billing"])
_ASSIGNED = connection(E["clerk"], "assignment", E["process"])
_AGAIN = "occ-clerk-again"


def _arrows(body: str) -> list[str]:
    return [line for line in body.splitlines() if "ACX_app001 " in line and "ACX_app002" in line and ">" in line]


def test_two_relations_between_one_pair_are_labelled_apart() -> None:
    body = generate_archimate_puml_body(
        "Two relations", [E["orders"], E["billing"]], [_SERVING, _FLOW], diagram_type=DIAGRAM_TYPE,
        edge_labels={stable_conn_id(_SERVING.artifact_id): "reads", stable_conn_id(_FLOW.artifact_id): "sends"},
    )

    labels = sorted(line.rpartition(" : ")[2] for line in _arrows(body))
    assert labels == ["reads", "sends"]


def test_a_label_on_one_of_two_relations_leaves_the_other_as_derived() -> None:
    unlabelled = generate_archimate_puml_body(
        "Two relations", [E["orders"], E["billing"]], [_SERVING, _FLOW], diagram_type=DIAGRAM_TYPE,
    )
    body = generate_archimate_puml_body(
        "Two relations", [E["orders"], E["billing"]], [_SERVING, _FLOW], diagram_type=DIAGRAM_TYPE,
        edge_labels={stable_conn_id(_FLOW.artifact_id): "sends"},
    )

    changed = [line for line in _arrows(body) if line not in _arrows(unlabelled)]
    assert len(changed) == 1 and changed[0].endswith(" : sends")


def test_the_arrow_at_a_further_occurrence_is_labelled_by_its_own_key() -> None:
    stated = {
        "diagram_entities": {"occurrence": [{"id": _AGAIN, "backing_entity_id": E["clerk"].artifact_id}]},
        "diagram_connections": [
            {"artifact_id": _ASSIGNED.artifact_id},
            {"artifact_id": _ASSIGNED.artifact_id, "source-occurrence": _AGAIN},
        ],
    }
    key_at_the_copy = f"{stable_conn_id(_ASSIGNED.artifact_id)}@{_AGAIN}>PXX@1700000000.prc001"

    body = generate_archimate_puml_body(
        "The clerk twice", [E["clerk"], E["process"]], [_ASSIGNED], diagram_type=DIAGRAM_TYPE,
        edge_labels={key_at_the_copy: "covers"}, **stated,  # type: ignore[arg-type]
    )

    arrows = [line for line in body.splitlines() if "PXX_prc001" in line and "RXX_rol001" in line and ">" in line]
    assert len(arrows) == 2
    assert [line.endswith(" : covers") for line in sorted(arrows)] == [False, True], arrows
    assert next(line for line in arrows if line.endswith(" : covers")).startswith("RXX_rol001__2 ")
