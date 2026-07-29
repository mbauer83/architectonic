"""Binding data model — the single diagram↔model correspondence mechanism.

A Binding relates a diagram subject (entity, connection, or the diagram itself)
to a model target via a declared correspondence_kind.  Canonical bindings live
at the top-level ``bindings:`` frontmatter key of every diagram.  The write
path also accepts nested ``binding:`` shorthand on diagram entity items and
normalises it here.

No sync_policy or derivation_basis fields — those are deferred per the plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CORE_CORRESPONDENCE_KINDS: frozenset[str] = frozenset(
    {"represents", "abstracts", "refines", "scoped-by", "traces-to"}
)


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
    """Tagged union; exactly one field must be set."""

    entity_id: str | None = None
    connection_id: str | None = None
    connection_ids: tuple[str, ...] | None = None
    diagram_local: DiagramLocalTarget | None = None
    connection_path: tuple[ConnectionPathItem, ...] | None = None

    def __post_init__(self) -> None:
        filled = sum(
            v is not None
            for v in (
                self.entity_id,
                self.connection_id,
                self.connection_ids,
                self.diagram_local,
                self.connection_path,
            )
        )
        if filled != 1:
            raise ValueError(
                "Target must have exactly one of: entity_id, connection_id, "
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
