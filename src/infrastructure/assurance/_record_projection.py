"""The rule every store-record projection shares: one shape, and one meaning, per record kind.

Four backends persist the assurance graph, and each returned its own idea of a record. SQLCipher gave
back whatever columns the table had; the file stores gave back whatever they wrote; PocketBase gave
back the stored fields plus its own collection metadata. The port promises "a node", "an edge", "an
analysis" — so a caller could not know what it had, and no closed response contract could be published
over any of them.

Each record kind therefore declares its field tuple and projects onto it at the store boundary
(``_analysis_records``, ``_grouping_records``, ``_node_records``, ``_edge_records``). Two rules are
common to all of them and live here rather than four times over.
"""

from __future__ import annotations


def null_if_empty(value: object) -> object:
    """``""`` becomes ``None``, because in one backend it *is* ``None``.

    PocketBase text fields cannot hold null; an unset one comes back as an empty string. So the same
    hazard read from PocketBase reported ``uca_type == ""`` and from every other store ``None`` — a
    divergence in the record's *meaning* rather than its key set, and the one a closed ``str | None``
    contract would have accepted in silence while two clients branched differently on it.

    Applied only to a record's nullable fields, and only where an empty string has no use distinct
    from having no value: a discriminator that does not apply, an architecture reference not yet
    resolved, an unattributed node's absent analysis. Never to a field whose emptiness is content.
    """
    return None if value == "" else value


def missing_required(
    row: object,
    fields: tuple[str, ...],
    nullable: frozenset[str],
) -> list[str]:
    """The non-nullable fields ``row`` does not have, for the caller to refuse over.

    Refusing rather than defaulting: a record missing its ``name`` or its ``node_type`` is corrupt, and
    filling one in would publish a record this code had partly invented. A *nullable* field's absence
    is a different thing — a store written before the field existed is opened, not migrated — so those
    read as ``None`` instead.
    """
    if not isinstance(row, dict):
        return list(fields)
    return [field for field in fields if field not in nullable and field not in row]
