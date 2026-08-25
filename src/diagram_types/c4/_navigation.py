"""C4 diagram navigation: which other C4 diagrams a diagram sits above, below, or beside.

Two axes, not one depth. `_C4_LEVELS` orders *containment* altitude — a landscape holds systems,
a system holds containers, a container holds components — and a drill-down moves along it. A
deployment view crosses that axis rather than extending it: it shows the same containers placed on
technology nodes, so calling it level 4 would claim it sits below components, which it does not.
It is a lookup from a diagram's scope instead, and the two directions are named separately so
neither has to be read as a parent or a child.
"""

from __future__ import annotations

from typing import Any

from src.diagram_types.c4._projection_vocabulary import LANDSCAPE_TYPE
from src.domain.diagrams.bindings import (
    SCOPE_IDS_KEY,
    SCOPE_KEY,
    diagram_scope_entity_ids,
    parse_bindings,
    scope_shorthand,
)
from src.domain.diagrams.element_correspondence import (
    element_entity_ids,
)

#: Registered C4 types and their containment depth. `c4-deployment` is deliberately absent: it is
#: the other axis, and a level for it would say it sits below components.
_C4_LEVELS: dict[str, int] = {
    LANDSCAPE_TYPE: 0,
    "c4-system-context": 1,
    "c4-container": 2,
    "c4-component": 3,
}

#: The type that shows where a system's containers run.
DEPLOYMENT_TYPE = "c4-deployment"

_C4_TYPES: frozenset[str] = frozenset(_C4_LEVELS) | {DEPLOYMENT_TYPE}


def scope_element_id(diagram_entities: dict[str, Any]) -> str:
    """The diagram-local id of the item marked ``scope: true``.

    `scope` survives persistence; `entity_id` does not. So the scope is found in two steps now —
    which element is the scope, then what that element is bound to.
    """
    for key, items in diagram_entities.items():
        if key.startswith("_") or not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("scope") and item.get("id"):
                return str(item["id"])
    return ""


def element_ids(diagram_entities: dict[str, Any]) -> list[str]:
    """Every diagram-local element id, in declaration order."""
    found: list[str] = []
    for key, items in diagram_entities.items():
        if key.startswith("_") or not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("id"):
                found.append(str(item["id"]))
    return found


def scope_entity_ids(diagram_entities: dict[str, Any]) -> tuple[str, ...]:
    """The scope this diagram's entities declare in shorthand, or the items marked as scope."""
    from src.diagram_types.c4._resolve import scope_ids_in  # noqa: PLC0415

    explicit = scope_ids_in(diagram_entities)
    if explicit:
        return explicit
    for key, items in diagram_entities.items():
        if key.startswith("_") or not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("scope") and item.get("entity_id"):
                return (str(item["entity_id"]),)
    return ()


