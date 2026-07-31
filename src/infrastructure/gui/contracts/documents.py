"""Response contracts for the document surface.

Closed models: no ``extra="allow"``. An open model documents "an object" and promises nothing
about its contents, which is what let this surface's payloads drift from the decoders reading them.
Every field a client can rely on is declared here, and a handler returning something undeclared is
a validation error rather than a silent addition.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


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
