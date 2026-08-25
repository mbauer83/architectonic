"""How a record becomes a row, apart from when rows are written.

Split out of `_sqlite_store` because the two are different questions and the file had grown past the
length policy answering both. The column order here is the column order in the INSERT statements
next door and in the DDL beside those — three places that must agree, which is exactly why they are
worth reading together rather than interleaved with transaction handling.

`scope` is passed rather than reached for: it is derived from where a repository is mounted, which a
row builder has no business knowing about.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from src.domain.ontology_representation.artifact_types import (
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
    ScratchpadNoteRecord,
)

_ScopeFn = Callable[[Path], str]


def entity_row(r: EntityRecord, scope: _ScopeFn) -> tuple[object, ...]:
    return (
        r.artifact_id,
        r.artifact_type,
        r.name,
        r.version,
        r.status,
        r.domain,
        r.subdomain,
        str(r.path),
        scope(r.path),
        json.dumps(list(r.keywords)),
        json.dumps(r.extra, sort_keys=True),
        r.content_text,
        json.dumps(r.display_blocks, sort_keys=True),
        r.display_label,
        r.display_alias,
        r.host_diagram_id,
        r.group,
    )

def connection_row(r: ConnectionRecord, scope: _ScopeFn) -> tuple[str, ...]:
    return (
        r.artifact_id,
        r.source,
        r.target,
        r.conn_type,
        r.version,
        r.status,
        str(r.path),
        scope(r.path),
        json.dumps(r.extra, sort_keys=True),
        r.content_text,
        json.dumps(list(r.associated_entities)),
        r.src_multiplicity,
        r.tgt_multiplicity,
        json.dumps(list(r.specializations)),
        r.group,
    )

def diagram_row(r: DiagramRecord, scope: _ScopeFn) -> tuple[str, ...]:
    return (
        r.artifact_id,
        r.artifact_type,
        r.name,
        r.diagram_type,
        r.version,
        r.status,
        str(r.path),
        scope(r.path),
        json.dumps(r.extra, sort_keys=True),
        r.group,
    )

def document_row(r: DocumentRecord, scope: _ScopeFn) -> tuple[str, ...]:
    return (
        r.artifact_id,
        r.doc_type,
        r.title,
        r.status,
        str(r.path),
        scope(r.path),
        json.dumps(list(r.keywords)),
        json.dumps(list(r.sections)),
        r.content_text,
        json.dumps(r.extra, sort_keys=True),
        r.group,
    )

def note_row(r: ScratchpadNoteRecord, scope: _ScopeFn) -> tuple[str, ...]:
    return (
        r.artifact_id,
        r.scratchpad_id,
        r.scratchpad_name,
        r.note_id,
        r.title,
        r.body,
        r.element_type,
        r.domain,
        r.area,
        r.status,
        str(r.path),
        scope(r.path),
        r.group,
    )


def entity_fts_row(rec: EntityRecord) -> tuple[str, ...]:
    """One entity's full-text row.

    A function rather than two inline tuples: the incremental upsert and the bulk rebuild both build
    this row, and they were spelled separately — so a column added to the table had to be remembered
    in two places, and a column added to one of them would have failed only whichever path ran first.
    Every other kind already answers this through a builder or a one-liner.
    """
    return (
        rec.artifact_id,
        rec.name,
        rec.artifact_type,
        rec.domain,
        rec.subdomain,
        " ".join(rec.keywords),
        rec.content_text,
        rec.display_label,
        rec.host_diagram_id or "",
    )


def note_fts_row(r: ScratchpadNoteRecord) -> tuple[str, ...]:
    return (r.artifact_id, r.scratchpad_id, r.title, r.body, r.element_type, r.domain, r.scratchpad_name)