def item_entity_ids(diagram_entities: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for key, items in diagram_entities.items():
        if key.startswith("_") or not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("entity_id"):
                result.add(str(item["entity_id"]))
    return result


def _extra(record: Any) -> dict[str, Any]:
    extra = getattr(record, "extra", None)
    return extra if isinstance(extra, dict) else {}


def _diagram_entities_of(record: Any) -> dict[str, Any]:
    de = _extra(record).get("diagram-entities")
    return de if isinstance(de, dict) else {}


def resolve_scope_entity_ids(diagram_entities: dict[str, Any], bindings: Any) -> tuple[str, ...]:
    """The entities a C4 diagram is scoped to, from whichever of the three shapes it was written in.

    Shared by navigation and by the read envelope's scope back-fill, because answering it
    differently in two places is how one of them came to answer `""` for every diagram the write
    path produces.
    """
    shorthand = scope_entity_ids(diagram_entities)
    if shorthand:
        return shorthand
    element = scope_element_id(diagram_entities)
    if element:
        bound = element_entity_ids(bindings).get(element, "")
        if bound:
            return (bound,)
    return diagram_scope_entity_ids(bindings)


def resolve_scope_entity_id(diagram_entities: dict[str, Any], bindings: Any) -> str:
    """The single entity a C4 diagram is scoped to, or ``""`` — a filter over the set form."""
    scope = resolve_scope_entity_ids(diagram_entities, bindings)
    return scope[0] if scope else ""


def resolve_scope_shorthand(
    diagram_entities: dict[str, Any], bindings: Any
) -> tuple[str, object] | None:
    """The ``diagram-entities`` key and value this diagram's scope is written under, if it has one.

    Same precedence as `resolve_scope_entity_ids`: what the entities already declare wins, then an
    element-level binding, then the diagram-level one. What is new is the *key* a diagram-level
    binding comes back under — the one its target shape says, by the same rule the render path
    restores it with, so `_scope_entity_ids: [one]` comes back as itself rather than as the
    singular key and a reader never has to guess whether a one-element list means "one system" or
    "the first of several".
    """
    for key in (SCOPE_KEY, SCOPE_IDS_KEY):
        declared = diagram_entities.get(key)
        if declared:
            return (key, declared)
    element = scope_element_id(diagram_entities)
    if element:
        bound = element_entity_ids(bindings).get(element, "")
        if bound:
            return (SCOPE_KEY, bound)
    for binding in parse_bindings(bindings if isinstance(bindings, list) else None):
        if (
            binding.correspondence_kind == "scoped-by"
            and binding.subject.kind == "diagram"
            and (binding.target.entity_id or binding.target.entity_ids)
        ):
            return scope_shorthand(binding.target)
    return None


def _scope_of(record: Any) -> tuple[str, ...]:
    """The entities this diagram is scoped to, however it was written.

    Three shapes, and the *persisted* one is the third — which is why this had to change. A
    standalone C4 diagram is authored with `entity_id` on the scope item, and the write path strips
    it into an element-level `represents` binding; a model-backed one carries a diagram-level
    `scoped-by` binding. Reading only the first two answered nothing for every diagram the product
    actually writes.
    """
    return resolve_scope_entity_ids(_diagram_entities_of(record), _extra(record).get("bindings"))


def _items_of(record: Any) -> set[str]:
    """Entity ids appearing in a diagram, from whichever of the three shapes it was written in."""
    entities = _diagram_entities_of(record)
    ids = item_entity_ids(entities)
    if ids:
        return ids
    bound = element_entity_ids(_extra(record).get("bindings"))
    if bound:
        from_elements = {bound[element] for element in element_ids(entities) if element in bound}
        if from_elements:
            return from_elements
    used = _extra(record).get("entity-ids-used")
    return {str(x) for x in used} if isinstance(used, list) else set()


def _link(other: Any) -> dict[str, Any]:
    return {
        "diagram_id": other.artifact_id,
        "diagram_name": other.name,
        "diagram_type": other.diagram_type,
    }


def _containment_relation(
    *,
    diagram_type: str,
    current_level: int,
    scope_ids: tuple[str, ...],
    current_item_ids: set[str],
    other: Any,
    other_scope_ids: tuple[str, ...],
) -> tuple[str, dict[str, Any]] | None:
    """Where *other* sits relative to this diagram on the containment axis, if anywhere.

    Returns ``("parent" | "child", link)``. A child link carries the entity it zooms into, which is
    what puts the drill-down badge on the right node rather than on the diagram as a whole.
    """
    other_level = _C4_LEVELS.get(other.diagram_type)
    if other_level is None:
        return None
    scope_set, other_scope_set = set(scope_ids), set(other_scope_ids)

    # L0 → L1: a landscape's children are the context views of the systems it holds.
    if diagram_type == LANDSCAPE_TYPE and other.diagram_type == "c4-system-context":
        zoomed = other_scope_set & scope_set
        return ("child", {**_link(other), "scope_entity_id": sorted(zoomed)[0]}) if zoomed else None
    if diagram_type == "c4-system-context" and other.diagram_type == LANDSCAPE_TYPE:
        return ("parent", _link(other)) if scope_set & other_scope_set else None

    # L1 ↔ L2: both scope the same software-system.
    if (
        diagram_type in ("c4-system-context", "c4-container")
        and other.diagram_type in ("c4-system-context", "c4-container")
        and scope_set
        and other_scope_set == scope_set
    ):
        return ("parent" if other_level < current_level else "child", _link(other))

    # L2 → L3: the L3's scope container appears as an item in this L2.
    if diagram_type == "c4-container" and other.diagram_type == "c4-component":
        zoomed = other_scope_set & current_item_ids
        return ("child", {**_link(other), "scope_entity_id": sorted(zoomed)[0]}) if zoomed else None

    # L3 → L2: this L3's scope container appears as an item in the other L2.
    if diagram_type == "c4-component" and other.diagram_type == "c4-container":
        return ("parent", _link(other)) if scope_set & _items_of(other) else None

    return None


def build_c4_navigation(
    repo: Any,
    current_id: str,
    diagram_type: str,
    diagram_entities: dict[str, Any],
) -> dict[str, Any] | None:
    if diagram_type not in _C4_TYPES:
        return None
    current_level = _C4_LEVELS.get(diagram_type)

    all_diagrams = list(repo.list_diagrams())
    current = next((d for d in all_diagrams if d.artifact_id == current_id), None)

    # Resolve scope and item set robustly: the passed diagram_entities is authoritative for
    # standalone diagrams, but model-backed diagrams keep it empty and carry the scope in a
    # scoped-by binding and the items in entity-ids-used.
    scope_ids = scope_entity_ids(diagram_entities) or (_scope_of(current) if current is not None else ())
    current_item_ids = item_entity_ids(diagram_entities) or (_items_of(current) if current is not None else set())
    scope_entities = [entity for eid in scope_ids if (entity := repo.get_entity(eid)) is not None]

    parents: list[dict[str, Any]] = []
    children: list[dict[str, Any]] = []
    deployments: list[dict[str, Any]] = []
    subjects: list[dict[str, Any]] = []

    for other in all_diagrams:
        if other.artifact_id == current_id or other.diagram_type not in _C4_TYPES:
            continue
        other_scope_ids = _scope_of(other)

        # The second axis: a deployment view and a logical view of the same scope are neither
        # above nor below one another, so each names the other in its own field.
        if other.diagram_type == DEPLOYMENT_TYPE and current_level is not None:
            if set(other_scope_ids) & set(scope_ids):
                deployments.append(_link(other))
            continue
        if diagram_type == DEPLOYMENT_TYPE:
            if set(other_scope_ids) & set(scope_ids):
                subjects.append(_link(other))
            continue
        if current_level is None:
            continue

        relation = _containment_relation(
            diagram_type=diagram_type,
            current_level=current_level,
            scope_ids=scope_ids,
            current_item_ids=current_item_ids,
            other=other,
            other_scope_ids=other_scope_ids,
        )
        if relation is not None:
            direction, link = relation
            (parents if direction == "parent" else children).append(link)

    return {
        "current_level": current_level,
        "scope_entity_id": scope_ids[0] if scope_ids else None,
        "scope_entity_ids": list(scope_ids),
        "scope_entity_name": scope_entities[0].name if scope_entities else None,
        "scope_entity_names": [entity.name for entity in scope_entities],
        "parent_diagrams": parents,
        "child_diagrams": children,
        "deployment_diagrams": deployments,
        "subject_diagrams": subjects,
    }
