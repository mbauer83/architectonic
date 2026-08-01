"""Response contracts for the document surface.

Closed models: no ``extra="allow"``. An open model documents "an object" and promises nothing
about its contents, which is what let this surface's payloads drift from the decoders reading them.
Every field a client can rely on is declared here, and a handler returning something undeclared is
a validation error rather than a silent addition.

One exception, named as such: a document *schema* is a repository-local JSON file served after
normalization, so its top level is the author's and only the keys the loader knows are declared.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, RootModel

from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted, mark_nulls_omitted


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentSummary(_Closed):
    """One row of the document list: enough to render and link, not the content."""

    artifact_id: str
    doc_type: str
    title: str
    status: str
    path: str
    keywords: list[str]
    sections: list[str]
    group: str
    is_global: bool
    last_updated: str | None = None


class DocumentListResponse(_Closed):
    """A page of documents, with the count of the *filtered* population.

    ``total`` is the size of the population the filters select, not of the page and not of the
    repository — a facet whose count came from the page would read zero for every filter the user
    has not yet scrolled into.
    """

    total: int
    items: list[DocumentSummary]


class DocumentDetailResponse(_Closed):
    """One document, with its content.

    ``content_snippet`` is carried alongside ``content_text`` rather than derived by the client:
    it is the same truncation the search surfaces use, so a title-and-snippet list built from a
    detail read looks identical to one built from a search result.
    """

    artifact_id: str
    artifact_type: str
    record_type: str
    doc_type: str
    title: str
    status: str
    path: str
    keywords: list[str]
    sections: list[str]
    content_snippet: str
    content_text: str
    group: str
    is_global: bool
    last_updated: str | None = None
    extra: dict[str, object] = {}


class DocumentSectionSpecEntry(NullsOmitted):
    """One section a document type declares: its heading, an optional starter, and which entity
    types a section of this kind is expected — or merely invited — to connect to."""

    name: str
    template: str | None = None
    required_entity_type_connections: list[str] | None = None
    suggested_entity_type_connections: list[str] | None = None


class DocumentSchemaEntry(NullsOmitted):
    """One document type's schema file, normalized.

    Open, and this is the ``authored`` case rather than a gap: the body is a repository-local JSON
    file, and everything below is what the loader normalizes out of it. A key the loader does not
    know is the author's, and refusing it would 500 a read of a repository whose schema file simply
    says more than this package does.

    ``required_sections`` is derived from ``sections`` rather than read from the file — the two
    disagreed in older files, and the section list is the one the writer enforces.
    """

    model_config = ConfigDict(extra="allow")

    name: str | None = None
    abbreviation: str | None = None
    subdirectory: str | None = None
    #: The JSON Schema a document's frontmatter validates against. Served as written: its keywords
    #: are that specification's, not this surface's.
    frontmatter_schema: dict[str, Any] | None = None
    sections: list[DocumentSectionSpecEntry]
    required_sections: list[str]
    #: Section name → starter text, present only for the sections that declare one.
    section_templates: dict[str, str] | None = None
    required_entity_type_connections: list[str] | None = None
    suggested_entity_type_connections: list[str] | None = None


class DocumentSchemataResponse(RootModel[dict[str, DocumentSchemaEntry]]):
    """Every document type's schema, keyed by doc type.

    A ``RootModel`` rather than ``dict[str, …]`` on the route: the latter publishes an inline schema
    a generated client cannot refer to. An open *map* with a closed key set is not the shape here —
    the keys are whichever schema files the repository holds, which is the repository's to decide.
    """

    # The claim :class:`NullsOmitted` carries, set directly: a ``RootModel`` has its own root type
    # and cannot inherit a second model, and the document still has to say that this route's unset
    # optionals are absent.
    model_config = ConfigDict(json_schema_extra=mark_nulls_omitted)

    root: dict[str, DocumentSchemaEntry]
