"""Declared containment, resolved into the tree a C4 body can draw.

A projection says which drawn item holds which other one. The renderer needs a *tree*, because PUML
declares an alias in exactly one place and a nested boundary is a block. Turning the first into the
second is this module's whole job, and it is where the choice lives when the model offers a child
more than one parent.

Beside `_resolve_model` rather than inside it, for the reason `_projection_deployment` sits beside
`_projection`: the two concerns are separable and together they broke the file-length policy.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace

from src.diagram_types.c4._resolve import _ResolvedItem


def _nest(
    internal_items: list[_ResolvedItem], contained_by: Sequence[tuple[str, str]]
) -> list[_ResolvedItem]:
    """Move each item the projection placed inside another into that one's ``children``.

    Empty ``contained_by`` leaves the list exactly as it was, which is every level but deployment.

    Built bottom-up, and that is the whole of the difficulty. The first version attached each child
    to its parent's *pre-`replace`* object, so a chain of three — a host holding a container holding
    an application — kept the container and silently dropped what was inside it. `contained_by` can
    express any chain, so a structure the renderer could not draw was reachable without anything
    failing; a diagram simply came back missing its contents.

    **A child may be offered more than one parent, and the choice is made here.** PUML declares an
    alias in exactly one place, so the drawing is a tree however many placements the model states —
    but which placement to draw depends on which parents this view is *keeping*, and only this
    function knows that. The projection used to decide instead, by truncating to the first host, and
    a view that then filtered that host out left the child with no surviving parent: it floated to
    the top level beside the host that does hold it. Deployment scenarios are exactly that case.

    Where several offered parents survive, the first by id wins — deterministic, and independent of
    the order the pairs arrive in, so a redraw does not move a box. The other placements are real and
    not drawn; a view narrowed to one of them shows each container once, in the host that holds it.

    A cycle in the declared containment would recurse forever, so each branch carries the ancestors
    it has already passed through and stops rather than following one.
    """
    if not contained_by:
        return internal_items
    by_id = {item.local_id: item for item in internal_items}
    offered: dict[str, list[str]] = {}
    for child_id, parent_id in contained_by:
        if child_id != parent_id and child_id in by_id and parent_id in by_id:
            offered.setdefault(child_id, []).append(parent_id)
    chosen = {child_id: min(parents) for child_id, parents in offered.items()}
    children_of: dict[str, list[str]] = {}
    placed: set[str] = set()
    # Arrival order within a parent, so the sibling order a diagram already has does not change.
    for child_id, parent_id in contained_by:
        if child_id in placed or chosen.get(child_id) != parent_id:
            continue
        children_of.setdefault(parent_id, []).append(child_id)
        placed.add(child_id)
    nested_ids = set(placed)

    def build(item_id: str, ancestors: frozenset[str]) -> _ResolvedItem:
        seen = ancestors | {item_id}
        kids = tuple(
            build(child_id, seen)
            for child_id in children_of.get(item_id, ())
            if child_id not in seen
        )
        return replace(by_id[item_id], children=kids)

    return [
        build(item.local_id, frozenset())
        for item in internal_items
        if item.local_id not in nested_ids
    ]


def _boundary_aliases(
    scope_items: Sequence[_ResolvedItem],
    nested_internal: Sequence[_ResolvedItem],
    scope_render_mode: str,
) -> set[str]:
    """Every alias that names a boundary rather than an element, so no edge may land on one.

    A C4 boundary is not an element and cannot be an endpoint of a relationship. Three things are
    drawn as one and they were not recognised as the same thing: the scope in `boundary` mode, a
    grouping, and a deployment node holding containers. Naming only the first left four arrows
    running from the Architecture Backend's own boundary to components inside it — which reads as a
    thing depending on its own parts — and then, once groupings became boundaries too, six more
    running onto the Assurance Module group.

    "Has children" is the test rather than the item type, because it is exactly the test the
    renderer applies when it decides to open a boundary instead of drawing a box: a grouping the
    level draws nothing inside is not drawn at all, and an unoccupied deployment node is a plain
    container that an edge may perfectly well reach.

    The membership is still recorded — `scope_of` says which boundary contains the element — and it
    is only the drawing that is declined. Context and landscape draw their scope as an element, so
    there the same edge is meaningful and is kept.
    """
    scope_boundary = {i.alias for i in scope_items} if scope_render_mode == "boundary" else set()
    return scope_boundary | {i.alias for i in nested_internal if i.children}


def _flatten(items: Iterable[_ResolvedItem]) -> list[_ResolvedItem]:
    """Every item in a nesting, at any depth — what "drawn" means once boxes can hold boxes."""
    out: list[_ResolvedItem] = []
    for item in items:
        out.append(item)
        out.extend(_flatten(item.children))
    return out
