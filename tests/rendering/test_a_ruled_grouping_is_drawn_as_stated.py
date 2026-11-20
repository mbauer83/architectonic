"""A diagram that states a ruled grouping draws the boxes it states, and no box it does not.

The body generator computes a box per domain and gathers some types into boxes of their own. Once a
diagram states a grouping whose membership is a rule, its groupings are the whole list of boxes:
each ruled box holds what its rule admits, a listed grouping still claims first, and whatever no
grouping holds stands on the canvas unboxed.
"""

from __future__ import annotations

import re

from src.domain.diagrams.layout.box_aliases import BoxKind, box_kind
from src.infrastructure.rendering.diagram_builder import generate_archimate_puml_body
from tests.support.archimate_scenes import DIAGRAM_TYPE, SCENES, E

_ORDER_HANDLING = SCENES[0]
_BOX = re.compile(r'^(?P<indent> *)rectangle "(?P<label>[^"]*)" <<[^>]*>> as (?P<alias>\w+) \{$')
_ELEMENT = re.compile(r'^(?P<indent> *)(?:rectangle|circle) "[^"]*"(?: <<[^>]*>>)? as (?P<alias>\w+)\b.*$')


def _body(groupings: list[dict[str, object]]) -> str:
    return generate_archimate_puml_body(
        _ORDER_HANDLING.name, list(_ORDER_HANDLING.entities), list(_ORDER_HANDLING.connections),
        diagram_type=DIAGRAM_TYPE, authored_groupings=groupings,
    )


def _boxes(body: str) -> dict[str, list[str]]:
    """Each grouping box by its label, with the aliases declared anywhere inside it."""
    element_aliases = {entity.display_alias for entity in _ORDER_HANDLING.entities}
    inside: dict[str, list[str]] = {}
    open_boxes: list[tuple[int, str]] = []
    for line in body.splitlines():
        indent = len(line) - len(line.lstrip(" "))
        if line.strip() == "}":
            if open_boxes and open_boxes[-1][0] == indent:
                open_boxes.pop()
            continue
        declared = _ELEMENT.match(line)
        if declared is None:
            continue
        alias = declared.group("alias")
        if alias in element_aliases:
            for _indent, label in open_boxes:
                inside[label].append(alias)
            continue
        box = _BOX.match(line)
        if box is not None:
            inside[box.group("label")] = []
            open_boxes.append((indent, box.group("label")))
    return inside


def _computed_boxes(body: str) -> list[str]:
    aliases = re.findall(r" as (\w+) \{", body)
    return [a for a in aliases if box_kind(a, element_aliases=()) in (BoxKind.DOMAIN, BoxKind.TYPE)]


def test_a_domain_rule_draws_one_box_holding_that_domain_and_computes_no_other() -> None:
    body = _body([{"id": "g-app001", "label": "Systems We Run", "rule": {"domain": "application"}}])

    assert _boxes(body)["Systems We Run"] == ["ACX_app001", "ACX_app002"]
    assert _computed_boxes(body) == [], "a diagram that states its boxes gets none computed"
    for alias in ("PXX_prc001", "BAX_act001", "TNX_nod001", "AJX_jct001"):
        assert f"as {alias}" in body, "what no grouping holds is still drawn"


def test_a_type_rule_nested_in_a_domain_rule_takes_that_type_from_it() -> None:
    body = _body([
        {"id": "g-common1", "label": "Work", "rule": {"domain": "common"},
         "groups": [{"id": "g-roles01", "label": "People", "rule": {"type": "role"}}]},
    ])

    boxes = _boxes(body)
    assert boxes["People"] == ["RXX_rol001"]
    assert "RXX_rol001" in boxes["Work"] and "PXX_prc001" in boxes["Work"]
    assert "ACX_app001" not in boxes["Work"] and "BAX_act001" not in boxes["Work"]


def test_a_listed_grouping_claims_before_a_rule_does() -> None:
    body = _body([
        {"id": "g-app001", "label": "Systems", "rule": {"domain": "application"}},
        {"id": "g-pick01", "label": "Under Review", "entity-ids": [E["billing"].artifact_id]},
    ])

    boxes = _boxes(body)
    assert boxes["Under Review"] == ["ACX_app002"]
    assert boxes["Systems"] == ["ACX_app001"]


def test_a_rule_nothing_satisfies_draws_no_box() -> None:
    body = _body([
        {"id": "g-none01", "label": "Strategy", "rule": {"domain": "strategy"}},
        {"id": "g-app001", "label": "Systems", "rule": {"domain": "application"}},
    ])

    assert "Strategy" not in _boxes(body)
    assert "Systems" in _boxes(body)


def test_every_element_is_drawn_exactly_once_whatever_the_groupings() -> None:
    groupings: list[dict[str, object]] = [
        {"id": "g-common1", "label": "Work", "rule": {"domain": "common"},
         "groups": [{"id": "g-fn0001", "label": "Functions", "rule": {"type": "function"}}]},
        {"id": "g-tech01", "label": "Technology", "rule": {"domain": "technology"}},
        {"id": "g-pick01", "label": "Picked", "entity-ids": [E["clerk"].artifact_id]},
    ]

    body = _body(groupings)

    for entity in _ORDER_HANDLING.entities:
        declared = re.findall(rf'^ *(?:rectangle|circle) .* as {entity.display_alias}\b', body, flags=re.MULTILINE)
        assert len(declared) == 1, (entity.display_alias, declared)
    assert body.count("{") == body.count("}")


def test_a_ruled_box_does_not_pull_a_part_out_of_the_element_that_holds_it() -> None:
    """The functions are drawn inside the process that composes them; a rule chooses among what stands free."""
    body = _body([{"id": "g-fn0001", "label": "Functions", "rule": {"type": "function"}}])

    assert "Functions" not in _boxes(body)
    assert re.search(r"as PXX_prc001 \{\n(?:.*\n)*? +rectangle .* as FXX_fnc001", body)
