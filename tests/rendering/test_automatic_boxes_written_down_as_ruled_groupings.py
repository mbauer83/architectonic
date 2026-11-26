"""Writing a diagram's automatic boxes down as ruled groupings: what stays the same, and what does not.

The plan's D9 has an editor do this the first time a box is created or deleted — "the current
automatic boxes are written down as ruled groupings (the same harvest-then-own pattern as the
layout)" — and expects the picture not to move when it does. This states how far that holds today,
box by box, so the stage that builds the harvest starts from an executable account of the gap
rather than from a remark.

Compared by what each box holds, not by text: a stated grouping is drawn under an authored-grouping
alias where the computed box had a domain's or a type's, so the bodies differ by construction.
"""

from __future__ import annotations

import re
import warnings

import pytest

from src.domain.diagrams.layout.box_aliases import BoxKind, box_kind
from src.infrastructure.rendering.diagram_builder import generate_puml_body
from tests.support.archimate_scenes import DIAGRAM_TYPE, SCENES, Scene, connection, entity

_DECLARED = re.compile(r'^ *(?:rectangle|circle) "(?P<label>[^"]*)"(?: <<[^>]*>>)? as (?P<alias>\w+)\b(?P<opens>.*\{)?')

#: Scenes whose body computes its boxes: none states a grouping.
_COMPUTED = [scene for scene in SCENES if not scene.statements.get("authored_groupings")]


def _body(scene: Scene, groupings: list[dict[str, object]] | None = None) -> str:
    statements = {**scene.statements, **({"authored_groupings": groupings} if groupings else {})}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return generate_puml_body(
            scene.name, list(scene.entities), list(scene.connections), diagram_type=DIAGRAM_TYPE,
            **statements,  # type: ignore[arg-type]
        )


def _boxes(body: str, elements: frozenset[str]) -> list[tuple[tuple[str, ...], str, frozenset[str]]]:
    """Every box that is not an element: the labels of the boxes around it, its alias, what it holds at any depth."""
    found: dict[str, tuple[tuple[str, ...], set[str]]] = {}
    open_boxes: list[tuple[str, str] | None] = []
    for line in body.splitlines():
        if line.strip() == "}":
            open_boxes.pop()
            continue
        declared = _DECLARED.match(line)
        if declared is None:
            continue
        alias, label = declared.group("alias"), declared.group("label")
        if alias in elements:
            for outer in open_boxes:
                if outer is not None:
                    found[outer[0]][1].add(alias)
            if declared.group("opens"):
                open_boxes.append(None)  # an element holding its parts: not a box of the kind compared
            continue
        if declared.group("opens"):
            found[alias] = (tuple(outer[1] for outer in open_boxes if outer is not None) + (label,), set())
            open_boxes.append((alias, label))
    return [(path, alias, frozenset(members)) for alias, (path, members) in found.items()]


def _written_down(body: str, scene: Scene) -> list[dict[str, object]]:
    """The computed boxes of *body* as the ruled groupings that say the same: a domain, and types within it."""
    by_alias = {entity.display_alias: entity for entity in scene.entities}
    elements = frozenset(by_alias)
    groupings: list[dict[str, object]] = []
    by_path: dict[tuple[str, ...], dict[str, object]] = {}
    for path, alias, members in _boxes(body, elements):
        kind = box_kind(alias, element_aliases=elements)
        if kind is BoxKind.DOMAIN:
            entry: dict[str, object] = {"label": path[-1], "rule": {"domain": alias.removeprefix("DOM_")}}
            groupings.append(entry)
        else:
            (member_type,) = {by_alias[member].artifact_type for member in members}
            entry = {"label": path[-1], "rule": {"type": member_type}}
            parent = by_path.get(path[:-1])
            (parent.setdefault("groups", []) if parent is not None else groupings).append(entry)  # type: ignore[union-attr]
        by_path[path] = entry
    return groupings


def _held(body: str, scene: Scene) -> dict[tuple[str, ...], frozenset[str]]:
    elements = frozenset(entity.display_alias for entity in scene.entities)
    held: dict[tuple[str, ...], frozenset[str]] = {}
    for path, _alias, members in _boxes(body, elements):
        held[path] = held.get(path, frozenset()) | members
    return held


@pytest.mark.parametrize("scene", _COMPUTED, ids=lambda scene: scene.slug)
def test_every_computed_box_has_a_rule_that_says_the_same(scene: Scene) -> None:
    """What does hold: each computed box can be stated, and every element is still drawn once."""
    computed = _body(scene)
    stated = _body(scene, _written_down(computed, scene) or None)

    for drawn in scene.entities:
        assert len(re.findall(rf" as {drawn.display_alias}\b", stated.split("' Connections")[0])) == 1


@pytest.mark.parametrize("scene", _COMPUTED, ids=lambda scene: scene.slug)
def test_the_stated_boxes_hold_what_the_computed_ones_held(scene: Scene) -> None:
    computed = _body(scene)
    groupings = _written_down(computed, scene)
    if not groupings:
        pytest.skip("this scene computes no box: one domain, and no type gathered")

    assert _held(_body(scene, groupings), scene) == _held(computed, scene)


def _two_flows() -> Scene:
    """Two flows on one canvas: two events start the first, one the second."""
    events = [entity(f"evt00{number}", "event", f"Event {number}") for number in (1, 2, 3)]
    functions = [entity(f"fnc10{number}", "function", f"Function {number}") for number in (1, 2, 3, 4)]
    return Scene("Two flows", (*events, *functions), (
        connection(events[0], "triggering", functions[0]), connection(events[1], "triggering", functions[0]),
        connection(functions[0], "triggering", functions[1]),
        connection(events[2], "triggering", functions[2]), connection(functions[2], "triggering", functions[3]),
    ))


@pytest.mark.xfail(
    strict=True,
    reason=(
        "PLAN-0.12.0-archimate-layout D9, harvest-then-own ('the current automatic boxes are written "
        "down as ruled groupings'): the canvas boxes a type per flow — the two events that start the "
        "first flow are boxed, the one that starts the second stands bare — while a rule {type: event} "
        "admits every event its parent holds, so the stated box takes the third as well. A computed box "
        "that holds only some of a type has no ruled grouping that says the same; the harvest has to "
        "write such a box down as a listed grouping, or a rule has to be able to say 'of this flow'."
    ),
)
def test_a_type_boxed_in_one_flow_and_bare_in_another_is_written_down_as_it_was() -> None:
    scene = _two_flows()
    computed = _body(scene)

    assert _held(_body(scene, _written_down(computed, scene)), scene) == _held(computed, scene)
