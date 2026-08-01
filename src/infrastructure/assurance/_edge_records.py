"""The shapes of a node's two relations: the edges between nodes, and the references out to architecture.

Both had the same per-backend divergence the node and analysis records had, and both are read by the
routes that read a node — so a closed contract for a node detail depends on all three.

An **edge** is the same six fields in every store. PocketBase added its own row id, which
``remove_edge`` needs and no caller outside this backend may see.

An **architecture reference** is four fields, and its ``resolved_at`` showed the other half of the
problem: PocketBase writes ``""`` for "not yet resolved" because its text fields cannot hold null,
while the file stores write ``None``. Same record, two answers to "has this been resolved?".
"""

from __future__ import annotations

from collections.abc import Mapping

from src.infrastructure.assurance._record_projection import missing_required, null_if_empty

#: An edge, field for field, in ``_schema.py`` declaration order.
EDGE_RECORD_FIELDS: tuple[str, ...] = (
    "edge_id",
    "source_id",
    "target_id",
    "conn_type",
    "attributes_json",
    "created_at",
)

#: Every edge field is written when the edge is created; none is nullable.
_EDGE_NULLABLE: frozenset[str] = frozenset()

#: One architecture reference: which node points at which artifact, how, and whether the pointer has
#: been resolved against the repository yet.
ARCH_REF_RECORD_FIELDS: tuple[str, ...] = (
    "assurance_node_id",
    "arch_artifact_id",
    "ref_type",
    "resolved_at",
)

#: ``resolved_at`` is null until the reference is checked against the repository. That is the state the
#: binding surface exists to change, so it has to be representable rather than defaulted to a time.
_ARCH_REF_NULLABLE: frozenset[str] = frozenset({"resolved_at"})


def as_edge_record(row: Mapping[str, object]) -> dict[str, object]:
    """``row`` as the canonical edge: exactly :data:`EDGE_RECORD_FIELDS`, nothing else."""
    missing = missing_required(row, EDGE_RECORD_FIELDS, _EDGE_NULLABLE)
    if missing:
        raise ValueError(f"stored assurance edge record is missing {', '.join(missing)}")
    return {field: row[field] for field in EDGE_RECORD_FIELDS}


def as_edge_records(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [as_edge_record(row) for row in rows]


def as_arch_ref_record(row: Mapping[str, object]) -> dict[str, object]:
    """``row`` as the canonical architecture reference, with an unresolved one reading as ``None``."""
    missing = missing_required(row, ARCH_REF_RECORD_FIELDS, _ARCH_REF_NULLABLE)
    if missing:
        raise ValueError(f"stored architecture reference is missing {', '.join(missing)}")
    return {
        field: null_if_empty(row.get(field)) if field in _ARCH_REF_NULLABLE else row[field]
        for field in ARCH_REF_RECORD_FIELDS
    }


def as_arch_ref_records(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [as_arch_ref_record(row) for row in rows]
