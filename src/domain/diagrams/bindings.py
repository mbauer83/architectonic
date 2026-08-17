"""Binding data model — the single diagram↔model correspondence mechanism.

A Binding relates a diagram subject (entity, connection, or the diagram itself)
to a model target via a declared correspondence_kind.  Canonical bindings live
at the top-level ``bindings:`` frontmatter key of every diagram.  The write
path also accepts nested ``binding:`` shorthand on diagram entity items and
normalises it here.

No sync_policy or derivation_basis fields — those are deferred per the plan.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

CORE_CORRESPONDENCE_KINDS: frozenset[str] = frozenset(
    {"represents", "abstracts", "refines", "scoped-by", "traces-to"}
)

#: The scope shorthand a diagram's entities may carry, and its set form. The write path normalises
#: either into the one diagram-level ``scoped-by`` binding below and strips it before persisting;
#: the render path puts it back. Declared here with the binding it stands for, because a diagram
#: type reads it too and spelling the key in each place is how the two came to disagree.
SCOPE_KEY = "_scope_entity_id"
SCOPE_IDS_KEY = "_scope_entity_ids"
SCOPE_KEYS: frozenset[str] = frozenset({SCOPE_KEY, SCOPE_IDS_KEY})

#: The membership shorthand a diagram's entities may carry: which of a projection's candidates the
#: diagram draws, and which it withholds. It stands for `DerivationSelection`'s included/excluded
#: entity ids the same way the scope keys above stand for the `scoped-by` binding — one fact, stated
#: in the frontmatter where it is decided and in `diagram-entities` where it is read.
#:
#: Declared here for the reason the scope keys are: the render path restores it, a diagram type
#: reads it, and it was spelled as a literal in six places across three modules.
INCLUDED_IDS_KEY = "_included_entity_ids"
EXCLUDED_IDS_KEY = "_excluded_entity_ids"
SELECTION_KEYS: frozenset[str] = frozenset({INCLUDED_IDS_KEY, EXCLUDED_IDS_KEY})


@dataclass(frozen=True)
class ConnectionPathItem:
    id: str
    reversed: bool = False


@dataclass(frozen=True)
class DiagramLocalTarget:
    element_id: str
    diagram_id: str | None = None


@dataclass(frozen=True)
class Target:
    """Tagged union; exactly one field must be set.

    ``entity_ids`` is the set form, and it exists for one correspondence: a diagram scoped by
    several entities at once. A C4 system landscape is about a portfolio rather than one system,
    and the singular ``entity_id`` could only have said which of them the diagram was *really*
    about. It is the entity counterpart of ``connection_ids``, which has carried a set since the
    first bindings shipped.
    """

    entity_id: str | None = None
    entity_ids: tuple[str, ...] | None = None
    connection_id: str | None = None
    connection_ids: tuple[str, ...] | None = None
    diagram_local: DiagramLocalTarget | None = None
    connection_path: tuple[ConnectionPathItem, ...] | None = None

    def __post_init__(self) -> None:
        filled = sum(
            v is not None
            for v in (
                self.entity_id,
                self.entity_ids,
                self.connection_id,
                self.connection_ids,
                self.diagram_local,
                self.connection_path,
            )
        )
        if filled != 1:
            raise ValueError(
                "Target must have exactly one of: entity_id, entity_ids, connection_id, "
                "connection_ids, diagram_local, connection_path"
            )


@dataclass(frozen=True)
class BindingSubject:
    kind: Literal["entity", "connection", "diagram"]
    id: str | None = None


@dataclass(frozen=True)
class Binding:
    id: str
    subject: BindingSubject
    correspondence_kind: str
    target: Target
    derived_from: str | None = None
    visual_role: str | None = None


# ---------------------------------------------------------------------------
# JSON Schema constants
# ---------------------------------------------------------------------------

BINDINGS_ARRAY_SCHEMA: dict[str, object] = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["id", "subject", "correspondence_kind", "target"],
        "properties": {
            "id": {"type": "string"},
            "subject": {
                "type": "object",
                "required": ["kind"],
                "properties": {
                    "kind": {"enum": ["entity", "connection", "diagram"]},
                    "id": {"type": "string"},
                },
            },
            "correspondence_kind": {"type": "string"},
            "target": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string"},
                    "entity_ids": {"type": "array", "items": {"type": "string"}},
                    "connection_id": {"type": "string"},
                    "connection_ids": {"type": "array", "items": {"type": "string"}},
                    "diagram_local": {
                        "type": "object",
                        "required": ["element_id"],
                        "properties": {
                            "element_id": {"type": "string"},
                            "diagram_id": {"type": "string"},
                        },
                    },
                    "connection_path": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["id"],
                            "properties": {
                                "id": {"type": "string"},
                                "reversed": {"type": "boolean"},
                            },
                        },
                    },
                },
            },
            "derived_from": {"type": "string"},
            "visual_role": {"type": "string"},
        },
    },
}

BINDING_SHORTHAND_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["target"],
    "properties": {
        "correspondence_kind": {
            "type": "string",
            "enum": ["represents", "scoped-by", "traces-to", "refines"],
        },
        "target": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "connection_id": {"type": "string"},
                "diagram_local": {
                    "type": "object",
                    "required": ["element_id"],
                    "properties": {
                        "element_id": {"type": "string"},
                        "diagram_id": {"type": "string"},
                    },
                },
            },
        },
    },
}

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_target(raw: dict[str, object]) -> Target:
    entity_id = str(raw["entity_id"]) if raw.get("entity_id") is not None else None
    connection_id = str(raw["connection_id"]) if raw.get("connection_id") is not None else None

    entity_ids: tuple[str, ...] | None = None
    raw_eids = raw.get("entity_ids")
    if raw_eids is not None:
        entity_ids = tuple(str(e) for e in raw_eids) if isinstance(raw_eids, list) else None

    connection_ids: tuple[str, ...] | None = None
    raw_cids = raw.get("connection_ids")
    if raw_cids is not None:
        connection_ids = tuple(str(c) for c in raw_cids) if isinstance(raw_cids, list) else None

    diagram_local: DiagramLocalTarget | None = None
    dl_raw = raw.get("diagram_local")
    if isinstance(dl_raw, dict):
        diagram_local = DiagramLocalTarget(
            element_id=str(dl_raw["element_id"]),
            diagram_id=str(dl_raw["diagram_id"]) if dl_raw.get("diagram_id") is not None else None,
        )

    connection_path: tuple[ConnectionPathItem, ...] | None = None
    cp_raw = raw.get("connection_path")
    if isinstance(cp_raw, list):
        connection_path = tuple(
            ConnectionPathItem(id=str(item["id"]), reversed=bool(item.get("reversed", False)))
            for item in cp_raw
            if isinstance(item, dict)
        )

    return Target(
        entity_id=entity_id,
        entity_ids=entity_ids,
        connection_id=connection_id,
        connection_ids=connection_ids,
        diagram_local=diagram_local,
        connection_path=connection_path,
    )


def parse_binding(raw: dict[str, object]) -> Binding:
    subject_raw = raw.get("subject")
    if not isinstance(subject_raw, dict):
        raise ValueError(f"Binding 'subject' must be a dict, got {type(subject_raw).__name__}")

    kind = str(subject_raw.get("kind", ""))
    if kind not in ("entity", "connection", "diagram"):
        raise ValueError(f"Invalid binding subject kind: {kind!r}")

    raw_id = subject_raw.get("id")
    subject = BindingSubject(
        kind=kind,  # type: ignore[arg-type]
        id=str(raw_id) if raw_id is not None else None,
    )

    target_raw = raw.get("target")
    if not isinstance(target_raw, dict):
        raise ValueError(f"Binding 'target' must be a dict, got {type(target_raw).__name__}")
    target = parse_target(target_raw)

    return Binding(
        id=str(raw.get("id", "")),
        subject=subject,
        correspondence_kind=str(raw.get("correspondence_kind", "")),
        target=target,
        derived_from=str(raw["derived_from"]) if raw.get("derived_from") is not None else None,
        visual_role=str(raw["visual_role"]) if raw.get("visual_role") is not None else None,
    )


def parse_bindings(raw: list[object] | None) -> list[Binding]:
    if not raw:
        return []
    return [parse_binding(item) for item in raw if isinstance(item, dict)]


def binding_to_dict(b: Binding) -> dict[str, object]:
    subject: dict[str, object] = {"kind": b.subject.kind}
    if b.subject.id is not None:
        subject["id"] = b.subject.id

    target: dict[str, object] = {}
    if b.target.entity_id is not None:
        target["entity_id"] = b.target.entity_id
    elif b.target.entity_ids is not None:
        target["entity_ids"] = list(b.target.entity_ids)
    elif b.target.connection_id is not None:
        target["connection_id"] = b.target.connection_id
    elif b.target.connection_ids is not None:
        target["connection_ids"] = list(b.target.connection_ids)
    elif b.target.diagram_local is not None:
        dl: dict[str, object] = {"element_id": b.target.diagram_local.element_id}
        if b.target.diagram_local.diagram_id is not None:
            dl["diagram_id"] = b.target.diagram_local.diagram_id
        target["diagram_local"] = dl
    elif b.target.connection_path is not None:
        target["connection_path"] = [
            {"id": item.id, "reversed": item.reversed} if item.reversed else {"id": item.id}
            for item in b.target.connection_path
        ]

    result: dict[str, object] = {
        "id": b.id,
        "subject": subject,
        "correspondence_kind": b.correspondence_kind,
        "target": target,
    }
    if b.derived_from is not None:
        result["derived_from"] = b.derived_from
    if b.visual_role is not None:
        result["visual_role"] = b.visual_role
    return result


def bindings_to_raw(bindings: list[Binding]) -> list[dict[str, object]]:
    return [binding_to_dict(b) for b in bindings]


# ── Read side ─────────────────────────────────────────────────────────────────
#
# The persist path is deliberately lossy of shorthand: `strip_diagram_shorthand` removes
# `entity_id`, `backing_entity_id`, `binding:` and `_scope_entity_id` from `diagram-entities`, because
# the top-level `bindings:` block is the canonical form. Every consumer that wants "which model
# entity does this diagram element stand for" must therefore read it from here.
#
# It is stated once, in the domain, because three consumers each answered it by reading a field the
# persist path guarantees is absent — and the result was a C4 diagram whose elements selected nothing
# and whose drill-down badges never appeared, with a green suite the whole time.


def element_entity_ids(bindings: object) -> dict[str, str]:
    """Diagram-local element id → the model entity it represents.

    Reads the raw (frontmatter) binding shape rather than `Binding`, because every caller has the
    persisted dict in hand and converting first would be ceremony. Only `subject.kind == "entity"`
    bindings carry an element correspondence; a diagram-level `scoped-by` is a different question,
    answered by `diagram_scope_entity_id`.
    """
    resolved: dict[str, str] = {}
    if not isinstance(bindings, list):
        return resolved
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
        if element_id and entity_id:
            resolved.setdefault(element_id, entity_id)
    return resolved


def scope_target(bindings: Iterable[Binding]) -> Target | None:
    """The target of the diagram-level ``scoped-by`` binding, or ``None``.

    The *target*, not the ids inside it, because the two shapes are not the same statement: a
    landscape scoped by one system said `entity_ids`, and answering a bare tuple would have made
    the restore path guess the key back from the count and rewrite the author's declaration.
    """
    for binding in bindings:
        if binding.correspondence_kind != "scoped-by" or binding.subject.kind != "diagram":
            continue
        if binding.target.entity_id or binding.target.entity_ids:
            return binding.target
    return None


def scope_entity_ids(bindings: Iterable[Binding]) -> tuple[str, ...]:
    """Every entity the diagram-level ``scoped-by`` binding names — the parsed-record form.

    The same rule as `diagram_scope_entity_ids` over the other representation. Both exist because
    the write path holds `Binding` records while the verifier and the read envelope hold
    unvalidated frontmatter dicts, where parsing first would raise on a file whose whole problem is
    that it is malformed. `tests/domain/test_bindings.py` holds the two to the same answer; three
    modules used to spell this loop themselves, and each read only the singular target.
    """
    target = scope_target(bindings)
    if target is None:
        return ()
    return (target.entity_id,) if target.entity_id else tuple(target.entity_ids or ())


def scope_shorthand(target: Target) -> tuple[str, object]:
    """The ``diagram-entities`` key and value a scope target is written under.

    One place decides this, and it decides from the target's shape rather than from how many ids it
    holds — which is what keeps `_scope_entity_ids: [one]` round-tripping as itself.
    """
    if target.entity_id:
        return (SCOPE_KEY, target.entity_id)
    return (SCOPE_IDS_KEY, list(target.entity_ids or ()))


def diagram_scope_entity_ids(bindings: object) -> tuple[str, ...]:
    """Every entity a diagram-level ``scoped-by`` binding names, in declaration order.

    Model-backed C4 diagrams keep `diagram-entities` empty and record their scope this way. One
    reading for both target forms — the singular ``entity_id`` most diagrams carry, and the
    ``entity_ids`` set a portfolio-altitude view needs — because a caller that asks for "the scope"
    of a landscape and gets `""` cannot tell that from a diagram with no scope at all.
    """
    if not isinstance(bindings, list):
        return ()
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        subject = binding.get("subject")
        if not isinstance(subject, dict) or subject.get("kind") != "diagram":
            continue
        if binding.get("correspondence_kind") != "scoped-by":
            continue
        target = binding.get("target")
        if not isinstance(target, dict):
            continue
        if target.get("entity_id"):
            return (str(target["entity_id"]),)
        raw_ids = target.get("entity_ids")
        if isinstance(raw_ids, list) and raw_ids:
            return tuple(str(entity_id) for entity_id in raw_ids)
    return ()


def diagram_scope_entity_id(bindings: object) -> str:
    """The single entity a diagram is scoped by, or ``""`` — a filter over the set form.

    Answers the first of several for a diagram scoped by a set, which is what a caller that can
    only hold one wants; a caller that can hold the set asks `diagram_scope_entity_ids`.
    """
    scope = diagram_scope_entity_ids(bindings)
    return scope[0] if scope else ""
