"""The assurance node record's shape, as every backend must hand it back.

The third record with a per-backend key set, after the analysis and the group, and the one that
matters most: nearly every read on this surface embeds a node. SQLCipher's ``SELECT *`` returned
nineteen columns, the file stores wrote seventeen, and PocketBase returned those seventeen plus its
own collection metadata. The port promises "a node", so nothing that reads one could know what it
had, and no closed response contract could be published over it.

The frontend proved the cost in both directions at once: ``domain/schemas/assurance.ts`` required
``created_by``, which only SQLCipher sends, *and* omitted ``failure_type`` and ``mode``, which every
store writes. One decoder, stricter than the surface in one place and blinder in another.

``created_by`` is not in the canonical set. It exists as a SQLCipher column with a ``''`` default and
nothing anywhere writes it or reads it — so publishing it would document an attribution this system
does not record. The column stays where it is: opening an existing store must not rewrite it.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.infrastructure.assurance._record_projection import missing_required, null_if_empty

#: The node record, field for field. The order is the declaration order in ``_schema.py``, so the two
#: read as the same list.
NODE_RECORD_FIELDS: tuple[str, ...] = (
    "node_id",
    "node_type",
    "name",
    "status",
    "tlp",
    "concern_class",
    "disposition",
    "uca_type",
    "failure_type",
    "mode",
    "binding_status",
    "node_role",
    "analysis_id",
    "attributes_json",
    "content_text",
    "created_at",
    "updated_at",
)

#: Fields that are null on a node the discriminator does not apply to — a hazard has no ``uca_type``,
#: an unattributed legacy node no ``analysis_id``. Every other field is written at creation.
_NULLABLE_FIELDS: frozenset[str] = frozenset({
    "concern_class",
    "disposition",
    "uca_type",
    "failure_type",
    "mode",
    "binding_status",
    "node_role",
    "analysis_id",
})


def as_node_record(row: Mapping[str, object]) -> dict[str, object]:
    """``row`` as the canonical record: exactly :data:`NODE_RECORD_FIELDS`, nothing else.

    A nullable field absent from a stored row reads as ``None`` — a store written before
    ``failure_type`` and ``mode`` were added has neither, and it is opened rather than migrated. A
    non-nullable one absent is a corrupt record and says so, because defaulting a missing ``name`` or
    ``node_type`` would publish a node this code had partly invented.

    The backend's own row identity is dropped. It addresses the row inside that backend; the node
    already has an identity, and passing both on invites a caller to use the wrong one.
    """
    missing = missing_required(row, NODE_RECORD_FIELDS, _NULLABLE_FIELDS)
    if missing:
        raise ValueError(f"stored assurance node record is missing {', '.join(missing)}")
    return {
        field: null_if_empty(row.get(field)) if field in _NULLABLE_FIELDS else row.get(field)
        for field in NODE_RECORD_FIELDS
    }


def as_node_records(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """:func:`as_node_record` over a collection, since every backend has both a list and a detail read
    and a projection applied to only one of them is the defect that surfaces when a reader scrolls."""
    return [as_node_record(row) for row in rows]
