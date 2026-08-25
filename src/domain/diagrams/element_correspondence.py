"""What a diagram element says it corresponds to in the model.

Split from `bindings.py`, which owns the binding *data model* — the dataclasses, the schema, and
parsing to and from the persisted shape. This module owns the questions asked *of* those bindings on
the read path, and it is where every consumer that wants "which model entity does this element stand
for" must come.

The persist path is deliberately lossy of shorthand: `strip_diagram_shorthand` removes
`entity_id`, `backing_entity_id`, `binding:` and `_scope_entity_id` from `diagram-entities`, because
the top-level `bindings:` block is the canonical form. Every consumer that wants "which model
entity does this diagram element stand for" must therefore read it from here.
It is stated once, in the domain, because three consumers each answered it by reading a field the
persist path guarantees is absent — and the result was a C4 diagram whose elements selected nothing
and whose drill-down badges never appeared, with a green suite the whole time.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ElementCorrespondence:
    """One statement an element makes about the model: what it corresponds to, and how."""

    correspondence_kind: str
    entity_id: str


def element_correspondences(bindings: object) -> dict[str, tuple[ElementCorrespondence, ...]]:
    """Diagram-local element id → every model correspondence it declares, in declaration order.

    Reads the raw (frontmatter) binding shape rather than `Binding`, because every caller has the
    persisted dict in hand and converting first would be ceremony. Only `subject.kind == "entity"`
    bindings carry an element correspondence; a diagram-level `scoped-by` is a different question,
    answered by `diagram_scope_entity_id`.

    All of them, and the kind with each: an element may `represents` one entity and `traces-to`
    another, and a reader who is shown one of the two learns something false about the other. The
    kind is the whole content of the statement — "represents" and "traces-to" are different claims —
    so dropping it would leave a link with nothing to say about itself.
    """
    resolved: dict[str, list[ElementCorrespondence]] = {}
    if not isinstance(bindings, list):
        return {}
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        subject = binding.get("subject")
        target = binding.get("target")
        if not isinstance(subject, dict) or not isinstance(target, dict):
            continue
        if subject.get("kind") != "entity":
            continue
        element_id = str(subject.get("id") or "").strip()
        entity_id = str(target.get("entity_id") or "").strip()
        kind = str(binding.get("correspondence_kind") or "").strip()
        if element_id and entity_id:
            resolved.setdefault(element_id, []).append(ElementCorrespondence(kind, entity_id))
    return {element: tuple(items) for element, items in resolved.items()}


def element_entity_ids(bindings: object) -> dict[str, str]:
    """Diagram-local element id → the model entity it represents, keeping the first declared.

    The narrow reading, kept because its callers navigate to *an* entity and a second target gives
    them nothing to do. Derived from `element_correspondences` rather than walking the bindings
    again: two readings of one block is how they come to disagree about what a binding is.
    """
    return {
        element: items[0].entity_id
        for element, items in element_correspondences(bindings).items()
        if items
    }


