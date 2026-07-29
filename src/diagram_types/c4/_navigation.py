"""C4 diagram navigation: computes parent/child C4 diagram links from shared scope entities."""

from __future__ import annotations

from typing import Any

_C4_LEVELS: dict[str, int] = {
    "c4-system-landscape": 0,
    "c4-system-context": 1,
    "c4-container": 2,
    "c4-component": 3,
}


def scope_entity_id(diagram_entities: dict[str, Any]) -> str:
    explicit = str(diagram_entities.get("_scope_entity_id") or "").strip()
    if explicit:
        return explicit
    for key, items in diagram_entities.items():
        if key.startswith("_") or not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("scope") and item.get("entity_id"):
                return str(item["entity_id"])
    return ""


def item_entity_ids(diagram_entities: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for key, items in diagram_entities.items():
        if key.startswith("_") or not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("entity_id"):
                result.add(str(item["entity_id"]))
    return result


def _scope_from_bindings(bindings: Any) -> str:
    """Resolve the diagram-level ``scoped-by`` binding's target entity id.

    Model-backed C4 diagrams keep ``diagram-entities`` empty and record their scope as a
    diagram-level ``scoped-by`` binding, so navigation must read the scope from there rather
    than from the (empty) diagram-entities.
    """
    if not isinstance(bindings, list):
        return ""
    for b in bindings:
        if not isinstance(b, dict):
            continue
        subject = b.get("subject")
        if (
            isinstance(subject, dict)
            and subject.get("kind") == "diagram"
            and b.get("correspondence_kind") == "scoped-by"
        ):
            target = b.get("target")
            if isinstance(target, dict) and target.get("entity_id"):
                return str(target["entity_id"])
    return ""


def _extra(record: Any) -> dict[str, Any]:
    extra = getattr(record, "extra", None)
    return extra if isinstance(extra, dict) else {}


def _diagram_entities_of(record: Any) -> dict[str, Any]:
    de = _extra(record).get("diagram-entities")
    return de if isinstance(de, dict) else {}


def _scope_of(record: Any) -> str:
    """Diagram scope from diagram-entities (standalone) or the scoped-by binding (model-backed)."""
    return scope_entity_id(_diagram_entities_of(record)) or _scope_from_bindings(_extra(record).get("bindings"))


def _items_of(record: Any) -> set[str]:
    """Entity ids appearing in a diagram — from diagram-entities or, for model-backed diagrams, entity-ids-used."""
    ids = item_entity_ids(_diagram_entities_of(record))
    if ids:
        return ids
    used = _extra(record).get("entity-ids-used")
    return {str(x) for x in used} if isinstance(used, list) else set()


def build_c4_navigation(
    repo: Any,
    current_id: str,
    diagram_type: str,
    diagram_entities: dict[str, Any],
) -> dict[str, Any] | None:
    current_level = _C4_LEVELS.get(diagram_type)
    if current_level is None:
        return None

    all_diagrams = list(repo.list_diagrams())
    current = next((d for d in all_diagrams if d.artifact_id == current_id), None)

    # Resolve scope and item set robustly: the passed diagram_entities is authoritative for
    # standalone diagrams, but model-backed diagrams keep it empty and carry the scope in a
    # scoped-by binding and the items in entity-ids-used.
    scope_id = scope_entity_id(diagram_entities) or (_scope_of(current) if current is not None else "")
    current_item_ids = item_entity_ids(diagram_entities) or (_items_of(current) if current is not None else set())
    scope_entity = repo.get_entity(scope_id) if scope_id else None

    parents: list[dict[str, Any]] = []
    children: list[dict[str, Any]] = []

    for other in all_diagrams:
        if other.artifact_id == current_id or other.diagram_type not in _C4_LEVELS:
            continue
        other_level = _C4_LEVELS[other.diagram_type]
        other_scope_id = _scope_of(other)
        link: dict[str, Any] = {
            "diagram_id": other.artifact_id,
            "diagram_name": other.name,
            "diagram_type": other.diagram_type,
        }

        # L1 ↔ L2: both scope the same software-system
        if (
            diagram_type in ("c4-system-context", "c4-container")
            and other.diagram_type in ("c4-system-context", "c4-container")
            and scope_id
            and other_scope_id == scope_id
        ):
            (parents if other_level < current_level else children).append(link)

        # L2 → L3: L3's scope container appears as an item in this L2
        elif diagram_type == "c4-container" and other.diagram_type == "c4-component":
            if other_scope_id and other_scope_id in current_item_ids:
                children.append({**link, "scope_entity_id": other_scope_id})

        # L3 → L2: this L3's scope container appears as an item in the other L2
        elif diagram_type == "c4-component" and other.diagram_type == "c4-container":
            if scope_id and scope_id in _items_of(other):
                parents.append(link)

    return {
        "current_level": current_level,
        "scope_entity_id": scope_id or None,
        "scope_entity_name": scope_entity.name if scope_entity else None,
        "parent_diagrams": parents,
        "child_diagrams": children,
    }
