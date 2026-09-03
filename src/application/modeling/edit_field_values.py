"""What an artifact's editable fields currently hold — the edit vocabulary, read off the artifact.

`edit_field_catalogue` says which fields an edit may name. This says what those fields say *now*, so
a recorded edit can be compared against the artifact it was proposed for. That comparison is how a
change is found to have been integrated upstream: the reviewer applied it, the enterprise artifact
now says what the proposal asked, and the local record can be closed.

**Parsed fields, never rendered text.** The tempting alternative — replay the edit and diff the
result against the file — fails on its own output: a replay re-renders the whole artifact, which
normalises quoting, key order and whitespace, so an integrated change and an unintegrated one both
come back different. Reading the fields the edit actually names avoids the question entirely.

**Unreadable is not equal.** A field this module cannot read is simply absent from what it returns,
and the caller treats absence as "not integrated". That is the safe direction: a change wrongly left
open is a change an author can still submit, while one wrongly closed is one that silently never
happens. Diagram structure is the honest example — most of a diagram's editable fields are nested
documents whose current value has no single reading, so a diagram proposal is never auto-closed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.application.artifacts.parsing import parse_entity_content_sections
from src.domain.ontology_representation.artifact_types import DocumentRecord, EntityRecord


def current_entity_values(record: EntityRecord) -> Mapping[str, Any]:
    """Every editable entity field this module can read, in the edit vocabulary's names.

    Three sources, because that is where they live: the indexed record, the parsed `§content`
    sections, and the frontmatter `extra` for attribute types. `parse_entity_content_sections` is the
    reader that already owns the section split; re-deriving it here would be a second one.
    """
    sections = parse_entity_content_sections(record.content_text)
    return {
        "name": record.name,
        "status": record.status,
        "version": record.version,
        "group": record.group,
        "keywords": tuple(record.keywords),
        "specializations": tuple(record.specializations),
        "summary": sections.get("summary"),
        "properties": sections.get("properties"),
        "notes": sections.get("notes"),
        "attribute_types": record.extra.get("attribute-types"),
    }


def current_document_values(record: DocumentRecord) -> Mapping[str, Any]:
    """Every editable document field this module can read.

    `body` and `extra_frontmatter` are absent on purpose: a document's body is prose that the write
    path reformats, and comparing it would report an integration the moment a reviewer rewrapped a
    line. A proposal touching either is left for a person to close.

    `version` is absent for a different reason: `DocumentRecord` does not carry one. It is an
    editable field with no reading here, which is exactly the case the module docstring describes —
    absent means "cannot decide", not "unchanged".
    """
    return {
        "title": record.title,
        "status": record.status,
        "group": record.group,
        "keywords": tuple(record.keywords),
        "last_updated": record.last_updated,
    }


def comparable(value: Any) -> Any:
    """Normalise a value so two readings of the same content compare equal.

    Sequences become tuples because one side arrives from YAML as a list and the other from a record
    as a tuple; mappings are normalised through their items for the same reason. Strings are stripped
    at the edges only — collapsing internal whitespace would make two genuinely different summaries
    compare equal, which is the error that closes a change nobody applied.
    """
    match value:
        case str():
            return value.strip()
        case Mapping():
            return tuple(sorted((str(k), comparable(v)) for k, v in value.items()))
        case list() | tuple():
            return tuple(comparable(v) for v in value)
        case _:
            return value
