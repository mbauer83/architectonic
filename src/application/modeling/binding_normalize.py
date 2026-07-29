"""Normalize diagram binding shorthand to canonical top-level Binding records.

Diagram entity items may carry a nested ``binding:`` shorthand for convenience.
The write path also accepts shorthand forms: ``entity_id``/``backing_entity_id`` on items
(→ ``represents`` binding) and ``_scope_entity_id`` at the top of
``diagram-entities`` (→ diagram-level ``scoped-by`` binding).  All forms are
normalized to top-level Binding records; none is persisted in the output file.

Shorthand restrictions for ``binding:`` (per spec §1.2):
- Only for entity subjects (kind=entity).
- Only single-target forms: entity_id, connection_id, or diagram_local.
- connection_ids and connection_path are not expressible as shorthand.
- Only correspondence kinds: represents, scoped-by, traces-to, refines.
- Default correspondence_kind is "represents" when omitted.
"""

from __future__ import annotations

from src.domain.diagrams.bindings import (
    CORE_CORRESPONDENCE_KINDS,
    Binding,
    BindingSubject,
    Target,
    parse_binding,
    parse_target,
)

_SHORTHAND_ALLOWED_KINDS: frozenset[str] = frozenset(
    {"represents", "scoped-by", "traces-to", "refines"}
)
_SCOPE_KEY = "_scope_entity_id"


def normalize_bindings(
    diagram_entities: dict[str, object] | None,
    existing_bindings: list[dict[str, object]] | None,
) -> list[Binding]:
    """Merge explicit top-level bindings with shorthand extracted from diagram entities.

    Handles shorthand forms:
    1. Explicit ``binding:`` key on a diagram-entity item (new API, §1.2).
    2. Legacy ``entity_id`` on a diagram-entity item → ``represents`` binding.
    3. ArchiMate ``backing_entity_id`` on a diagram-entity item → ``represents`` binding.
    4. Legacy ``_scope_entity_id`` at top of diagram_entities → ``scoped-by`` binding.

    Explicit top-level bindings take precedence: if an explicit binding has the same
    id as a shorthand-derived binding, the shorthand is silently dropped.
    """
    result: list[Binding] = []
    seen_ids: set[str] = set()

    for raw in existing_bindings or []:
        if not isinstance(raw, dict):
            continue
        b = parse_binding(raw)
        result.append(b)
        seen_ids.add(b.id)

    if not diagram_entities:
        return result

    # _scope_entity_id → diagram-level scoped-by binding
    scope_eid = str(diagram_entities.get(_SCOPE_KEY) or "").strip()
    if scope_eid:
        bid = "bind-scope"
        if bid not in seen_ids:
            result.append(
                Binding(
                    id=bid,
                    subject=BindingSubject(kind="diagram"),
                    correspondence_kind="scoped-by",
                    target=Target(entity_id=scope_eid),
                )
            )
            seen_ids.add(bid)

    for entity_type, items in diagram_entities.items():
        if entity_type == _SCOPE_KEY or not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            shorthand = item.get("binding")
            if shorthand is not None:
                # binding: shorthand (new API)
                if not isinstance(shorthand, dict):
                    raise ValueError(
                        f"Diagram entity in '{entity_type}': 'binding' must be a dict, "
                        f"got {type(shorthand).__name__}"
                    )
                element_id = str(item.get("id") or "").strip()
                if not element_id:
                    raise ValueError(
                        f"Diagram entity in '{entity_type}' has a 'binding' shorthand "
                        "but no 'id' — cannot generate a stable binding id"
                    )
                binding = _normalize_shorthand(entity_type, element_id, shorthand)
                if binding.id not in seen_ids:
                    result.append(binding)
                    seen_ids.add(binding.id)
            else:
                # entity_id shorthand (legacy) / backing_entity_id shorthand (ArchiMate occurrences)
                entity_id_str = str(item.get("entity_id") or item.get("backing_entity_id") or "").strip()
                if not entity_id_str:
                    continue
                element_id = str(item.get("id") or "").strip()
                if not element_id:
                    continue
                bid = f"bind-{element_id}"
                if bid not in seen_ids:
                    result.append(
                        Binding(
                            id=bid,
                            subject=BindingSubject(kind="entity", id=element_id),
                            correspondence_kind="represents",
                            target=Target(entity_id=entity_id_str),
                            visual_role=str(item["visual_role"]) if item.get("visual_role") is not None else None,
                        )
                    )
                    seen_ids.add(bid)

    return result


def strip_diagram_shorthand(
    diagram_entities: dict[str, object] | None,
) -> dict[str, object] | None:
    """Return diagram_entities with all binding shorthand fields removed.

    Strips ``entity_id``, ``backing_entity_id``, and ``binding:`` from entity items, and removes
    the top-level ``_scope_entity_id`` key.  The result is safe to persist;
    the write path calls this after normalize_bindings so the output file
    contains only clean entity data and top-level bindings.
    """
    if not diagram_entities:
        return diagram_entities
    out: dict[str, object] = {}
    for key, value in diagram_entities.items():
        if key == _SCOPE_KEY:
            continue
        if isinstance(value, list):
            out[key] = [
                {k: v for k, v in item.items() if k not in ("entity_id", "backing_entity_id", "binding")}
                if isinstance(item, dict)
                else item
                for item in value
            ]
        else:
            out[key] = value
    return out


def _normalize_shorthand(entity_type: str, element_id: str, shorthand: dict[str, object]) -> Binding:
    corr_kind = str(shorthand.get("correspondence_kind") or "represents")
    if corr_kind not in CORE_CORRESPONDENCE_KINDS:
        raise ValueError(
            f"Shorthand binding for '{element_id}' (type '{entity_type}'): "
            f"'{corr_kind}' is not a core correspondence kind"
        )
    if corr_kind not in _SHORTHAND_ALLOWED_KINDS:
        raise ValueError(
            f"Shorthand binding for '{element_id}' (type '{entity_type}'): "
            f"'{corr_kind}' cannot be expressed as shorthand — "
            "use an explicit top-level binding"
        )

    target_raw = shorthand.get("target")
    if not isinstance(target_raw, dict):
        raise ValueError(
            f"Shorthand binding for '{element_id}' (type '{entity_type}'): "
            f"'target' must be a dict, got {type(target_raw).__name__}"
        )
    if target_raw.get("connection_ids") is not None:
        raise ValueError(
            f"Shorthand binding for '{element_id}': connection_ids is a multi-target "
            "form — use an explicit top-level binding"
        )
    if target_raw.get("connection_path") is not None:
        raise ValueError(
            f"Shorthand binding for '{element_id}': connection_path cannot be "
            "expressed as shorthand — use an explicit top-level binding"
        )

    target = parse_target(target_raw)
    return Binding(
        id=f"bind-{element_id}",
        subject=BindingSubject(kind="entity", id=element_id),
        correspondence_kind=corr_kind,
        target=target,
    )
